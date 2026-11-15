"""Experiment t9-env-subagents-pastdev: shared run memory through past.dev.

Goal: sub-agents start with an empty context and re-read the same data and files again and
again. This module gives the whole run (orchestrator and every sub-agent) one shared memory,
held in past.dev and scoped to this run only:

* capture (no model call): every read-only inspection of /data, /opt/task-env or the
  pipeline folder made by any agent is stored as an ``observation`` card (exact command and
  output); every file a sub-agent produces is stored as a ``file`` card;
* lessons (no extra model call): each sub-agent ends its report with a ``LEARNED`` block,
  stored as ``convention`` / ``how_to`` / ``pitfall`` / ``fact`` cards;
* the librarian: before a sub-agent starts, past.dev ranks the cards against its brief and the
  harness prepends the most relevant ones (budgeted) to the brief. Conventions are never left
  to the ranking: all of them are always included;
* on demand: a ``recall`` tool asks past.dev a question in natural language.

Scope and safety: one past.dev audience per run, readable only by that run's reader identity,
so nothing crosses runs. Only the host-side harness talks to past.dev; ``PAST_API_KEY`` never
enters the sandbox and is never printed. If past.dev is unavailable the run continues and
falls back to a local keyword ranking; the fallback is recorded so such runs can be excluded.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, ToolDef, tool
from inspect_ai.util import sandbox, store

CONDITION = "t9-env-subagents-pastdev"
API_KEY_ENV = "PAST_API_KEY"
BASE_URL_ENV = "PAST_API_BASE_URL"
DEFAULT_BASE_URL = "https://api.past.dev/api/v1"
STORE_KEY = "bixbench3_run_memory"

PACK_CHARS = 8000  # ~2,000 tokens of ranked memory added to a sub-agent brief
CONVENTIONS_CHARS = 4000  # conventions are always included, up to this size
RECALL_MAX_TOKENS = 4000
RECALL_LIMIT = 60
RECALL_TOOL_CHARS = 4000
OBS_MAX = 1500  # characters of command output kept in an observation card
CARD_TEXT_MAX = 2000
LEARNED_MAX_ITEMS = 12
INGEST_WAIT_SECONDS = 45
HTTP_TIMEOUT_SECONDS = 30
MAX_FILES_REGISTERED = 20

LEARNED_KINDS = {"convention", "how_to", "pitfall", "fact"}

_PATH = re.compile(
    r"(?:/workspace/data|(?<![\w./-])\./data|(?<![\w./-])data(?=/)|/data|/opt/task-env|"
    r"/workspace/work/pipeline|(?<![\w./-])work/pipeline)(?:/[^\s'\"`;|&)>,\]]*)?"
)
_READ = re.compile(
    r"\b(head|tail|cat|zcat|gzip -cd|gunzip -c|zless|less|wc|ls|find|stat|file|du|cut|awk|grep|zgrep|"
    r"sort|uniq|column|jq|sed -n)\b|read_csv|read_table|read\.table|read\.csv|readLines|fread|"
    r"read_text|\.read\(|json\.load|gzip\.open|open\(|\.head\(|\.columns|\.shape|\.dtypes|"
    r"value_counts|nrow|ncol|colnames|str\(|summary\(|view "
)
_WRITE = re.compile(
    r"(?<![0-9&])>(?!&)|>>|\btee\b|\bcp\b|\bmv\b|\brm\b|\bmkdir\b|\bln\b|\btouch\b|\bchmod\b|"
    r"to_csv|to_parquet|write_text|write_bytes|\.write\(|open\([^)]*['\"][wax]b?['\"]|write\.csv|write\.table|"
    r"saveRDS|fwrite|Rscript\s+\S+\.R\b|python3?\s+\S+\.py\b|bash\s+\S+\.sh\b|nohup|subprocess|"
    r"hisat2|featureCounts|cutadapt|samtools|fastqc|tagseq_clipper|DESeq|enrichGO|pip install|"
    r"install\.packages|BiocManager|mamba|conda|apt-get|kill\b",
    re.IGNORECASE,
)
_PROMPT_LINE = re.compile(r"^\S+@\S+:[^\n]*[#$] ?.*$", re.MULTILINE)
_CONTINUATION = re.compile(r"^(?:> )+", re.MULTILINE)
_ERROR = re.compile(
    r"No such file or directory|Traceback \(most recent call last\)|command not found|"
    r"Permission denied|cannot access|Error in |^Error|SyntaxError|NameError",
    re.MULTILINE,
)
_SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|past_[sm]k_[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_-]{16,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
_LEARNED_BLOCK = re.compile(r"LEARNED\s*:?\s*(?:```(?:json)?\s*)?(\[.*?\])\s*(?:```)?", re.DOTALL)
_OUTPUT_DIR = re.compile(r"OUTPUT:\s*(/[^\s,;]+?)/?(?:\s|$)")

MEMORY_NOTE = """## Experiment Note: Shared Run Memory

Everything above still applies and takes precedence. This note only adds a shared memory for this run.

The harness records automatically what any agent learns by inspecting files (the exact commands and
their outputs), every file a sub-agent produces, and the LEARNED notes sub-agents return. Before a
sub-agent starts, the harness adds to its brief all conventions of the run and the most relevant
known facts, so it does not have to rediscover them.

- Orchestrator: right after the dependency plan, call `record_convention` once for every convention
  that several artifacts must share (identifier formats, gene symbol source, sample-to-condition
  mapping, shared scripts, column names and ordering). Every later sub-agent receives all
  conventions. Do not paste long file listings or data descriptions into briefs: the memory
  carries them.
- Every agent: before inspecting data or upstream files, use what your brief's memory section shows
  and the `recall` tool; inspect a file only for information that is not already known.
"""

SUBAGENT_MEMORY_RULES = """
Shared run memory:
- The section "Shared run memory" in your brief was established earlier in THIS run by other agents
  (exact command outputs and notes). Reuse it instead of re-reading the same files; inspect a file
  only for information that is missing. Use the `recall` tool to ask what other agents found.
- Conventions listed there are mandatory.
- End your final report with a block listing at most 8 things later agents should know
  (conventions you followed, commands or scripts that work, problems and their fixes, facts
  about the data), exactly in this form:
  LEARNED: [{"kind": "convention|how_to|pitfall|fact", "key": "short-id", "text": "one or two sentences"}]
  Never include secrets.
"""

_background: set[asyncio.Task[Any]] = set()


# ─── past.dev client ───────────────────────────────────────────────────────────────────
class PastDevError(RuntimeError):
    pass


class PastDevClient:
    """Minimal past.dev Memory API client: audiences, ingest, ingestion status, recall."""

    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL,
                 opener: Callable[..., Any] = urlopen) -> None:
        if not api_key:
            raise PastDevError(f"{API_KEY_ENV} is not set")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._opener = opener

    @classmethod
    def from_environment(cls) -> PastDevClient:
        return cls(os.environ.get(API_KEY_ENV, ""), base_url=os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL))

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        last = "unknown"
        for attempt in range(3):
            request = Request(
                f"{self._base_url}{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            )
            try:
                with self._opener(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                    payload = response.read()
                return json.loads(payload) if payload else {}
            except HTTPError as error:
                last = f"HTTP {error.code}"
                if error.code not in (429, 500, 502, 503, 504):
                    break
            except (URLError, TimeoutError, OSError) as error:
                last = type(error).__name__
            time.sleep(1.0 * (2 ** attempt))
        raise PastDevError(f"past.dev {method} {path.split('?')[0]} failed: {last}")

    def put_audience(self, slug: str, identities: list[str]) -> dict[str, Any]:
        return self._request("PUT", f"/audiences/{slug}", {"kind": "fixed", "identities": identities})

    def ingest(self, card: dict[str, Any], audience: str) -> dict[str, Any]:
        return self._request("POST", "/ingest", {
            "id": card["id"],
            "content": f"[{card['kind']}] {card['title']}\n{card['text']}",
            "label": card["title"][:200],
            "timestamp": card["ts"],
            "metadata": {key: card[key] for key in ("run", "kind", "key", "author", "paths")},
            "audience": audience,
            "idempotencyKey": f"{card['id']}-{hashlib.sha256(card['text'].encode()).hexdigest()[:12]}",
        })

    def ingestion_status(self, ingestion_id: str) -> str:
        return str(self._request("GET", f"/ingest/{ingestion_id}").get("status", "unknown"))

    def recall(self, query: str, *, identity: str, max_tokens: int = RECALL_MAX_TOKENS,
               limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        response = self._request("POST", "/recall", {
            "query": query[:8000], "identity": identity, "limit": limit, "maxTokens": max_tokens,
            "sort": "relevance",
        })
        results = response.get("results", [])
        return results if isinstance(results, list) else []


def _client() -> PastDevClient | None:
    try:
        return PastDevClient.from_environment()
    except PastDevError:
        return None


# ─── memory state (Inspect sample store) ──────────────────────────────────────────────
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(text: str, size: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:size]


def _state() -> dict[str, Any]:
    value = store().get(STORE_KEY)
    if not value:
        value = new_state(run="unscoped", pastdev=False, reason="memory not initialised")
        store().set(STORE_KEY, value)
    return value


def _save(value: dict[str, Any]) -> None:
    store().set(STORE_KEY, value)


def new_state(*, run: str, pastdev: bool, reason: str | None = None) -> dict[str, Any]:
    slug = "bb3-" + _hash(run, 20)
    return {
        "condition": CONDITION,
        "run": run,
        "audience": slug,
        "reader": f"{slug}-reader",
        "pastdev": pastdev,
        "pastdev_reason": reason,
        "cards": {},
        "pending": [],
        "stats": {
            "cards_by_kind": {}, "cards_by_author": {}, "observations_captured": 0,
            "inspected_by": {}, "packs": [], "recall_calls": 0, "pastdev_errors": 0,
            "ranking_fallbacks": 0, "learned_items": 0, "files_registered": 0,
        },
    }


def _log_dir() -> Path | None:
    value = os.environ.get("BIXBENCH3_BROKER_LOG_DIR")
    return Path(value) if value else None


def _append_log(name: str, record: dict[str, Any]) -> None:
    directory = _log_dir()
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _write_stats(value: dict[str, Any]) -> None:
    directory = _log_dir()
    if directory is None:
        return
    summary = {key: value[key] for key in ("condition", "run", "audience", "pastdev", "pastdev_reason")}
    stats = dict(value["stats"])
    stats["inspected_by"] = {path: sorted(set(authors)) for path, authors in stats["inspected_by"].items()}
    summary["stats"] = stats
    summary["n_cards"] = len(value["cards"])
    summary["updated_at"] = _now()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / ".memory_stats.json.tmp"
        tmp.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(directory / "memory_stats.json")
    except OSError:
        pass


# ─── writing cards ────────────────────────────────────────────────────────────────────
def make_card(*, run: str, kind: str, key: str, title: str, text: str, author: str,
              paths: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "id": f"{_hash(run, 10)}-{kind}-{_hash(kind + chr(0) + key)}",
        "run": run, "kind": kind, "key": key[:300], "title": title[:200],
        "text": text[:CARD_TEXT_MAX], "author": author, "paths": sorted(set(paths))[:20], "ts": _now(),
    }


async def _ingest(card: dict[str, Any], audience: str) -> None:
    client = _client()
    if client is None:
        return
    try:
        response = await asyncio.to_thread(client.ingest, card, audience)
    except PastDevError as error:
        value = _state()  # re-read after the await: other coroutines may have written meanwhile
        value["stats"]["pastdev_errors"] += 1
        _save(value)
        _append_log("memory_events.jsonl", {"event": "ingest_error", "card": card["id"], "error": str(error), "ts": _now()})
        return
    ingestion_id = response.get("ingestionId")
    if ingestion_id and response.get("status") != "completed":
        value = _state()
        value["pending"].append(str(ingestion_id))
        _save(value)


async def remember(kind: str, key: str, text: str, *, author: str, title: str | None = None,
                   paths: Iterable[str] = ()) -> dict[str, Any] | None:
    """Store one card in the run memory (local mirror now, past.dev in the background)."""
    if not text.strip() or _SECRET.search(text) or _SECRET.search(key):
        return None
    value = _state()
    card = make_card(run=value["run"], kind=kind, key=key, title=title or f"{kind}: {key}", text=text,
                     author=author, paths=paths)
    previous = value["cards"].get(card["id"])
    value["cards"][card["id"]] = card
    stats = value["stats"]
    stats["cards_by_kind"][kind] = stats["cards_by_kind"].get(kind, 0) + (0 if previous else 1)
    stats["cards_by_author"][author] = stats["cards_by_author"].get(author, 0) + (0 if previous else 1)
    _save(value)
    _append_log("memory_cards.jsonl", {"event": "update" if previous else "create", **card})
    _write_stats(value)
    if value["pastdev"]:
        task = asyncio.create_task(_ingest(card, value["audience"]))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return card


async def flush_ingestion(timeout: float = INGEST_WAIT_SECONDS) -> None:
    """Wait until the cards written so far are searchable in past.dev (bounded)."""
    if _background:
        await asyncio.wait(set(_background), timeout=timeout / 2)
    value = _state()
    client = _client()
    if not value["pastdev"] or client is None or not value["pending"]:
        return
    deadline = time.monotonic() + timeout / 2
    remaining = list(value["pending"])
    while remaining and time.monotonic() < deadline:
        still: list[str] = []
        for ingestion_id in remaining:
            try:
                status = await asyncio.to_thread(client.ingestion_status, ingestion_id)
            except PastDevError:
                status = "unknown"
            if status not in ("completed", "failed"):
                still.append(ingestion_id)
        remaining = still
        if remaining:
            await asyncio.sleep(2)
    value = _state()
    value["pending"] = remaining
    _save(value)


# ─── automatic capture of inspections ─────────────────────────────────────────────────
def normalize_path(path: str) -> str:
    path = path.rstrip(".:")
    for prefix, replacement in (("/workspace/data", "/data"), ("./data", "/data"), ("work/pipeline", "/workspace/work/pipeline")):
        if path.startswith(prefix) and not path.startswith(replacement):
            return replacement + path[len(prefix):]
    if path.startswith("data/"):
        return "/" + path
    return path


def command_of(tool_name: str, arguments: dict[str, Any]) -> str | None:
    if tool_name == "bash_session":
        if arguments.get("action") not in (None, "type_submit", "type"):
            return None
        return str(arguments.get("input") or "") or None
    if tool_name == "python":
        return str(arguments.get("code") or "") or None
    if tool_name == "text_editor":
        if arguments.get("command") != "view":
            return None
        view_range = arguments.get("view_range")
        return f"view {arguments.get('path')}" + (f" {view_range}" if view_range else "")
    return None


def inspection_paths(command: str) -> list[str]:
    """Paths read by a read-only inspection command; empty if the command writes or runs work."""
    cleaned = re.sub(r"2>\s*/dev/null|2>&1|>\s*/dev/null", "", command)
    if _WRITE.search(cleaned) or not _READ.search(cleaned):
        return []
    paths = {normalize_path(match.group(0)) for match in _PATH.finditer(cleaned)}
    return sorted(path for path in paths if path not in ("/data", "/workspace/work/pipeline", "/opt/task-env") or
                  re.search(r"\b(ls|find|du)\b", cleaned))


def clean_output(text: str) -> str:
    text = _PROMPT_LINE.sub("", text)
    text = _CONTINUATION.sub("", text)
    return "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip()).strip()


def _result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(str(getattr(part, "text", "")) for part in result if getattr(part, "text", None))
    return str(getattr(result, "text", "") or "")


async def capture_call(tool_name: str, arguments: dict[str, Any], result: Any, author: str) -> None:
    command = command_of(tool_name, arguments)
    if not command:
        return
    paths = inspection_paths(command)
    if not paths:
        return
    output = clean_output(_result_text(result))
    if not output or _ERROR.search(output[:400]):
        return
    value = _state()
    for path in paths:
        value["stats"]["inspected_by"].setdefault(path, []).append(author)
    value["stats"]["observations_captured"] += 1
    _save(value)
    shown = output if len(output) <= OBS_MAX else output[:OBS_MAX] + f"\n... [{len(output) - OBS_MAX} more characters]"
    one_line = " ".join(command.split())
    await remember(
        "observation", key=one_line, author=author, paths=paths,
        title=f"observation of {', '.join(paths[:3])}",
        text=f"$ {one_line[:400]}\n{shown}",
    )


def with_capture(tool_object: Tool, author: str) -> Tool:
    """The same tool, plus capture of read-only inspections into the run memory."""
    definition = ToolDef(tool_object)

    # Inspect passes the model's tool arguments through unchanged only to a `**kwargs: Any`
    # parameter (model._call_tools.tool_params); any other name receives them as one argument.
    async def wrapped(**kwargs: Any) -> Any:
        arguments = kwargs
        result = await definition.tool(**arguments)
        try:
            await capture_call(definition.name, arguments, result, author)
        except Exception as error:  # capture must never change what the agent sees
            _append_log("memory_events.jsonl", {"event": "capture_error", "error": repr(error)[:300], "ts": _now()})
        return result

    return ToolDef(
        wrapped, name=definition.name, description=definition.description, parameters=definition.parameters,
        parallel=definition.parallel, viewer=definition.viewer, model_input=definition.model_input,
        options=definition.options,
    ).as_tool()


# ─── lessons and produced files ───────────────────────────────────────────────────────
def parse_learned(report: str) -> list[dict[str, str]]:
    matches = list(_LEARNED_BLOCK.finditer(report))
    if not matches:
        return []
    try:
        items = json.loads(matches[-1].group(1))
    except json.JSONDecodeError:
        return []
    learned: list[dict[str, str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        kind = str(item.get("kind", "fact")).strip().lower()
        learned.append({
            "kind": kind if kind in LEARNED_KINDS else "fact",
            "key": str(item.get("key") or item.get("text"))[:120],
            "text": str(item["text"])[:800],
        })
    return learned[:LEARNED_MAX_ITEMS]


def strip_learned(report: str) -> tuple[str, int]:
    """Report for the caller without the LEARNED block (the memory holds it)."""
    matches = list(_LEARNED_BLOCK.finditer(report))
    if not matches:
        return report, 0
    last = matches[-1]
    count = len(parse_learned(report))
    return (report[:last.start()].rstrip() + f"\n\n[LEARNED: {count} item(s) saved to the run memory]").strip(), count


def output_dir_of(brief: str) -> str | None:
    match = _OUTPUT_DIR.search(brief)
    return match.group(1) if match else None


_DESCRIBE_FILES = r"""
import json, os, sys
root = sys.argv[1]; limit = int(sys.argv[2]); out = []
if os.path.isdir(root):
    for name in sorted(os.listdir(root))[:200]:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        item = {"path": path, "bytes": os.path.getsize(path)}
        if name.endswith((".csv", ".tsv", ".txt", ".json", ".md", ".gmt", ".R", ".py", ".sh")) and item["bytes"] < 300_000_000:
            with open(path, "rb") as handle:
                head = handle.readline(400).decode("utf-8", "replace").rstrip()
                handle.seek(0)
                item["lines"] = sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 20), b""))
            item["first_line"] = head
        out.append(item)
        if len(out) >= limit:
            break
print(json.dumps(out))
"""


async def register_files(directory: str, author: str) -> int:
    try:
        result = await sandbox().exec(["python3", "-c", _DESCRIBE_FILES, directory, str(MAX_FILES_REGISTERED)], timeout=120)
        items = json.loads(result.stdout.strip().splitlines()[-1]) if result.success else []
    except Exception:
        return 0
    for item in items:
        details = f"{item['path']} ({item['bytes']} bytes" + (f", {item['lines']} lines" if "lines" in item else "") + ")"
        if item.get("first_line"):
            details += f"\nfirst line: {item['first_line']}"
        await remember("file", key=item["path"], author=author, paths=[item["path"]],
                       title=f"file {item['path']}", text=details + f"\nproduced by {author}")
    value = _state()
    value["stats"]["files_registered"] += len(items)
    _save(value)
    return len(items)


async def absorb_subagent(report: str, brief: str, author: str) -> str:
    """After a sub-agent: store its LEARNED items and produced files; return the shortened report."""
    for item in parse_learned(report):
        await remember(item["kind"], key=item["key"], text=item["text"], author=author,
                       title=f"{item['kind']}: {item['key']}")
    value = _state()
    value["stats"]["learned_items"] += len(parse_learned(report))
    _save(value)
    directory = output_dir_of(brief)
    if directory:
        await register_files(directory, author)
    shortened, _ = strip_learned(report)
    return shortened


# ─── the librarian: context pack for a sub-agent ──────────────────────────────────────
def render_card(card: dict[str, Any]) -> str:
    if card["kind"] == "observation":
        return f"- observed by {card['author']}:\n```\n{card['text']}\n```"
    return f"- [{card['kind']}] {card['title']} (from {card['author']}): {card['text']}"


def keyword_rank(query: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback ranking when past.dev is unavailable: shared paths first, then shared words."""
    query_paths = {normalize_path(match.group(0)) for match in _PATH.finditer(query)}
    words = set(re.findall(r"[a-z0-9_]{4,}", query.lower()))

    def score(card: dict[str, Any]) -> tuple[int, int]:
        path_hits = sum(1 for path in card["paths"] if path in query_paths)
        word_hits = len(words & set(re.findall(r"[a-z0-9_]{4,}", (card["title"] + " " + card["text"]).lower())))
        return path_hits, word_hits

    scored = [(score(card), card) for card in cards]
    return [card for (paths, hits), card in sorted(scored, key=lambda item: item[0], reverse=True) if paths or hits]


async def ranked_cards(query: str) -> tuple[list[dict[str, Any]], str]:
    """Cards of this run ranked by relevance to the query: past.dev first, local fallback."""
    value = _state()
    cards = value["cards"]
    candidates = [card for card in cards.values() if card["kind"] != "convention"]
    client = _client()
    if value["pastdev"] and client is not None:
        try:
            await flush_ingestion()
            results = await asyncio.to_thread(client.recall, query, identity=value["reader"])
            ordered: list[dict[str, Any]] = []
            seen: set[str] = set()
            for result in results:
                for source in result.get("sources") or []:
                    source_id = str(source.get("sourceId"))
                    card = cards.get(source_id)
                    if card and card["kind"] != "convention" and source_id not in seen:
                        seen.add(source_id)
                        ordered.append(card)
            return ordered, "pastdev"
        except PastDevError as error:
            value = _state()
            value["stats"]["pastdev_errors"] += 1
            _save(value)
            _append_log("memory_events.jsonl", {"event": "recall_error", "error": str(error), "ts": _now()})
    value = _state()
    value["stats"]["ranking_fallbacks"] += 1
    _save(value)
    return keyword_rank(query, candidates), "local_fallback"


def _fit(blocks: list[tuple[str, dict[str, Any]]], budget: int) -> tuple[list[str], list[str]]:
    kept, ids, used = [], [], 0
    for text, card in blocks:
        if used + len(text) > budget:
            continue
        kept.append(text)
        ids.append(card["id"])
        used += len(text) + 1
    return kept, ids


async def build_pack(brief: str, role: str) -> str:
    value = _state()
    conventions = sorted((card for card in value["cards"].values() if card["kind"] == "convention"),
                         key=lambda card: card["ts"])
    convention_lines, convention_ids = _fit([(render_card(card), card) for card in conventions], CONVENTIONS_CHARS)
    ranked, source = await ranked_cards(brief)
    known_lines, known_ids = _fit([(render_card(card), card) for card in ranked], PACK_CHARS)
    value = _state()
    value["stats"]["packs"].append({
        "role": role, "ranking": source, "conventions": len(convention_ids), "cards": len(known_ids),
        "chars": sum(map(len, convention_lines + known_lines)), "ts": _now(),
    })
    _save(value)
    _append_log("memory_packs.jsonl", {"role": role, "ranking": source, "convention_ids": convention_ids,
                                       "card_ids": known_ids, "ts": _now()})
    _write_stats(value)
    if not convention_lines and not known_lines:
        return ""
    parts = [
        "## Shared run memory",
        "Established earlier in THIS run by other agents. Reuse it instead of re-reading the same files;",
        "inspect a file only for information that is missing here. Use `recall` for anything else.",
    ]
    if convention_lines:
        parts += ["", "### Conventions of this run (mandatory)", *convention_lines]
    if known_lines:
        parts += ["", "### Already known (most relevant to your brief first)", *known_lines]
    return "\n".join(parts)


# ─── tools and setup ──────────────────────────────────────────────────────────────────
@tool(name="recall")
def recall_tool() -> Tool:
    async def execute(query: str) -> str:
        """Ask the shared run memory what other agents of this run already found.

        Returns the most relevant notes: exact outputs of earlier file inspections, files
        produced by earlier sub-agents, conventions, commands that work and known problems.

        Args:
            query: A question in natural language, e.g. "columns of the sample sheet".

        Returns:
            The most relevant memory items, or a note that nothing relevant is known.
        """
        value = _state()
        value["stats"]["recall_calls"] += 1
        _save(value)
        ranked, _ = await ranked_cards(query)
        lines, _ = _fit([(render_card(card), card) for card in ranked[:8]], RECALL_TOOL_CHARS)
        return "\n".join(lines) if lines else "Nothing relevant is in the run memory yet."

    return execute


@tool
def record_convention() -> Tool:
    async def execute(key: str, text: str) -> str:
        """Record a convention that several artifacts of this run must share.

        Every sub-agent started afterwards receives all conventions in its brief.

        Args:
            key: Short identifier, e.g. "gene_symbol_source".
            text: The convention in one or two sentences.

        Returns:
            Confirmation.
        """
        card = await remember("convention", key=key, text=text[:800], author="orchestrator",
                              title=f"convention: {key}")
        return f"convention '{key}' recorded" if card else "not recorded (empty or looks like a secret)"

    return execute


def run_identifier(state: TaskState) -> str:
    return os.environ.get("BIXBENCH3_RUN_ID") or f"{state.sample_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


@solver
def run_memory_setup(client_factory: Callable[[], PastDevClient | None] = _client) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate
        run = run_identifier(state)
        value = new_state(run=run, pastdev=False)
        client = client_factory()
        if client is None:
            value["pastdev_reason"] = f"{API_KEY_ENV} is not set: local fallback ranking only"
        else:
            try:
                await asyncio.to_thread(client.put_audience, value["audience"], [value["reader"]])
                value["pastdev"] = True
            except PastDevError as error:
                value["pastdev_reason"] = f"audience creation failed: {error}: local fallback ranking only"
        state.store.set(STORE_KEY, value)
        _append_log("memory_events.jsonl", {"event": "setup", "run": run, "audience": value["audience"],
                                            "pastdev": value["pastdev"], "reason": value["pastdev_reason"], "ts": _now()})
        state.user_prompt.text = state.user_prompt.text.rstrip() + "\n\n" + MEMORY_NOTE.strip() + "\n"
        return state

    return solve

"""Experiment t9-env-subagents-pastdev: shared run memory (no network in these tests)."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from inspect_ai.model import ChatMessageUser, ModelName
from inspect_ai.solver import TaskState
from inspect_ai.tool import tool

from bixbench3.inspect_harness import run_memory as memory
from bixbench3.inspect_harness.run_memory import (
    MEMORY_NOTE,
    PastDevClient,
    PastDevError,
    clean_output,
    inspection_paths,
    normalize_path,
    parse_learned,
    strip_learned,
)

REPO = Path(__file__).resolve().parents[2]
SECRET = "past_sk_" + "z" * 30


class _Store:
    def __init__(self) -> None:
        self.values: dict = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        self.values[key] = value


class _FakePastDev:
    """Records ingests; recall returns the ingested cards in an order chosen by the test."""

    def __init__(self, *, order: list[str] | None = None, fail_recall: bool = False) -> None:
        self.ingested: list[dict] = []
        self.order = order
        self.fail_recall = fail_recall
        self.queries: list[tuple[str, str]] = []
        self.audiences: list[tuple[str, list[str]]] = []

    def put_audience(self, slug, identities):
        self.audiences.append((slug, identities))
        return {}

    def ingest(self, card, audience):
        self.ingested.append({"card": card, "audience": audience})
        return {"ingestionId": f"ing-{len(self.ingested)}", "status": "queued"}

    def ingestion_status(self, ingestion_id):
        return "completed"

    def recall(self, query, *, identity, max_tokens=0, limit=0):
        if self.fail_recall:
            raise PastDevError("past.dev POST /recall failed: HTTP 503")
        self.queries.append((query, identity))
        ids = self.order if self.order is not None else [entry["card"]["id"] for entry in self.ingested]
        return [{"sources": [{"sourceId": card_id}]} for card_id in ids]


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    fake_store = _Store()
    client = _FakePastDev()
    monkeypatch.setattr(memory, "store", lambda: fake_store)
    monkeypatch.setattr(memory, "_client", lambda: client)
    monkeypatch.delenv("BIXBENCH3_BROKER_LOG_DIR", raising=False)
    fake_store.set(memory.STORE_KEY, memory.new_state(run="run-test", pastdev=True))
    return SimpleNamespace(store=fake_store, client=client, monkeypatch=monkeypatch)


def _state(env) -> dict:
    return env.store.get(memory.STORE_KEY)


# ─── capture rules ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(("command", "paths"), [
    ("head -5 /data/metadata/sample_sheet.tsv", ["/data/metadata/sample_sheet.tsv"]),
    ("zcat ./data/metadata/reference/gencode.v38.annotation.gtf.gz | head -3",
     ["/data/metadata/reference/gencode.v38.annotation.gtf.gz"]),
    ("cat /opt/task-env/MANIFEST.json", ["/opt/task-env/MANIFEST.json"]),
    ("import pandas as pd\nprint(pd.read_csv('/workspace/data/metadata/sample_gsm_mapping.tsv', sep='\\t').head())",
     ["/data/metadata/sample_gsm_mapping.tsv"]),
    ("wc -l /workspace/work/pipeline/artifacts/1_counts/matrix.tsv 2>/dev/null",
     ["/workspace/work/pipeline/artifacts/1_counts/matrix.tsv"]),
    ("ls /data/raw/PRJNA983731 | head", ["/data/raw/PRJNA983731"]),
    ("view /workspace/work/pipeline/plan.json", ["/workspace/work/pipeline/plan.json"]),
])
def test_read_only_inspections_are_captured_with_normalized_paths(command: str, paths: list[str]) -> None:
    assert inspection_paths(command) == paths


@pytest.mark.parametrize("command", [
    "head -5 /data/metadata/sample_sheet.tsv > /workspace/work/x.tsv",
    "cp /data/metadata/sample_sheet.tsv /workspace/work/",
    "hisat2 -p 4 -x idx -U /data/raw/PRJNA983731/SRR1.fastq.gz | samtools sort",
    "Rscript /workspace/work/pipeline/shared/analysis_driver.R",
    "df = pd.read_csv('/data/metadata/sample_sheet.tsv', sep='\\t'); df.to_csv('/workspace/work/x.csv')",
    "mkdir -p /workspace/work/pipeline/artifacts",
    "echo hello",
    "python3 /workspace/work/pipeline/run.py",
])
def test_writes_and_real_work_are_never_captured(command: str) -> None:
    assert inspection_paths(command) == []


def test_output_cleaning_and_path_normalization() -> None:
    raw = "root@sh03:/workspace# head -2 x\n> > > a\tb\nc\td\nroot@sh03:/workspace# "
    assert clean_output(raw) == "a\tb\nc\td"
    assert normalize_path("/workspace/data/raw/x.fastq.gz") == "/data/raw/x.fastq.gz"
    assert normalize_path("data/metadata/sample_sheet.tsv") == "/data/metadata/sample_sheet.tsv"


@tool(name="bash_session")
def _fake_bash():
    async def execute(action: str = "type_submit", input: str = "") -> str:
        """Fake shell.

        Args:
          action: Action.
          input: Input.
        """
        if "missing" in input:
            return "head: cannot open '/data/missing.tsv': No such file or directory"
        return f"root@node:/workspace# {input}\nrun\tsample\tcell_line\nSRR1\tT98G_Ctrl_rep1\tT98G\nroot@node:/workspace# "

    return execute


def test_wrapped_tool_is_transparent_and_captures(env) -> None:
    original = _fake_bash()
    wrapped = memory.with_capture(_fake_bash(), "subagent-3-artifact-x")

    async def scenario() -> tuple[str, str]:
        a = await original(input="head -2 /data/metadata/sample_sheet.tsv")
        b = await wrapped(input="head -2 /data/metadata/sample_sheet.tsv")
        await wrapped(input="head -2 /data/missing.tsv")  # error output: not captured
        await wrapped(action="read")  # not a command: not captured
        await memory.flush_ingestion()
        return a, b

    seen_by_original, seen_by_wrapped = asyncio.run(scenario())
    assert seen_by_wrapped == seen_by_original
    cards = list(_state(env)["cards"].values())
    assert [card["kind"] for card in cards] == ["observation"]
    assert cards[0]["paths"] == ["/data/metadata/sample_sheet.tsv"]
    assert cards[0]["text"].startswith("$ head -2 /data/metadata/sample_sheet.tsv\nrun\tsample\tcell_line")
    assert "root@node" not in cards[0]["text"]
    assert _state(env)["stats"]["inspected_by"] == {"/data/metadata/sample_sheet.tsv": ["subagent-3-artifact-x"]}
    assert env.client.ingested[0]["audience"] == _state(env)["audience"]


def test_wrapped_tool_receives_arguments_as_inspect_passes_them(env) -> None:
    """Regression: Inspect maps model arguments with tool_params(); the wrapper must accept them."""
    from inspect_ai.model._call_tools import tool_params

    wrapped = memory.with_capture(_fake_bash(), "orchestrator")
    model_arguments = {"input": "head -2 /data/metadata/sample_sheet.tsv"}
    params = tool_params(model_arguments, wrapped)
    assert params == model_arguments
    result = asyncio.run(wrapped(**params))
    assert "run\tsample\tcell_line" in result


def test_same_inspection_updates_one_card_and_counts_every_reader(env) -> None:
    async def scenario() -> None:
        for author in ("planner", "artifact-a", "artifact-b"):
            await memory.capture_call("bash_session", {"input": "head -2 /data/metadata/sample_sheet.tsv"},
                                      "a\tb\n1\t2", author)
        await memory.flush_ingestion()

    asyncio.run(scenario())
    value = _state(env)
    assert len(value["cards"]) == 1 and value["stats"]["cards_by_kind"] == {"observation": 1}
    assert value["stats"]["inspected_by"]["/data/metadata/sample_sheet.tsv"] == ["planner", "artifact-a", "artifact-b"]


def test_secrets_are_never_stored(env) -> None:
    assert asyncio.run(memory.remember("fact", "key", f"token {SECRET}", author="x")) is None
    assert _state(env)["cards"] == {} and env.client.ingested == []


# ─── lessons and files ────────────────────────────────────────────────────────────────
REPORT = """Built /workspace/work/pipeline/artifacts/2_c10/c10.csv (312 rows).
LEARNED: [{"kind": "convention", "key": "gene_symbol", "text": "gene_symbol comes from gene_name in the GENCODE v38 GTF."},
 {"kind": "how_to", "key": "deseq2", "text": "Rscript from /opt/task-env/bin has DESeq2 1.30.1."},
 {"kind": "weird", "key": "", "text": "Counts columns follow Counts_<line>_<clone>_rep<n>."}]"""


def test_learned_block_is_parsed_and_stripped_from_the_caller_report() -> None:
    items = parse_learned(REPORT)
    assert [item["kind"] for item in items] == ["convention", "how_to", "fact"]
    assert items[2]["key"].startswith("Counts columns")
    report, count = strip_learned(REPORT)
    assert count == 3 and "\"kind\"" not in report and report.endswith("[LEARNED: 3 item(s) saved to the run memory]")
    assert parse_learned("no block here") == [] and parse_learned("LEARNED: [not json") == []


def test_absorb_stores_lessons_and_produced_files(env) -> None:
    async def exec_(cmd, timeout=None):
        items = [{"path": "/workspace/work/pipeline/artifacts/2_c10/c10.csv", "bytes": 4096, "lines": 313,
                  "first_line": "gene_id,gene_symbol,base_mean"}]
        return SimpleNamespace(success=True, stdout=json.dumps(items))

    env.monkeypatch.setattr(memory, "sandbox", lambda: SimpleNamespace(exec=exec_))
    brief = "GOAL: x\nOUTPUT: /workspace/work/pipeline/artifacts/2_c10/ containing c10.csv"

    async def scenario() -> str:
        shortened = await memory.absorb_subagent(REPORT, brief, "subagent-3-artifact-c10")
        await memory.flush_ingestion()
        return shortened

    shortened = asyncio.run(scenario())
    kinds = sorted(card["kind"] for card in _state(env)["cards"].values())
    assert kinds == ["convention", "fact", "file", "how_to"]
    file_card = next(card for card in _state(env)["cards"].values() if card["kind"] == "file")
    assert "313 lines" in file_card["text"] and "gene_id,gene_symbol,base_mean" in file_card["text"]
    assert "[LEARNED: 3 item(s)" in shortened


# ─── the librarian ────────────────────────────────────────────────────────────────────
def _seed(env) -> dict[str, str]:
    async def scenario() -> dict[str, str]:
        conv = await memory.remember("convention", "ids", "gene_id without version suffix", author="orchestrator")
        obs = await memory.remember("observation", "head sample sheet", "$ head ...\nrun\tsample", author="planner",
                                    paths=["/data/metadata/sample_sheet.tsv"])
        gtf = await memory.remember("observation", "zcat gtf", "$ zcat ...\nchr1 HAVANA gene", author="planner",
                                    paths=["/data/metadata/reference/gencode.v38.annotation.gtf.gz"])
        await memory.flush_ingestion()
        return {"conv": conv["id"], "obs": obs["id"], "gtf": gtf["id"]}

    return asyncio.run(scenario())


def test_pack_always_has_all_conventions_and_follows_pastdev_ranking(env) -> None:
    ids = _seed(env)
    env.client.order = [ids["gtf"], ids["obs"]]  # the librarian ranks the GTF first and never returns the convention
    pack = asyncio.run(memory.build_pack("GOAL: DESeq2 C10 vs control", "subagent-3"))
    assert "### Conventions of this run (mandatory)" in pack and "gene_id without version suffix" in pack
    assert pack.index("chr1 HAVANA gene") < pack.index("run\tsample")
    query, identity = env.client.queries[-1]
    assert query.startswith("GOAL: DESeq2 C10") and identity == _state(env)["reader"]
    assert _state(env)["stats"]["packs"][-1]["ranking"] == "pastdev"


def test_pack_respects_its_budget(env) -> None:
    async def scenario() -> None:
        for index in range(40):
            await memory.remember("observation", f"cmd {index}", "x" * 900, author="planner")
        await memory.flush_ingestion()

    asyncio.run(scenario())
    pack = asyncio.run(memory.build_pack("anything", "subagent-9"))
    assert len(pack) <= memory.PACK_CHARS + memory.CONVENTIONS_CHARS + 400


def test_local_fallback_when_pastdev_fails(env) -> None:
    _seed(env)
    env.client.fail_recall = True
    pack = asyncio.run(memory.build_pack("needs /data/metadata/sample_sheet.tsv", "subagent-4"))
    assert "gene_id without version suffix" in pack and "run\tsample" in pack
    assert _state(env)["stats"]["ranking_fallbacks"] == 1 and _state(env)["stats"]["pastdev_errors"] >= 1


def test_recall_tool_and_record_convention(env) -> None:
    _seed(env)
    answer = asyncio.run(memory.recall_tool()(query="sample sheet columns"))
    assert "run\tsample" in answer and _state(env)["stats"]["recall_calls"] == 1
    confirmation = asyncio.run(memory.record_convention()(key="symbols", text="from GTF gene_name"))
    assert confirmation == "convention 'symbols' recorded"
    pack = asyncio.run(memory.build_pack("anything", "subagent-5"))
    assert "from GTF gene_name" in pack


# ─── setup and client ─────────────────────────────────────────────────────────────────
def _task_state() -> TaskState:
    return TaskState(model=ModelName("mockllm/model"), sample_id="t9", epoch=1, input="p",
                     messages=[ChatMessageUser(content="# Analysis Task\n")])


def test_setup_scopes_memory_to_this_run_and_appends_the_note() -> None:
    client = _FakePastDev()
    state = asyncio.run(memory.run_memory_setup(lambda: client)(_task_state(), None))
    value = state.store.get(memory.STORE_KEY)
    assert value["pastdev"] is True and client.audiences == [(value["audience"], [value["reader"]])]
    assert state.user_prompt.text.endswith(MEMORY_NOTE.strip() + "\n")
    other = asyncio.run(memory.run_memory_setup(lambda: client)(_task_state(), None)).store.get(memory.STORE_KEY)
    assert other["audience"] != value["audience"]  # two runs never share an audience


def test_setup_without_key_continues_with_local_fallback() -> None:
    state = asyncio.run(memory.run_memory_setup(lambda: None)(_task_state(), None))
    value = state.store.get(memory.STORE_KEY)
    assert value["pastdev"] is False and "not set" in value["pastdev_reason"]


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *arguments) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_client_requests_follow_the_documented_api_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.time, "sleep", lambda seconds: None)
    sent: list = []
    failures = iter([True, False])

    def opener(request, timeout):
        sent.append(request)
        if request.full_url.endswith("/recall") and next(failures):
            raise HTTPError(request.full_url, 503, "busy", None, io.BytesIO(b""))
        return _Response(b'{"ingestionId": "i1", "status": "queued", "results": []}')

    client = PastDevClient(SECRET, opener=opener)
    card = memory.make_card(run="r", kind="fact", key="k", title="t", text="hello", author="a", paths=["/data/x"])
    client.ingest(card, "bb3-aud")
    body = json.loads(sent[0].data)
    assert sent[0].full_url == "https://api.past.dev/api/v1/ingest" and body["audience"] == "bb3-aud"
    assert body["id"] == card["id"] and body["metadata"]["paths"] == ["/data/x"]
    assert sent[0].get_header("Authorization") == f"Bearer {SECRET}"
    assert client.recall("q", identity="reader") == []
    assert json.loads(sent[-1].data)["identity"] == "reader" and len(sent) == 3


def test_client_errors_never_contain_the_key() -> None:
    def opener(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", None, io.BytesIO(b""))

    with pytest.raises(PastDevError) as failure:
        PastDevClient(SECRET, opener=opener).recall("q", identity="r")
    assert "HTTP 401" in str(failure.value) and SECRET not in str(failure.value)


def test_wiring_redaction_and_sherlock_secret() -> None:
    harness = REPO / "src/bixbench3/inspect_harness"
    assert "run_memory_setup()" in (harness / "tasks.py").read_text()
    solvers = (harness / "solvers.py").read_text()
    assert "record_convention()" in solvers and "recall_tool()" in solvers and solvers.count("with_capture(") == 3
    subagent = (harness / "tools/subagent.py").read_text()
    assert "build_pack(brief, name)" in subagent and "absorb_subagent(report, brief, name)" in subagent
    assert 'past_[sm]k_[A-Za-z0-9_-]+' in (REPO / "src/bixbench3/gcp_runner.py").read_text()
    assert "/^PAST_API_KEY=/p" in (REPO / "sherlock/run_job.sbatch").read_text()


def test_parallel_subagents_share_one_memory_without_losing_cards(env) -> None:
    """v5 runs one dependency level in parallel: concurrent captures and packs must not lose cards."""

    async def agent(name: str, path: str) -> str:
        await memory.capture_call("bash_session", {"input": f"head -3 {path}"}, f"col_a\tcol_b\nrow of {name}", name)
        await memory.remember("how_to", f"tip-{name}", f"{name} found a working command", author=name)
        return await memory.build_pack(f"GOAL: artifact {name}, reads {path}", name)

    async def scenario() -> list[str]:
        paths = [f"/workspace/work/pipeline/artifacts/1_counts/part{index}.tsv" for index in range(6)]
        return await asyncio.gather(*(agent(f"subagent-{index}", path) for index, path in enumerate(paths)))

    packs = asyncio.run(scenario())
    value = _state(env)
    assert value["stats"]["cards_by_kind"] == {"observation": 6, "how_to": 6}
    assert len(value["cards"]) == 12 and len(value["stats"]["packs"]) == 6
    assert all(pack.startswith("## Shared run memory") for pack in packs)
def test_recall_query_respects_pastdev_limit() -> None:
    """past.dev rejects recall queries over 1,000 characters (HTTP 400 recall-query-too-long)."""
    import io
    import json as _json

    sent = {}

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=None):
        sent.update(_json.loads(request.data))
        return _Response(b'{"results": []}')

    client = memory.PastDevClient("past_sk_test", opener=opener)
    client.recall("x" * 5000, identity="reader")
    assert len(sent["query"]) == memory.RECALL_QUERY_MAX == 1000

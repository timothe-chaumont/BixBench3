#!/usr/bin/env python3
"""bixdash collector — read-only snapshot of one BixBench3 run on its VM.

Runs as root from a systemd timer (see install_collector.sh). It NEVER writes
inside the run directory (/var/lib/bixbench3), never touches the service or the
sandbox. Everything it produces lives in /var/lib/bixdash and in the
`_dashboard/<run_id>/` prefix of the results bucket.

Per run it publishes:
  meta.json      — who/what/why (incl. the one-line RUN_DESCRIPTION)
  latest.json    — newest snapshot, with per-artifact detail
  history.jsonl  — one compact line per snapshot (score/cost/tokens vs time)

Partial grading copies the agent outputs to a private dir, downloads the
ground truth into a 0700 temp dir on the HOST (never mounted in the sandbox),
grades with the official grader, then deletes the ground truth — exactly what
run.sh does at the end of a run.

Python stdlib only; grading shells out to the harness venv via `uv`.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

RUN_ROOT = Path(os.environ.get("BIXDASH_RUN_ROOT", "/var/lib/bixbench3"))
HARNESS = Path(os.environ.get("BIXDASH_HARNESS", "/opt/bixbench3"))
STATE = Path(os.environ.get("BIXDASH_STATE", "/var/lib/bixdash"))
BUFFER_GLOB = os.environ.get(
    "BIXDASH_BUFFER_GLOB", "/root/.local/share/inspect_ai/samplebuffer/*/*.db"
)
TIME_LIMIT_S = 86_400  # harness default (inspect_harness/dataset.py)

# USD per 1M tokens. Edit /var/lib/bixdash/prices.json to override.
DEFAULT_PRICES = {
    "openai/gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
    "openai/gpt-5.5": {"input": 5.00, "cached": 0.50, "output": 30.00},
}

SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"AIza[A-Za-z0-9_-]{10,}"), "<redacted>"),
    (re.compile(r"(?i)((?:api_?key|token|secret|password)\s*[=:]\s*)\S+"), r"\1<redacted>"),
]


def redact(text: str) -> str:
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- run config
def parse_run_sh() -> dict:
    """Extract model / effort / sample / grader / upload prefix from run.sh."""
    text = (RUN_ROOT / "run.sh").read_text(encoding="utf-8", errors="replace")
    out: dict = {}
    if m := re.search(r"^#\s*RUN_DESCRIPTION:\s*(.+)$", text, re.M):
        out["description"] = m.group(1).strip()
    if m := re.search(r"--model\s+(\S+)", text):
        out["model"] = m.group(1)
    if m := re.search(r"--reasoning-effort\s+(\S+)", text):
        out["effort"] = m.group(1)
    if m := re.search(r"--sample-id\s+(\S+)", text):
        out["paper_id"] = m.group(1)
    if m := re.search(
        r"uv run python - (\d+) (\S+) (https://storage\.googleapis\.com/bixbench3-ground-truth/\S+\.json) ([0-9a-f]{64})",
        text,
    ):
        out["task_id"], _, out["grader_url"], out["grader_sha256"] = m.groups()
    if m := re.search(r"(gs://[^\s/]+)/(\S+?)/?\s", text[text.find("gcloud storage cp"):] if "gcloud storage cp" in text else ""):
        out["results_bucket"] = m.group(1)
        out["results_prefix"] = f"{m.group(1)}/{m.group(2).rstrip('/')}/"
        out["run_id"] = m.group(2).rstrip("/").replace("/", "__")
    return out


def gcp_project_id() -> str | None:
    """Project of this VM, from the GCE metadata server (no credentials needed)."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.read().decode().strip() or None
    except Exception:
        return None


def dashboard_uri(cfg: dict, meta: dict) -> str | None:
    """Where snapshots go. Priority: env BIXDASH_DASHBOARD_URI, run_meta.json
    "dashboard_uri" (central bucket shared by the team), else <results bucket>/_dashboard."""
    uri = os.environ.get("BIXDASH_DASHBOARD_URI") or meta.get("dashboard_uri")
    if not uri and cfg.get("results_bucket"):
        uri = f"{cfg['results_bucket']}/_dashboard"
    return uri.rstrip("/") if uri else None


def load_meta(cfg: dict) -> dict:
    """meta = run.sh facts, overridden by /var/lib/bixdash/run_meta.json."""
    override = read_json(STATE / "run_meta.json")
    meta = {
        "run_id": cfg.get("run_id") or os.uname().nodename,
        "task_id": cfg.get("task_id"),
        "paper_id": cfg.get("paper_id"),
        "model": cfg.get("model"),
        "effort": cfg.get("effort"),
        "condition": "baseline",
        "description": cfg.get("description", ""),
        "baseline_run_id": None,
        "vm": os.uname().nodename,
        "owner": None,
        "gcp_project": gcp_project_id(),
        "results_prefix": cfg.get("results_prefix"),
        "time_limit_s": TIME_LIMIT_S,
        "deadline": os.environ.get("BIXDASH_DEADLINE", "2026-11-15T22:00:00+00:00"),
    }
    meta.update({k: v for k, v in override.items() if v not in (None, "")})
    return meta


def started_at() -> float | None:
    """Service start time (systemd), else first inspect log mtime."""
    try:
        out = subprocess.run(
            ["systemctl", "show", "bixbench3-run", "-p", "ActiveEnterTimestamp", "--value"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if out and out != "n/a":
            out = subprocess.run(
                ["date", "-d", out, "+%s"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
            return float(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    logs = sorted((RUN_ROOT / "inspect_logs").glob("*.eval"), key=lambda p: p.stat().st_mtime)
    return logs[0].stat().st_mtime if logs else None


# ------------------------------------------------------- inspect sample buffer
def buffer_stats(prices: dict, t0: float | None = None) -> dict:
    """Tokens, cost and latest activity from Inspect's live sample buffer.

    Opened read-only (sqlite URI mode=ro). Events can be re-logged while
    pending, so we keep the last row per event_id.
    """
    dbs = sorted(glob.glob(BUFFER_GLOB), key=os.path.getmtime)
    if not dbs:
        return {"available": False}
    db = dbs[-1]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        rows = conn.execute(
            """
            SELECT e.event_id,
                   json_extract(e.data,'$.event'),
                   json_extract(e.data,'$.timestamp'),
                   json_extract(e.data,'$.model'),
                   json_extract(e.data,'$.output.usage'),
                   json_extract(e.data,'$.function'),
                   json_extract(e.data,'$.arguments'),
                   json_extract(e.data,'$.output.choices[0].message.content'),
                   json_extract(e.data,'$.pending'),
                   json_extract(e.data,'$.span_id'),
                   json_extract(e.data,'$.role')
            FROM events e
            JOIN (SELECT event_id, MAX(id) AS id FROM events GROUP BY event_id) last
              ON last.id = e.id
            WHERE json_extract(e.data,'$.event') IN ('model','tool')
            ORDER BY e.id
            """
        ).fetchall()
        span_rows = conn.execute(
            """
            SELECT json_extract(data,'$.id'), json_extract(data,'$.parent_id'),
                   json_extract(data,'$.type'), json_extract(data,'$.name')
            FROM events WHERE json_extract(data,'$.event') = 'span_begin'
            """
        ).fetchall()
    finally:
        conn.close()

    tok = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    cost = 0.0
    n_model = n_tool = 0
    last_ts = None
    last_tool = None
    last_text = None
    model_seen = None
    spans = {sid: {"parent_id": pid, "type": typ, "name": name} for sid, pid, typ, name in span_rows if sid}
    calls: list[tuple] = []
    for _eid, kind, ts, model, usage, fn, args, content, pending, span_id, role in rows:
        last_ts = ts or last_ts
        if kind == "model":
            if pending:
                continue
            n_model += 1
            model_seen = model or model_seen
            u = json.loads(usage) if usage else {}
            inp = u.get("input_tokens") or 0
            cached = u.get("input_tokens_cache_read") or 0
            out = u.get("output_tokens") or 0
            tok["input"] += inp
            tok["cached"] += cached
            tok["output"] += out
            tok["reasoning"] += u.get("reasoning_tokens") or 0
            p = prices.get(model or "", prices.get(f"openai/{model}", {}))
            c = (inp * p["input"] + cached * p.get("cached", p["input"]) + out * p["output"]) / 1e6 if p else 0.0
            cost += c
            t_call = parse_iso(ts)
            if t_call:
                calls.append((t_call, agent_of(span_id, role, spans), inp + cached + out, c))
            text = _content_text(content)
            if text:
                last_text = {"ts": ts, "text": redact(text[-600:])}
        elif kind == "tool":
            n_tool += 1
            a = json.loads(args) if args else {}
            cmd = a.get("cmd") or a.get("command") or a.get("code") or json.dumps(a)[:400]
            last_tool = {"ts": ts, "function": fn, "args": redact(str(cmd)[:400])}
    return {
        "available": True,
        **agents_summary(calls, t0, time.time()),
        "tokens": tok,
        "cost_usd": round(cost, 4) if cost else (0.0 if n_model == 0 else None),
        "n_model_calls": n_model,
        "n_tool_calls": n_tool,
        "last_event_ts": last_ts,
        "last_tool": last_tool,
        "last_message": last_text,
    }


def agent_of(span_id, role, spans: dict) -> str:
    """Name of the nearest enclosing Inspect span of type 'agent' (set by
    inspect_ai agent(), as_tool, handoff, run); fallback to the model role."""
    seen = 0
    while span_id and span_id in spans and seen < 50:
        sp = spans[span_id]
        if sp.get("type") == "agent":
            return sp.get("name") or "agent"
        span_id = sp.get("parent_id")
        seen += 1
    return role or "main"


def agents_summary(calls: list[tuple], t0: float | None, now: float, step: int = 300) -> dict:
    """calls: (t, agent, tokens, cost). Returns per-agent table + active-agents timeline."""
    table: dict[str, dict] = {}
    for t, agent, tok, cost in calls:
        row = table.setdefault(agent, {"agent": agent, "calls": 0, "tokens": 0, "cost_usd": 0.0, "first_ts": t, "last_ts": t})
        row["calls"] += 1
        row["tokens"] += tok
        row["cost_usd"] += cost
        row["last_ts"] = max(row["last_ts"], t)
        row["first_ts"] = min(row["first_ts"], t)
    timeline = []
    t0 = t0 or (min(c[0] for c in calls) if calls else None)
    if t0 and calls:
        end = max(now, max(c[0] for c in calls))
        bins: dict[int, set] = {}
        for t, agent, _tok, _cost in calls:
            bins.setdefault(int((t - t0) // step), set()).add(agent)
        for b in range(0, int((end - t0) // step) + 1):
            timeline.append({"elapsed_s": b * step, "n_agents": len(bins.get(b, ()))})
    for row in table.values():
        row["cost_usd"] = round(row["cost_usd"], 4)
        row["first_ts"] = datetime.fromtimestamp(row["first_ts"], UTC).isoformat(timespec="seconds")
        row["last_ts"] = datetime.fromtimestamp(row["last_ts"], UTC).isoformat(timespec="seconds")
    return {"agents": sorted(table.values(), key=lambda r: -r["calls"]), "agent_timeline": timeline}


def clean_details(details: dict | None) -> dict:
    """Keep only counts/ratios and column-name lists from grader check details."""
    out = {}
    for k, v in (details or {}).items():
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str) and len(v) < 40:
            out[k] = v
        elif isinstance(v, list) and len(v) <= 30 and all(isinstance(x, str) for x in v):
            out[k] = v
    return out


def _content_text(content: str | None) -> str:
    if not content:
        return ""
    try:
        parsed = json.loads(content)
    except ValueError:
        return content
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, list):
        return "\n".join(
            part.get("text", "") for part in parsed if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


# ------------------------------------------------------------ outputs/progress
def expected_outputs() -> list[dict]:
    case = read_json(RUN_ROOT / "dataset" / "case.json")
    return [
        {"artifact_id": o.get("artifact_id"), "path": o.get("path")}
        for o in case.get("expected_outputs", [])
    ]


def outputs_dir() -> Path:
    return RUN_ROOT / "outputs"


def artifact_presence(expected: list[dict]) -> list[dict]:
    out = []
    for item in expected:
        rel = (item["path"] or "").removeprefix("outputs/")
        p = outputs_dir() / rel
        st = p.stat() if p.exists() else None
        out.append({
            **item,
            "present": bool(st),
            "bytes": st.st_size if st else 0,
            "mtime": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds") if st else None,
        })
    return out


def work_dir() -> Path | None:
    for cand in (RUN_ROOT / "workspace" / "work", RUN_ROOT / "workspace"):
        if cand.is_dir():
            return cand
    return None


def task_progress(meta: dict) -> dict:
    """Task-specific counters. Configure in run_meta.json:
    "progress": {"label": "Tempo-seq samples counted", "glob": "counts/*", "total": 85}
    """
    spec = meta.get("progress")
    wd = work_dir()
    if not spec or not wd:
        return {}
    n = len([p for p in wd.glob(spec["glob"]) if p.is_file()])
    return {"label": spec.get("label", spec["glob"]), "done": n, "total": spec.get("total")}


def last_file_activity() -> float | None:
    newest = None
    for base in (work_dir(), outputs_dir()):
        if not base:
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                try:
                    m = os.path.getmtime(os.path.join(root, f))
                except OSError:
                    continue
                newest = m if newest is None or m > newest else newest
    return newest


def resources() -> dict:
    try:
        load1 = os.getloadavg()[0]
    except OSError:
        load1 = None
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) / 1024 / 1024
    except OSError:
        pass
    du = shutil.disk_usage("/")
    return {
        "load1": load1,
        "ncpu": os.cpu_count(),
        "mem_used_gb": round(mem.get("MemTotal", 0) - mem.get("MemAvailable", 0), 1) if mem else None,
        "mem_total_gb": round(mem.get("MemTotal", 0), 1) if mem else None,
        "disk_used_gb": round(du.used / 1e9, 1),
        "disk_total_gb": round(du.total / 1e9, 1),
    }


# ------------------------------------------------------------- partial grading
GRADE_SNIPPET = r"""
import json, sys
from pathlib import Path
from bixbench3.gcp_runner import TaskSpec, grade_existing_artifacts
task_id, paper_id, url, sha, art, grades, gt = sys.argv[1:]
task = TaskSpec(task_id=task_id, paper_id=paper_id, input_manifest_uri="host-grading-only",
                input_manifest_sha256="0"*64, input_size_bytes=0,
                grader_manifest_url=url, grader_manifest_sha256=sha)
g = grade_existing_artifacts(task=task, artifacts_dir=Path(art), grades_dir=Path(grades),
                             ground_truth_parent=Path(gt))
print(json.dumps(g))
"""


def _uv() -> str:
    for cand in (shutil.which("uv"), "/usr/local/bin/uv", "/root/.local/bin/uv", "/root/.cargo/bin/uv"):
        if cand and os.path.exists(cand):
            return cand
    return "uv"


def partial_grade(cfg: dict) -> dict | None:
    if not cfg.get("grader_url"):
        return None
    snap = STATE / "grading" / "current"
    if snap.exists():
        shutil.rmtree(snap)
    art = snap / "agent_artifacts"
    art.mkdir(parents=True)
    # copy the agent outputs (read-only source); copy, never move
    if outputs_dir().is_dir():
        shutil.copytree(outputs_dir(), art, dirs_exist_ok=True)
    gt = STATE / "gt"
    gt.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(gt, 0o700)
    proc = subprocess.run(
        ["nice", "-n", "19", _uv(), "run", "--project", str(HARNESS), "python", "-c", GRADE_SNIPPET,
         cfg["task_id"], cfg["paper_id"], cfg["grader_url"], cfg["grader_sha256"],
         str(art), str(snap / "artifact_grades"), str(gt)],
        capture_output=True, text=True, timeout=900, cwd=str(HARNESS),
    )
    if proc.returncode != 0:
        return {"error": redact(proc.stderr[-800:])}
    try:
        grade = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "unparseable grader output"}
    return {
        "score": grade.get("score"),
        "artifacts": {
            a["artifact_id"]: {
                "score": a.get("score"),
                "checks": [
                    {"metric": c.get("metric"), "axis": c.get("axis"), "score": c.get("score"),
                     "details": clean_details(c.get("details"))}
                    for c in a.get("checks", [])
                ],
                "reason": a.get("reason"),
            }
            for a in grade.get("artifacts", [])
        },
    }


# --------------------------------------------------------------------- ETA
def estimate_eta(elapsed: float, present: int, total: int, progress: dict, history: list[dict]) -> dict:
    """Very rough: extrapolate the artifact completion rate; during a counted
    phase use the task counter rate. Always bounded by the time limit."""
    limit_left = max(0.0, TIME_LIMIT_S - elapsed)
    est = None
    method = None
    if progress.get("total") and progress.get("done") and progress["done"] < progress["total"]:
        pts = [(h["elapsed_s"], h.get("progress_done")) for h in history if h.get("progress_done")]
        if len(pts) >= 2 and pts[-1][1] > pts[0][1]:
            rate = (pts[-1][1] - pts[0][1]) / max(1.0, pts[-1][0] - pts[0][0])
            est = (progress["total"] - progress["done"]) / rate
            method = f"{progress['label']} rate (phase only)"
    if est is None and total and present and elapsed >= 1800:
        est = elapsed * (total - present) / present
        method = "artifact completion rate"
    if est is not None:
        est = min(est, limit_left)
    return {"remaining_s": round(est) if est is not None else None, "method": method, "time_limit_left_s": round(limit_left)}


# -------------------------------------------------------------------- upload
def gs_put_many(paths: list[Path], dest_prefix: str) -> dict:
    """Upload files in ONE gcloud call; return a status record (kept locally and printed)."""
    try:
        proc = subprocess.run(
            ["gcloud", "storage", "cp", "--quiet", *[str(p) for p in paths], dest_prefix],
            capture_output=True, text=True, timeout=180,
        )
        ok = proc.returncode == 0
        err = None if ok else redact(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "upload failed")
    except (OSError, subprocess.SubprocessError) as error:
        ok, err = False, str(error)[:300]
    return {"ts": now_iso(), "dest": dest_prefix, "ok": ok, "error": err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade", action="store_true", help="force partial grading now")
    ap.add_argument("--grade-every", type=int, default=900, help="seconds between partial gradings (0=never)")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    STATE.mkdir(parents=True, exist_ok=True)
    cfg = parse_run_sh()
    meta = load_meta(cfg)
    prices = {**DEFAULT_PRICES, **read_json(STATE / "prices.json")}

    t0 = started_at()
    meta["started_at"] = datetime.fromtimestamp(t0, UTC).isoformat(timespec="seconds") if t0 else None
    status = read_json(RUN_ROOT / "status.json")
    now = time.time()
    finished = status.get("status") in ("succeeded", "failed")
    end_t = parse_iso(status.get("updated_at")) if finished else now
    elapsed = (end_t or now) - t0 if t0 else 0.0

    hist_path = STATE / "history.jsonl"
    history = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()] if hist_path.exists() else []

    buf = {}
    try:
        buf = buffer_stats(prices, t0)
    except Exception as error:  # never let a stats bug break the snapshot
        buf = {"available": False, "error": str(error)[:300]}

    expected = expected_outputs()
    arts = artifact_presence(expected)
    progress = task_progress(meta)

    grade = None
    final_grade = read_json(RUN_ROOT / "grade.json")
    if final_grade.get("score") is not None:
        grade = {"score": final_grade["score"], "final": True, "artifacts": {
            a["artifact_id"]: {"score": a.get("score"), "checks": [
                {"metric": c.get("metric"), "axis": c.get("axis"), "score": c.get("score"),
                 "details": clean_details(c.get("details"))} for c in a.get("checks", [])]}
            for a in final_grade.get("artifacts", [])}}
    else:
        stamp = STATE / "last_grade_ts"
        last = float(stamp.read_text()) if stamp.exists() else 0.0
        due = args.grade or (args.grade_every > 0 and now - last >= args.grade_every)
        if due and any(a["present"] for a in arts):
            stamp.write_text(str(now))
            try:
                grade = partial_grade(cfg)
            except Exception as error:
                grade = {"error": str(error)[:300]}
    if grade is None and history:  # carry forward last partial score between gradings
        prev = read_json(STATE / "latest.json").get("grade")
        if prev and not prev.get("error"):
            grade = {**prev, "carried": True}

    for a in arts:
        g = (grade or {}).get("artifacts", {}).get(a["artifact_id"])
        a["score"] = g.get("score") if g else None
        a["checks"] = g.get("checks") if g else None

    present = sum(a["present"] for a in arts)
    last_act = last_file_activity()
    last_evt = parse_iso(buf.get("last_event_ts")) if buf.get("available") else None
    eta = estimate_eta(elapsed, present, len(arts), progress, history)

    snap = {
        "ts": now_iso(),
        "elapsed_s": round(elapsed),
        "phase": status.get("phase"),
        "status": status.get("status"),
        "artifacts_present": present,
        "artifacts_total": len(arts),
        "partial_score": (grade or {}).get("score"),
        "score_is_final": bool((grade or {}).get("final")),
        "grade_error": (grade or {}).get("error"),
        "cost_usd": buf.get("cost_usd"),
        "tokens": buf.get("tokens"),
        "n_model_calls": buf.get("n_model_calls"),
        "n_tool_calls": buf.get("n_tool_calls"),
        "last_tool": buf.get("last_tool"),
        "last_message": buf.get("last_message"),
        "idle_s": round(now - max(x for x in (last_act, last_evt, t0, 0) if x is not None)),
        "progress": progress,
        "agents": buf.get("agents"),
        "agent_timeline": buf.get("agent_timeline"),
        "eta": eta,
        "resources": resources(),
        "artifacts": arts,
    }
    compact = {k: snap[k] for k in ("ts", "elapsed_s", "phase", "artifacts_present", "partial_score", "cost_usd", "n_model_calls", "n_tool_calls")}
    compact["tokens_total"] = sum((buf.get("tokens") or {}).get(k, 0) for k in ("input", "cached", "output"))
    compact["progress_done"] = progress.get("done")
    tl = buf.get("agent_timeline") or []
    compact["n_agents"] = tl[-1]["n_agents"] if tl else None
    with hist_path.open("a") as f:
        f.write(json.dumps(compact) + "\n")
    snap["grade"] = grade

    (STATE / "meta.json").write_text(json.dumps(meta, indent=2))
    (STATE / "latest.json").write_text(json.dumps(snap, indent=2))

    upload = None
    target = dashboard_uri(cfg, meta)
    if not args.no_upload and target:
        upload = gs_put_many([STATE / n for n in ("meta.json", "latest.json", "history.jsonl")],
                             f"{target}/{meta['run_id']}/")
        (STATE / "upload_status.json").write_text(json.dumps(upload, indent=2))
    summary = {k: snap[k] for k in ("ts", "elapsed_s", "phase", "artifacts_present", "partial_score", "cost_usd", "idle_s")}
    if upload:
        summary["upload"] = "ok" if upload["ok"] else f"FAILED: {upload['error']}"
        summary["dashboard"] = upload["dest"]
    print(json.dumps(summary))
    return 0 if (upload is None or upload["ok"]) else 3


if __name__ == "__main__":
    sys.exit(main())

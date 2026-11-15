#!/usr/bin/env python3
"""Import a FINISHED BixBench3 run into the dashboard (no collector needed).

Reads the run's results folder (read-only):
  grade.json, judge.json, run_manifest.json, inspect_logs/*.eval
and writes  <dashboard prefix>/<run_id>/{meta,latest,history}.json[l].

History is rebuilt from the Inspect .eval trace: cumulative cost, tokens,
model/tool calls vs elapsed time (one point per 5 min). Only the FINAL score
is known (no partial grading ran), so the score curve is a single end point.

Usage (Mac, after `gcloud auth application-default login`):
  python3 tools/import_finished_run.py \
    gs://bixbench3-task11-jex20-results/10.1016_j.crtox.2021.01.003_v1/openai-gpt-5-4-mini/20261114T220820106596Z \
    --description "Baseline : harness Inspect d'origine, GPT-5.4 mini xhigh, n2-standard-8 sans Cell Ranger" \
    --condition baseline
Add --out-dir ./demo_data to write locally instead of to the bucket.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vm"))
from collect import agent_of, agents_summary, clean_details  # noqa: E402

PRICES = {  # USD per 1M tokens
    "openai/gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
    "gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
}
STEP_S = 300


def ts(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def cost_of(model: str, usage: dict) -> float:
    p = PRICES.get(model) or PRICES.get(model.split("/")[-1]) or {}
    if not p:
        return 0.0
    return (
        (usage.get("input_tokens") or 0) * p["input"]
        + (usage.get("input_tokens_cache_read") or 0) * p["cached"]
        + (usage.get("output_tokens") or 0) * p["output"]
    ) / 1e6


class GCS:
    def __init__(self, uri: str):
        from google.cloud import storage

        bucket, _, prefix = uri[5:].partition("/")
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket)
        self.bucket_name = bucket
        self.prefix = prefix.rstrip("/") + "/"

    def read(self, rel: str) -> bytes | None:
        blob = self.bucket.blob(self.prefix + rel)
        return blob.download_as_bytes() if blob.exists() else None

    def list(self, rel: str) -> list[str]:
        return [b.name[len(self.prefix):] for b in self.bucket.list_blobs(prefix=self.prefix + rel)]


class Local:
    """Same interface as GCS, for testing against a local copy of a results folder."""
    def __init__(self, path: str):
        self.root = Path(path)
        parts = self.root.resolve().parts
        self.prefix = "/".join(parts[-3:]) + "/"
        self.bucket_name = None
        self.client = None

    def read(self, rel: str) -> bytes | None:
        p = self.root / rel
        return p.read_bytes() if p.exists() else None

    def list(self, rel: str) -> list[str]:
        base = self.root / rel
        return [str(p.relative_to(self.root)) for p in base.glob("*")] if base.is_dir() else []


def _read_member(z: zipfile.ZipFile, raw: bytes, name: str) -> bytes:
    """Read a zip member; Inspect writes zstd (method 93), which zipfile only
    supports from Python 3.14 — fall back to the `zstandard` package."""
    try:
        return z.read(name)
    except NotImplementedError:
        info = z.getinfo(name)
        if info.compress_type != 93:
            raise
        try:
            import zstandard
        except ImportError:
            raise SystemExit("Ce .eval est compressé en zstd : pip install zstandard")
        off = info.header_offset
        fname_len = int.from_bytes(raw[off + 26:off + 28], "little")
        extra_len = int.from_bytes(raw[off + 28:off + 30], "little")
        start = off + 30 + fname_len + extra_len
        data = raw[start:start + info.compress_size]
        return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)).read()


def load_eval(raw: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = [n for n in z.namelist() if n.startswith("samples/") and n.endswith(".json")]
    if not names:
        raise SystemExit("no sample in the .eval file")
    return json.loads(_read_member(z, raw, names[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_uri", help="gs://…/<paper_id>/<model>/<timestamp>")
    ap.add_argument("--description", required=True)
    ap.add_argument("--condition", default="baseline")
    ap.add_argument("--task-id", default="11")
    ap.add_argument("--owner", default=None, help="team member who ran it")
    ap.add_argument("--gcp-project", default=None, help="GCP project the run used")
    ap.add_argument("--dashboard-prefix", default=None, help="default: gs://<bucket>/_dashboard")
    ap.add_argument("--out-dir", default=None, help="write locally instead of to GCS")
    ap.add_argument("--run-id", default=None, help="override run_id (default: <paper_id>__<model>__<timestamp>)")
    args = ap.parse_args()

    src = GCS(args.results_uri) if args.results_uri.startswith("gs://") else Local(args.results_uri)
    rel_path = src.prefix.rstrip("/")
    run_id = args.run_id or rel_path.replace("/", "__")
    parts = rel_path.split("/")
    paper_id = parts[0] if len(parts) >= 3 else None
    model_slug = parts[1] if len(parts) >= 3 else None

    grade = json.loads(src.read("grade.json") or b"{}")
    judge = json.loads(src.read("judge.json") or b"{}")
    manifest = json.loads(src.read("run_manifest.json") or b"{}")
    evals = [n for n in src.list("inspect_logs/") if n.endswith(".eval")] or [n for n in src.list("") if n.endswith(".eval")]
    if not evals:
        raise SystemExit("no inspect_logs/*.eval in the results folder")
    sample = load_eval(src.read(sorted(evals)[-1]))

    t0 = ts(sample.get("started_at")) or min(ts(e.get("timestamp")) for e in sample["events"] if e.get("timestamp"))
    t_end = ts(sample.get("completed_at")) or max(ts(e.get("timestamp")) for e in sample["events"] if e.get("timestamp"))

    # ---- rebuild cumulative series from events
    spans = {e.get("id"): {"parent_id": e.get("parent_id"), "type": e.get("type"), "name": e.get("name")}
             for e in sample.get("events", []) if e.get("event") == "span_begin" and e.get("id")}
    calls = []
    model_name = None
    points = []  # (t, cost, tokens, n_model, n_tool)
    cost = tokens = 0.0
    n_model = n_tool = 0
    last_tool = last_msg = None
    for e in sample.get("events", []):
        t = ts(e.get("timestamp"))
        if t is None:
            continue
        if e.get("event") == "model" and not e.get("pending"):
            model_name = e.get("model") or model_name
            u = (e.get("output") or {}).get("usage") or {}
            c = cost_of(model_name or "", u)
            tk = (u.get("input_tokens") or 0) + (u.get("input_tokens_cache_read") or 0) + (u.get("output_tokens") or 0)
            cost += c
            tokens += tk
            calls.append((t, agent_of(e.get("span_id"), e.get("role"), spans), tk, c))
            n_model += 1
            content = (((e.get("output") or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
            text = content if isinstance(content, str) else " ".join(
                c.get("text", "") for c in (content or []) if isinstance(c, dict) and c.get("type") == "text")
            if text.strip() and not text.strip().startswith("attachment://"):
                last_msg = {"ts": e["timestamp"], "text": text[-600:]}
        elif e.get("event") == "tool":
            n_tool += 1
            a = e.get("arguments") or {}
            last_tool = {"ts": e["timestamp"], "function": e.get("function"),
                         "args": str(a.get("cmd") or a.get("command") or a.get("code") or a)[:400]}
        points.append((t - t0, cost, tokens, n_model, n_tool))

    # aggregated usage (authoritative total; event sum can be slightly lower, e.g. compaction)
    agg_cost = 0.0
    agg_tok = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    for m, u in (sample.get("model_usage") or {}).items():
        agg_cost += cost_of(m, u)
        agg_tok["input"] += u.get("input_tokens") or 0
        agg_tok["cached"] += u.get("input_tokens_cache_read") or 0
        agg_tok["output"] += u.get("output_tokens") or 0
        agg_tok["reasoning"] += u.get("reasoning_tokens") or 0
        model_name = model_name or m

    elapsed_total = (t_end - t0) if t_end and t0 else (points[-1][0] if points else 0)
    history = []
    idx = 0
    cur = (0, 0.0, 0, 0, 0)
    for step in range(0, int(elapsed_total), STEP_S):
        while idx < len(points) and points[idx][0] <= step:
            cur = points[idx]
            idx += 1
        history.append({"ts": datetime.fromtimestamp(t0 + step).astimezone().isoformat(timespec="seconds"),
                        "elapsed_s": step, "phase": "agent_running",
                        "artifacts_present": None, "partial_score": None,
                        "cost_usd": round(cur[1], 4), "tokens_total": int(cur[2]),
                        "n_model_calls": cur[3], "n_tool_calls": cur[4], "progress_done": None})
    final_score = grade.get("score")
    arts = grade.get("artifacts", [])
    history.append({"ts": datetime.fromtimestamp(t_end).astimezone().isoformat(timespec="seconds"),
                    "elapsed_s": round(elapsed_total), "phase": "completed",
                    "artifacts_present": len(arts),
                    "partial_score": final_score, "cost_usd": round(agg_cost or cost, 4),
                    "tokens_total": int(sum(agg_tok[k] for k in ("input", "cached", "output")) or tokens),
                    "n_model_calls": n_model, "n_tool_calls": n_tool, "progress_done": None})

    meta = {
        "run_id": run_id, "task_id": args.task_id, "paper_id": paper_id or (sample.get("id") if isinstance(sample.get("id"), str) else None),
        "model": model_name or model_slug, "effort": (sample.get("metadata") or {}).get("resolved_effort", "xhigh"),
        "condition": args.condition, "description": args.description, "baseline_run_id": None,
        "vm": manifest.get("instance_name") or manifest.get("vm_name") or "(supprimée)",
        "results_prefix": args.results_uri.rstrip("/") + "/", "time_limit_s": 86400,
        "started_at": datetime.fromtimestamp(t0).astimezone().isoformat(timespec="seconds"),
        "imported": True,
        "owner": args.owner,
        "gcp_project": args.gcp_project or manifest.get("project"),
    }
    latest = {
        "ts": history[-1]["ts"], "elapsed_s": round(elapsed_total), "phase": "completed",
        "status": "succeeded" if manifest.get("status", "succeeded") == "succeeded" else manifest.get("status"),
        "artifacts_present": len(arts), "artifacts_total": len(arts),
        "partial_score": final_score, "score_is_final": True, "grade_error": None,
        "cost_usd": round(agg_cost or cost, 4), "tokens": agg_tok,
        "n_model_calls": n_model, "n_tool_calls": n_tool,
        "last_tool": last_tool, "last_message": last_msg, "idle_s": 0, "progress": {},
        "eta": {"remaining_s": 0, "method": "terminé", "time_limit_left_s": None},
        "resources": {},
        **agents_summary(calls, t0, t_end),
        "judge": {"score": judge.get("judge_score"), "failure_modes": judge.get("failure_modes", [])},
        "artifacts": [{
            "artifact_id": a.get("artifact_id"), "path": a.get("agent_artifact_path") or a.get("artifact_id"),
            "present": True, "mtime": None, "score": a.get("score"),
            "checks": [{"metric": c.get("metric"), "axis": c.get("axis"), "score": c.get("score"),
                        "details": clean_details(c.get("details"))} for c in a.get("checks", [])],
        } for a in arts],
    }

    files = {"meta.json": json.dumps(meta, indent=2, ensure_ascii=False),
             "latest.json": json.dumps(latest, indent=2, ensure_ascii=False),
             "history.jsonl": "\n".join(json.dumps(h) for h in history) + "\n"}
    if args.out_dir:
        d = Path(args.out_dir) / run_id
        d.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (d / name).write_text(body, encoding="utf-8")
        dest = str(d)
    else:
        dest_uri = args.dashboard_prefix or f"gs://{src.bucket_name}/_dashboard"
        b, _, p = dest_uri[5:].partition("/")
        bucket = src.client.bucket(b)
        for name, body in files.items():
            bucket.blob(f"{p.rstrip('/')}/{run_id}/{name}").upload_from_string(body, content_type="application/json")
        dest = f"{dest_uri}/{run_id}/"
    print(f"run_id   : {run_id}")
    print(f"score    : {final_score}  ({len(arts)} artefacts)")
    print(f"durée    : {elapsed_total/60:.1f} min agent")
    print(f"coût LLM : {agg_cost:.3f} $ (agrégé)  · somme des événements {cost:.3f} $")
    print(f"judge    : {judge.get('judge_score')}  {judge.get('failure_modes')}")
    print(f"écrit dans {dest}")


if __name__ == "__main__":
    main()

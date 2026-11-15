"""Collect every COMPLETED task 9 run on Sherlock into one JSONL (one line per run).

Runs inside the runner image (needs inspect_ai to read .eval logs). Per run: condition, artifact
scores (grade.json), process-judge failure modes and score (judge.json), cost/tokens/turns/time
(.eval log, gpt-5.4-mini prices used by the bixdash collector), sub-agent count.
Only phase == "completed" runs are kept (smoke tests, cancelled and crashed runs are excluded).
A per-run cache makes re-runs fast: only new runs are read.
usage: python collect_on_sherlock.py RUNS_DIR OUT_JSONL
"""
import glob, json, os, sys

RUNS, OUT = sys.argv[1], sys.argv[2]
CACHE = OUT + ".cache.json"
P = {"input": 0.75, "cached": 0.075, "output": 4.50}  # $ per 1M tokens, gpt-5.4-mini
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def with_fulltrace(row, run_dir):
    """Sub-agent runs: the official judge only sees the orchestrator's messages. If a re-judge on the
    transcript flattened from all eval events exists (judge_fulltrace.json), use it; keep the original too."""
    path = os.path.join(run_dir, "judge_fulltrace.json")
    if os.path.exists(path):
        j = json.load(open(path))
        if j.get("judge_status") == "ok":
            row["failure_modes_orchestrator_only"] = row.get("failure_modes")
            row["judge_score_orchestrator_only"] = row.get("judge_score")
            row.update(failure_modes=j.get("failure_modes") or [], judge_score=j.get("judge_score"), judge_source="full_logs")
    return row


def eval_stats(run_dir):
    from inspect_ai.log import read_eval_log
    paths = glob.glob(os.path.join(run_dir, "inspect_logs", "*.eval"))
    if not paths:
        return {}
    log = read_eval_log(paths[0])
    if not log.samples:
        return {"sample_error": "no samples in eval log"}
    s = log.samples[0]
    inp = cached = out = reas = calls = tools = 0
    for e in s.events:
        if e.event == "model" and e.output and e.output.usage:
            u = e.output.usage
            c = u.input_tokens_cache_read or 0
            i = u.input_tokens or 0
            inp += i - c if i >= c else i
            cached += c
            out += u.output_tokens or 0
            reas += u.reasoning_tokens or 0
            calls += 1
        elif e.event == "tool":
            tools += 1
    cost = (inp * P["input"] + cached * P["cached"] + out * P["output"]) / 1e6
    return {"cost_usd": round(cost, 3), "tokens_uncached_in": inp, "tokens_cached_in": cached,
            "tokens_out": out, "tokens_reasoning": reas, "model_calls": calls, "tool_calls": tools,
            "total_time_s": round(s.total_time or 0), "working_time_s": round(s.working_time or 0),
            "sample_error": bool(s.error), "main_messages": len(s.messages)}


rows = []
for run_dir in sorted(glob.glob(os.path.join(RUNS, "*01879*"))):
    name = os.path.basename(run_dir)
    try:
        manifest = json.load(open(os.path.join(run_dir, "run_manifest.json")))
        phase = json.load(open(os.path.join(run_dir, "status.json"))).get("phase")
    except Exception:
        continue
    if phase != "completed" or not os.path.exists(os.path.join(run_dir, "grade.json")):
        continue
    if name in cache:
        rows.append(with_fulltrace(dict(cache[name]), run_dir)); continue
    text = json.dumps(manifest)
    condition = manifest.get("live_tracking", {}).get("condition") if isinstance(manifest.get("live_tracking"), dict) else None
    if not condition:
        import re
        m = re.search(r'"condition": "([^"]+)"', text)
        condition = m.group(1) if m else "unknown"
    grade = json.load(open(os.path.join(run_dir, "grade.json")))
    artifacts = {a["artifact_id"]: a.get("score") for a in grade.get("artifacts", [])}
    judge = {}
    if os.path.exists(os.path.join(run_dir, "judge.json")):
        j = json.load(open(os.path.join(run_dir, "judge.json")))
        judge = {"judge_score": j.get("judge_score"), "judge_status": j.get("judge_status"),
                 "failure_modes": j.get("failure_modes") or []}
    try:
        n_sub = json.load(open(os.path.join(run_dir, "broker_logs", "subagents_summary.json"))).get("total_subagents")
    except Exception:
        n_sub = None
    row = {"run": name, "run_id": manifest.get("run_id"), "condition": condition,
           "task_score_mean": grade.get("score"), "artifact_scores": artifacts,
           "n_subagents": n_sub, **judge, **eval_stats(run_dir)}
    cache[name] = row
    rows.append(with_fulltrace(dict(row), run_dir))
    print("read", condition, name[-30:], round(grade.get("score") or 0, 3), row.get("cost_usd"), file=sys.stderr)

json.dump(cache, open(CACHE, "w"))
with open(OUT, "w") as handle:
    for row in rows:
        handle.write(json.dumps(row) + "\n")
print(f"{len(rows)} completed task 9 runs -> {OUT}", file=sys.stderr)

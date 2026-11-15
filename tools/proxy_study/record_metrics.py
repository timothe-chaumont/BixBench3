"""Authoritative actor metrics and deterministic common-scope scores, host only."""

import json
from datetime import datetime
from pathlib import Path

from inspect_ai.log import read_eval_log

PRICES = {"openai/gpt-5.4-mini": (0.75, 0.075, 4.5), "gpt-5.4-mini": (0.75, 0.075, 4.5)}


def summarize(root):
    root = Path(root)
    files = sorted((root / "inspect_logs").glob("*.eval"))
    if not files:
        raise RuntimeError("Missing Inspect trace")
    log = read_eval_log(str(files[-1]))
    sample = log.samples[0] if log.samples else None
    if sample is None:
        raise RuntimeError("Missing Inspect sample")
    usage = sample.model_usage or {}
    cost = 0.0
    tokens = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    unknown = []
    for model, u in usage.items():
        p = PRICES.get(model) or PRICES.get(model.split("/")[-1])
        if p:
            cost += (
                u.input_tokens * p[0]
                + (u.input_tokens_cache_read or 0) * p[1]
                + u.output_tokens * p[2]
            ) / 1e6
        else:
            unknown.append(model)
        tokens["input"] += u.input_tokens
        tokens["cached"] += u.input_tokens_cache_read or 0
        tokens["output"] += u.output_tokens
        tokens["reasoning"] += u.reasoning_tokens or 0
    events = sample.events or []
    start = datetime.fromisoformat(sample.started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(sample.completed_at.replace("Z", "+00:00"))
    grade = json.loads((root / "grade.json").read_text()) if (root / "grade.json").exists() else {}
    artifacts = {a["artifact_id"]: a.get("score", 0.0) for a in grade.get("artifacts", [])}
    downstream = {k: v for k, v in artifacts.items() if k != "tempo_seq_filtered_counts"}
    limit = sample.limit.model_dump(mode="json") if sample.limit else None
    error = sample.error.model_dump(mode="json") if sample.error else None
    out = {
        "source": "final_inspect_eval",
        "is_lower_bound": False,
        "cost_usd": round(cost, 8),
        "unknown_price_models": unknown,
        "tokens": tokens,
        "tokens_total": sum(tokens[k] for k in ["input", "cached", "output"]),
        "n_model_calls": sum(
            getattr(e, "event", None) == "model" and not getattr(e, "pending", False)
            for e in events
        ),
        "n_tool_calls": sum(getattr(e, "event", None) == "tool" for e in events),
        "elapsed_s": round((end - start).total_seconds(), 3),
        "started_at": sample.started_at,
        "completed_at": sample.completed_at,
        "ts": sample.completed_at,
        "limit": limit,
        "sample_error": error,
        "eval_status": log.status,
        "artifact_score": grade.get("score"),
        "artifact_scores": artifacts,
        "downstream_score": sum(downstream.values()) / 4 if len(downstream) == 4 else None,
        "count_score": artifacts.get("tempo_seq_filtered_counts"),
        "artifacts_present": sum(
            (root / "outputs" / Path(a["path"]).name).is_file()
            for a in json.loads((root / "dataset/case.json").read_text())["expected_outputs"]
        ),
        "scientifically_valid": error is None or limit is not None,
    }
    (root / "study_metrics.json").write_text(json.dumps(out, indent=2) + "\n")
    (root / "final_usage.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(summarize(sys.argv[1]), indent=2))

"""Export tool/model timing and usage without copying prompts or tool output text."""

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from inspect_ai.log import read_eval_log
from record_metrics import flattened_events


def category(event):
    arguments = event.arguments or {}
    text = str(arguments).lower()
    if arguments.get("action") == "read" or "sleep " in text:
        return "polling_or_wait"
    if any(
        s in text
        for s in (
            "install.packages",
            "biocmanager::install",
            "pip install",
            "micromamba create",
            "micromamba install",
        )
    ):
        return "package_setup"
    if any(s in text for s in ("help(", "args(", "deparse(", "body(", "vignette")):
        return "api_documentation"
    if any(s in text for s in ("qalign", "qcount", "bowtie", "fastq")):
        return "read_counting"
    if any(s in text for s in ("deseq(", "deseqdataset", "results(dds")):
        return "differential_expression"
    if any(s in text for s in ("rungsa", "gsasummarytable", "hypergeom", "phyper", "dna_damage")):
        return "enrichment"
    if event.function in ("text_editor", "file_editor"):
        return "code_editing"
    if any(s in text for s in ("metadata", "read_csv", "read.delim", "find /data", "columns")):
        return "input_schema"
    return "other"


def export(trace, out):
    log = read_eval_log(str(trace), resolve_attachments=True)
    sample = log.samples[0]
    start = datetime.fromisoformat(sample.started_at)
    out.mkdir(parents=True, exist_ok=True)
    models = []
    tools = []
    for event in flattened_events(sample.events):
        elapsed = (event.timestamp - start).total_seconds()
        duration = (
            (event.completed - event.timestamp).total_seconds()
            if getattr(event, "completed", None)
            else None
        )
        if event.event == "model" and not getattr(event, "pending", False):
            usage = event.output.usage if event.output else None
            if not usage:
                continue
            models.append(
                {
                    "elapsed_s": elapsed,
                    "duration_s": duration,
                    "model": event.model,
                    "uncached_input": usage.input_tokens,
                    "cached_input": usage.input_tokens_cache_read or 0,
                    "output": usage.output_tokens,
                    "reasoning_subset_of_output": usage.reasoning_tokens or 0,
                    "logged_cost_usd": usage.total_cost,
                }
            )
        elif event.event == "tool":
            text = str(event.result)
            tools.append(
                {
                    "elapsed_s": elapsed,
                    "duration_s": duration,
                    "tool": event.function,
                    "action": event.arguments.get("action") if event.arguments else None,
                    "category": category(event),
                    "tool_error": bool(event.error),
                    "error_text_marker": any(
                        s in text
                        for s in (
                            "Error in ",
                            "Traceback (most recent call last)",
                            "ModuleNotFoundError:",
                            "Execution halted",
                        )
                    ),
                }
            )
    for name, values in (("model-calls.csv", models), ("tool-events.csv", tools)):
        if values:
            with (out / name).open("w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(values[0]))
                writer.writeheader()
                writer.writerows(values)
    return {
        "model_events": len(models),
        "tool_events": len(tools),
        "tool_categories": dict(Counter(row["category"] for row in tools)),
        "tool_output_error_markers": sum(row["error_text_marker"] for row in tools),
    }


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.trace, args.out), indent=2))

"""v5 dag-orchestrator: sub-agent tools that start fresh agents on self-contained briefs.

`run_subagent(role, brief)` starts one sub-agent; `run_subagents(jobs)` starts several at once
(one level of the dependency plan, whose artifacts never depend on each other) and returns all
their reports. Each sub-agent is a new `react` agent with the same sandbox tools as the main agent
(its own bash session, python, text editor, web access request) and an empty context: the brief
is the only thing it knows.

v5 changes (cost and time, see experiments/t9-env-subagents-v5.md):
  - sub-agents run at reasoning effort `medium` (SUBAGENT_EFFORT); the orchestrator keeps the
    run's effort (xhigh). Every other generation setting is copied from the run's configuration;
  - sub-agent instructions: wait for long jobs with one blocking call (no busy polling), inspect
    tables with head/wc/grep and run shared scripts instead of reading them, verify existing
    outputs before rebuilding, shared reference files are always allowed;
  - `run_subagents` runs up to MAX_PARALLEL sub-agents concurrently.

Depth: the main agent is depth 0. A sub-agent at depth d gets the sub-agent tools only while
d < MAX_DEPTH (orchestrator -> artifact builder -> brick worker), so recursion is bounded.

Counting (never touches /outputs, the grade or the judge):
  - Inspect sample store key `bixbench3_subagents` (saved in the .eval log);
  - $BIXBENCH3_BROKER_LOG_DIR/subagents.jsonl (one line per sub-agent start/end) and
    subagents_summary.json (running totals); broker_logs/ is uploaded with the run;
  - every sub-agent runs in an Inspect agent span named `subagent-<n>-<role>`, which the
    bixdash collector counts (`n_subagents` on the live dashboard).
A failure inside a sub-agent is returned to the caller as text; it never ends the sample.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import anyio
from inspect_ai.agent import AgentSubmit, react, run
from inspect_ai.model import GenerateConfig, Model, get_model
from inspect_ai.model._generate_config import active_generate_config
from inspect_ai.tool import Tool, ToolDef, ToolError, bash_session, python, text_editor, tool
from inspect_ai.util import message_limit, store
from pydantic import ValidationError

from ..run_memory import (
    SUBAGENT_MEMORY_RULES,
    absorb_subagent,
    build_pack,
    recall_tool,
    with_capture,
)
from .web_access import request_web_access

MAX_DEPTH = 2  # 0 = main agent, 1 = planner / artifact builder, 2 = brick worker (no further sub-agents)
MAX_SUBAGENTS = 200  # per sample, all depths
MAX_PARALLEL = 6  # sub-agents running at the same time in one run_subagents call (6 CPUs)
MESSAGE_LIMITS = {1: 800, 2: 300}  # per sub-agent, by depth
SUBAGENT_EFFORT = "medium"  # orchestrator keeps the run's effort (xhigh)
STORE_KEY = "bixbench3_subagents"

SUBAGENT_INSTRUCTIONS = """You are a sub-agent of a computational biology reproduction run.
You start with no memory of the main conversation: the brief below is everything you know.

Rules:
- Read ONLY the inputs the brief lists as allowed. Shared reference files under /data (raw data,
  reference genome, annotation/GTF, sample metadata) are always allowed. Never open forbidden
  paths, outputs of artifacts the brief does not list, or anything that looks like expected
  results, reference outputs or published values.
- Write ONLY inside the output folder the brief gives you (create it if needed). Never write to
  /outputs unless the brief explicitly tells you to.
- If your output folder already holds a result, verify it first; rebuild it only if it fails the
  check.
- Waiting: to wait for a long-running job, use ONE blocking call (`wait <PID>`, or `sleep 300` in a
  single command, staying under the 10-minute tool timeout), then check once. Never check a job's
  status more often than every 5 minutes, and never with a series of short calls.
- Reading: inspect tables with `head`, `wc -l`, `cut` or `grep`; never print or open whole tables.
  Run long or verbose programs (index builds, aligners, installers) with their output redirected to a
  log file (`cmd > step.log 2>&1`), then read the log with `tail` or `grep`.
  Run shared scripts instead of reading them; open a script only if you must change it.
- Save every script you run in your output folder, so the work can be audited and re-run.
- If something blocks you, try reasonable fixes; if you still cannot finish, stop and report
  exactly what failed, what you tried and what partial files exist.
- When done, call submit() with a short report: output paths, what you checked, any issues.
""" + SUBAGENT_MEMORY_RULES


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "task"


def _log_dir() -> Path | None:
    value = os.environ.get("BIXBENCH3_BROKER_LOG_DIR")
    return Path(value) if value else None


def _record(event: dict, summary: dict) -> None:
    """Best effort: the counter files must never break the run."""
    directory = _log_dir()
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "subagents.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        tmp = directory / ".subagents_summary.json.tmp"
        tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(directory / "subagents_summary.json")
    except OSError:
        pass


def _summary(state: dict) -> dict:
    by_role: dict[str, int] = {}
    by_depth: dict[str, int] = {}
    for item in state["calls"]:
        by_role[item["role"]] = by_role.get(item["role"], 0) + 1
        by_depth[str(item["depth"])] = by_depth.get(str(item["depth"]), 0) + 1
    return {
        "total_subagents": state["count"],
        "finished": sum(1 for c in state["calls"] if c.get("status")),
        "failed": sum(1 for c in state["calls"] if c.get("status") not in (None, "ok")),
        "max_parallel_seen": state.get("max_parallel_seen", 1),
        "subagent_effort": SUBAGENT_EFFORT,
        "by_role": by_role,
        "by_depth": by_depth,
        "updated_at": _now(),
    }


def subagent_model() -> Model:
    """The run's model with the run's generation settings, except reasoning effort = SUBAGENT_EFFORT.

    A separate Model instance is not the active model, so Inspect does not merge the run-level
    config (e.g. --reasoning-effort xhigh) into it; we copy that config explicitly instead.
    """
    active = get_model()
    config = active.config.merge(active_generate_config()).merge(GenerateConfig(reasoning_effort=SUBAGENT_EFFORT))
    return get_model(str(active), config=config, **(getattr(active, "model_args", None) or {}))


UNREADABLE_REPLY = (
    "The tool's reply could not be read (usually because the command printed more than about 10 MB). "
    "The command may still be running or may have finished: check its state and outputs with a short "
    "command. Redirect long or verbose output to a log file (`cmd > step.log 2>&1`) and read it with "
    "`tail` or `grep`."
)


def _robust(tool_object: Tool) -> Tool:
    """The same tool, but an unreadable sandbox reply becomes a ToolError the agent can recover from.

    Inspect keeps only the last 10 MiB of a sandbox command's output (Docker and Sherlock alike);
    a flood of output (e.g. hisat2-build warnings) truncates the tool-support JSON reply, and the
    resulting ValidationError would otherwise end the whole sub-agent.
    """
    definition = ToolDef(tool_object)

    async def wrapped(**kwargs: Any) -> Any:  # must be **kwargs: Any (Inspect's tool_params passes arguments through)
        try:
            return await definition.tool(**kwargs)
        except (ValidationError, JSONDecodeError) as error:
            raise ToolError(UNREADABLE_REPLY) from error

    return ToolDef(
        wrapped, name=definition.name, description=definition.description, parameters=definition.parameters,
        parallel=definition.parallel, viewer=definition.viewer, model_input=definition.model_input,
        options=definition.options,
    ).as_tool()


def _sub_tools(depth: int, number: int, name: str) -> list[Tool]:
    tools: list[Tool] = [
        _robust(with_capture(bash_session(timeout=600, instance=f"subagent-{number}"), name)),  # own shell: no shared cwd/jobs
        _robust(with_capture(python(timeout=600), name)),  # run memory: capture read-only inspections
        with_capture(text_editor(timeout=120), name),
        request_web_access(),
        recall_tool(),  # run memory
    ]
    if depth < MAX_DEPTH:
        tools += [run_subagent(depth=depth + 1), run_subagents(depth=depth + 1)]
    return tools


async def _run_one(role: str, brief: str, depth: int) -> str:
    state = store().get(STORE_KEY) or {"count": 0, "calls": [], "active": 0, "max_parallel_seen": 0}
    if state["count"] >= MAX_SUBAGENTS:
        return f"[sub-agent not started: limit reached ({MAX_SUBAGENTS}); finish the work yourself]"
    state["count"] += 1
    state["active"] = state.get("active", 0) + 1
    state["max_parallel_seen"] = max(state.get("max_parallel_seen", 0), state["active"])
    number = state["count"]
    name = f"subagent-{number}-{_slug(role)}"
    call = {"n": number, "role": role, "depth": depth, "name": name, "started_at": _now(), "status": None}
    state["calls"].append(call)
    store().set(STORE_KEY, state)
    _record({"event": "start", **call, "brief_chars": len(brief)}, _summary(state))

    report = ""
    status = "ok"
    limit = MESSAGE_LIMITS.get(depth, 300)
    try:
        pack = await build_pack(brief, name)  # run memory: conventions + most relevant known facts
        full_brief = brief + ("\n\n" + pack if pack else "")
        agent = react(
            name=name,
            description=f"sub-agent ({role})",
            prompt=SUBAGENT_INSTRUCTIONS,
            tools=_sub_tools(depth, number, name),
            model=subagent_model(),
            submit=AgentSubmit(answer_only=True),
        )
        result, limit_error = await run(agent, full_brief, limits=[message_limit(limit)], name=name)
        report = (result.output.completion or "").strip()
        if limit_error is not None:
            status = "message_limit"
            report = (report + "\n\n" if report else "") + (
                f"[sub-agent stopped: message limit {limit} reached; check its output folder for partial results]"
            )
        if not report:
            report = "[sub-agent ended without a report; check its output folder]"
    except Exception as error:  # report, never crash the caller
        status = "error"
        report = f"[sub-agent failed: {type(error).__name__}: {str(error)[:500]}]"

    try:  # run memory: store LEARNED items and produced files; the caller gets the short report
        report = await absorb_subagent(report, brief, name)
    except Exception as error:
        report += f"\n[run memory: could not store this sub-agent's results: {type(error).__name__}]"

    state = store().get(STORE_KEY) or state
    state["active"] = max(0, state.get("active", 1) - 1)
    for item in state["calls"]:
        if item["n"] == number:
            item.update({"status": status, "ended_at": _now(), "report_chars": len(report)})
    store().set(STORE_KEY, state)
    _record({"event": "end", "n": number, "role": role, "depth": depth, "name": name,
             "status": status, "ended_at": _now()}, _summary(state))
    return report


@tool
def run_subagent(depth: int = 1) -> Tool:
    async def execute(role: str, brief: str) -> str:
        """Start ONE new sub-agent with an empty context and a self-contained brief.

        The sub-agent has its own shell plus python, the text editor and web access
        requests, in the same sandbox and filesystem as you. It knows NOTHING except
        the brief, so the brief must contain: the goal, the exact input paths it is
        allowed to read, what it must not read, the output folder to write to, and
        how to check success. It returns the sub-agent's final report.
        To start several independent sub-agents at once, use run_subagents.

        Args:
            role: Short role label, e.g. "artifact:deseq2", "brick:3-normalize".
            brief: The complete, self-contained instructions for the sub-agent.

        Returns:
            The sub-agent's final report (or an error description if it failed).
        """
        if not brief.strip():
            raise ToolError("brief is empty")
        return await _run_one(role, brief, depth)

    return execute


@tool
def run_subagents(depth: int = 1) -> Tool:
    async def execute(jobs: list[dict[str, str]]) -> str:
        """Start several INDEPENDENT sub-agents at the same time and wait for all of them.

        Use it for artifacts of the same dependency level: none of them may need another's
        output. Each job is {"role": ..., "brief": ...} with the same self-contained brief
        rules as run_subagent. At most 6 run at once (the rest start as slots free up).

        Args:
            jobs: List of {"role": short role label, "brief": complete instructions}.

        Returns:
            One section per job, in the given order, with each sub-agent's final report.
        """
        if not jobs:
            raise ToolError("jobs is empty")
        for job in jobs:
            if not isinstance(job, dict) or not str(job.get("brief", "")).strip():
                raise ToolError('every job needs {"role": ..., "brief": ...} with a non-empty brief')
        results: list[str] = [""] * len(jobs)
        limiter = anyio.Semaphore(MAX_PARALLEL)

        async def one(index: int, job: dict[str, str]) -> None:
            async with limiter:
                results[index] = await _run_one(str(job.get("role") or f"job-{index + 1}"), str(job["brief"]), depth)

        async with anyio.create_task_group() as group:
            for index, job in enumerate(jobs):
                group.start_soon(one, index, job)
        return "\n\n".join(
            f"### {job.get('role') or f'job-{i + 1}'}\n{results[i]}" for i, job in enumerate(jobs)
        )

    return execute

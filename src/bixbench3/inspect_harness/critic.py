"""Experiment v3e: lightweight critic at stage boundaries (critic-only).

At three boundaries (after counting, after differential expression, before the final
submit) a critic built on the run's own model reads the task prompt (which carries the
method guidance), the agent's most recent code and the head of its output files, and
reports deviations from the guidance. The critic only advises: it never edits files,
never sees ground truth, grader output or reference results (none of which exist in
the sandbox), and is capped at ``MAX_CALLS_PER_STAGE`` calls per boundary. Every
critique is appended to ``work/critic_notes.md``.

The agent calls ``request_critique`` for the first two boundaries. The pre-submit
review is triggered by the first ``submit`` call, which is returned as a tool error
carrying the critique; the next ``submit`` call is accepted unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from inspect_ai.model import ChatMessage, ChatMessageSystem, ChatMessageUser, get_model
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, ToolError, tool
from inspect_ai.util import sandbox, store

_HERE = Path(__file__).parent
SNAPSHOT_SCRIPT_PATH = _HERE / "sandbox_scripts" / "critic_snapshot.py"
SANDBOX_SNAPSHOT_PATH = "/tmp/bixbench3_critic_snapshot.py"
SANDBOX_DATA = "/data"
SANDBOX_WORK = "/workspace/work"
SANDBOX_OUTPUTS = "/outputs"

AGENT_STAGES = ("counting", "differential_expression")
SUBMIT_STAGE = "pre_submit"
MAX_CALLS_PER_STAGE = 2
GUIDANCE_CHARS = 12_000
SNAPSHOT_CHARS = 24_000
SNAPSHOT_TIMEOUT_SECONDS = 120

PROMPT_KEY = "critic_task_prompt"
LOG_KEY = "critic_log"
SUBMIT_REVIEWED_KEY = "critic_submit_reviewed"

CRITIC_NOTICE = """## Stage Critic

A critic is available through the `request_critique` tool. It reads the task and method \
guidance above, your most recent code under `./work` and the files under `./outputs`, and \
reports deviations from the guidance (method substitutions, wrong contrasts, wrong filters, \
missing samples, format issues). It only advises: it never edits files and has no reference \
answers, so weigh its notes against the guidance yourself.

- Call `request_critique(stage="counting")` once the count matrix is written.
- Call `request_critique(stage="differential_expression")` once the differential-expression \
results are written.
- Your first `submit()` call triggers a final review instead of submitting. Address real \
problems, then call `submit()` again; that call is accepted.

Critiques are logged in `./work/critic_notes.md`.
"""

CRITIC_SYSTEM = """You are a method critic reviewing a bioinformatics analysis agent's work \
in progress. You only advise; you cannot edit anything.

Compare the agent's code and outputs with the task's method guidance and report concrete \
deviations: tool or method substitutions, wrong versions or parameters, wrong contrasts or \
reference levels, wrong filters or thresholds, missing, extra or mislabeled samples, wrong \
output file names, columns or formats, and gaps in METHODS.md. Cite the file and the \
guidance it departs from. You have no reference answers: never guess expected values, gene \
lists or row counts. If the snapshot is too partial to judge something, say so briefly.

Answer with at most 8 bullet points, most severe first. If nothing deviates, answer exactly \
"No deviations found."
"""


def append_critic_notice(prompt: str) -> str:
    return prompt.rstrip() + "\n\n" + CRITIC_NOTICE


def critic_messages(stage: str, guidance: str, snapshot: str) -> list[ChatMessage]:
    if len(guidance) > GUIDANCE_CHARS:
        guidance = guidance[:GUIDANCE_CHARS] + "\n<guidance truncated>"
    return [
        ChatMessageSystem(content=CRITIC_SYSTEM),
        ChatMessageUser(
            content=f"Boundary: {stage}\n\n# Task and method guidance\n\n{guidance}\n\n# Agent workspace snapshot\n\n{snapshot}"
        ),
    ]


def notes_entry(stage: str, call: int, critique: str) -> str:
    return f"## {stage} (critique {call}/{MAX_CALLS_PER_STAGE})\n\n{critique.strip()}\n\n"


class Critic:
    """Stage-limited critique loop with injectable I/O (sandbox, model, notes file)."""

    def __init__(
        self,
        *,
        state: Any,
        take_snapshot: Callable[[], Awaitable[str]],
        ask_model: Callable[[list[ChatMessage]], Awaitable[str]],
        append_notes: Callable[[str], Awaitable[None]],
    ) -> None:
        self.state = state
        self.take_snapshot = take_snapshot
        self.ask_model = ask_model
        self.append_notes = append_notes

    async def critique(self, stage: str) -> str:
        log = list(self.state.get(LOG_KEY, []))
        calls = sum(1 for entry in log if entry["stage"] == stage)
        if calls >= MAX_CALLS_PER_STAGE:
            return f"Critique limit reached for stage '{stage}' ({MAX_CALLS_PER_STAGE} calls). Continue with your own judgement."
        try:
            snapshot = await self.take_snapshot()
            critique = (await self.ask_model(critic_messages(stage, self.state.get(PROMPT_KEY, ""), snapshot))).strip()
            status = "ok"
        except Exception as error:  # the critic is advisory; it must never cost the run
            critique = f"Critic unavailable ({type(error).__name__}). Continue with your own checks."
            status = "error"
        if not critique:
            critique, status = "Critic returned no text. Continue with your own checks.", "error"
        self.state[LOG_KEY] = [*log, {"stage": stage, "status": status, "chars": len(critique)}]
        try:
            await self.append_notes(notes_entry(stage, calls + 1, critique))
        except Exception:
            pass
        return critique


async def _take_snapshot() -> str:
    environment = sandbox()
    await environment.write_file(SANDBOX_SNAPSHOT_PATH, SNAPSHOT_SCRIPT_PATH.read_text(encoding="utf-8"))
    result = await environment.exec(
        ["python3", SANDBOX_SNAPSHOT_PATH, "--data", SANDBOX_DATA, "--work", SANDBOX_WORK,
         "--outputs", SANDBOX_OUTPUTS, "--budget", str(SNAPSHOT_CHARS)],
        timeout=SNAPSHOT_TIMEOUT_SECONDS,
    )
    if not result.success:
        raise RuntimeError((result.stderr or result.stdout)[-500:])
    return result.stdout


async def _ask_model(messages: list[ChatMessage]) -> str:
    output = await get_model().generate(messages)
    return output.completion


def _notes_path() -> str:
    return SANDBOX_WORK + "/critic_notes.md"


async def _append_notes(entry: str) -> None:
    environment = sandbox()
    try:
        existing = await environment.read_file(_notes_path())
    except FileNotFoundError:
        existing = "# Stage critic notes\n\nAdvisory only; the critic never sees reference answers.\n\n"
    await environment.write_file(_notes_path(), existing + entry)


class _StoreState:
    """Mapping view over the sample store, so the critic log lands in the eval log."""

    def get(self, key: str, default: Any = None) -> Any:
        return store().get(key, default)

    def __setitem__(self, key: str, value: Any) -> None:
        store().set(key, value)


def _critic() -> Critic:
    return Critic(state=_StoreState(), take_snapshot=_take_snapshot, ask_model=_ask_model, append_notes=_append_notes)


@tool
def request_critique() -> Tool:
    async def execute(stage: str) -> str:
        """Ask the stage critic to review your work against the method guidance.

        The critic reads the task and method guidance, your most recent code under
        ./work and the head of each file under ./outputs, and lists deviations from
        the guidance. It is advisory only and has no reference answers. At most two
        critiques per stage.

        Args:
            stage: "counting" once the count matrix is written, or
                "differential_expression" once differential-expression results are written.

        Returns:
            The critic's notes (also appended to ./work/critic_notes.md).
        """
        if stage not in AGENT_STAGES:
            raise ToolError(f"stage must be one of {', '.join(AGENT_STAGES)}")
        return await _critic().critique(stage)

    return execute


@tool(name="submit")
def critic_submit() -> Tool:
    async def execute(answer: str) -> str:
        """Submit an answer for evaluation.

        Args:
          answer (str): Submitted answer
        """
        if store().get(SUBMIT_REVIEWED_KEY, False):
            return answer
        store().set(SUBMIT_REVIEWED_KEY, True)
        critique = await _critic().critique(SUBMIT_STAGE)
        raise ToolError(
            "Not submitted yet: a final critic review ran first (advisory only; it never sees "
            "reference answers). Its notes, also in ./work/critic_notes.md:\n\n"
            f"{critique}\n\n"
            "Fix any real problems you agree with, then call submit() again; the next call is accepted."
        )

    return execute


@solver
def critic_setup() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate
        state.store.set(PROMPT_KEY, state.user_prompt.text)
        state.user_prompt.text = append_critic_notice(state.user_prompt.text)
        return state

    return solve

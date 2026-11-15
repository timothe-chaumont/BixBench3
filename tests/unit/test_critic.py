"""Experiment v3e: lightweight critic at stage boundaries."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
from inspect_ai import Task, eval
from inspect_ai.agent import AgentSubmit, react
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model

from bixbench3.inspect_harness import critic as critic_module
from bixbench3.inspect_harness.critic import (
    CRITIC_NOTICE,
    LOG_KEY,
    MAX_CALLS_PER_STAGE,
    PROMPT_KEY,
    SNAPSHOT_SCRIPT_PATH,
    Critic,
    append_critic_notice,
    critic_messages,
    critic_setup,
    critic_submit,
    request_critique,
)


def _snapshot_module():
    spec = importlib.util.spec_from_file_location("critic_snapshot", SNAPSHOT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _critic(state: dict, *, answer: str = "No deviations found.", fail: bool = False) -> tuple[Critic, list, list]:
    asked: list = []
    notes: list = []

    async def take_snapshot() -> str:
        if fail:
            raise RuntimeError("sandbox gone")
        return "## Output files\n(no output files yet)"

    async def ask_model(messages) -> str:
        asked.append(messages)
        return answer

    async def append_notes(entry: str) -> None:
        notes.append(entry)

    return Critic(state=state, take_snapshot=take_snapshot, ask_model=ask_model, append_notes=append_notes), asked, notes


def test_notice_is_appended_once_and_names_the_three_boundaries() -> None:
    prompt = append_critic_notice("# Analysis Task\n\nBody.\n")
    assert prompt.startswith("# Analysis Task\n\nBody.\n\n## Stage Critic")
    assert prompt.count(CRITIC_NOTICE) == 1
    for text in ('stage="counting"', 'stage="differential_expression"', "first `submit()`", "./work/critic_notes.md"):
        assert text in prompt


def test_critic_sees_guidance_and_snapshot_but_no_reference_material() -> None:
    messages = critic_messages("counting", "Use DESeq2 1.28.1.", "## Output files\ncounts.csv")
    system, user = (message.text for message in messages)
    assert "only advise" in system and "never guess expected values" in system
    assert "Boundary: counting" in user and "Use DESeq2 1.28.1." in user and "counts.csv" in user
    long = critic_messages("counting", "x" * 50_000, "")[1].text
    assert "<guidance truncated>" in long and len(long) < 13_000


def test_critique_is_logged_and_capped_per_stage() -> None:
    state = {PROMPT_KEY: "Use DESeq2."}
    critic, asked, notes = _critic(state, answer="- counts filtered at >=10 instead of >=5")
    results = [asyncio.run(critic.critique("counting")) for _ in range(MAX_CALLS_PER_STAGE + 1)]
    assert results[0] == "- counts filtered at >=10 instead of >=5"
    assert "limit reached" in results[-1]
    assert len(asked) == MAX_CALLS_PER_STAGE and len(notes) == MAX_CALLS_PER_STAGE
    assert notes[1].startswith(f"## counting (critique 2/{MAX_CALLS_PER_STAGE})")
    assert [entry["stage"] for entry in state[LOG_KEY]] == ["counting"] * MAX_CALLS_PER_STAGE
    asyncio.run(critic.critique("differential_expression"))  # other stages keep their own budget
    assert len(asked) == MAX_CALLS_PER_STAGE + 1


def test_critic_failure_never_raises() -> None:
    state: dict = {}
    critic, asked, notes = _critic(state, fail=True)
    result = asyncio.run(critic.critique("pre_submit"))
    assert result.startswith("Critic unavailable (RuntimeError)")
    assert asked == [] and state[LOG_KEY] == [{"stage": "pre_submit", "status": "error", "chars": len(result)}]
    assert len(notes) == 1


def test_snapshot_lists_inputs_outputs_and_recent_code(tmp_path: Path) -> None:
    snapshot = _snapshot_module()
    data, work, outputs = tmp_path / "data", tmp_path / "work", tmp_path / "outputs"
    (data / "fastq").mkdir(parents=True)
    (data / "fastq" / "S1.fastq.gz").write_bytes(b"x" * 10)
    work.mkdir()
    (work / "de.R").write_text("library(DESeq2)\n")
    (work / "critic_notes.md").write_text("old notes")
    outputs.mkdir()
    (outputs / "counts.csv").write_text("gene,S1\n" + "".join(f"g{i},{i}\n" for i in range(20)))
    (outputs / "METHODS.md").write_text("# Methods\nDESeq2.")
    text = snapshot.snapshot(data, work, outputs, 24_000)
    assert "fastq/S1.fastq.gz  (10 bytes)" in text
    assert "outputs/counts.csv" in text and "21 lines" in text and "g4,4" in text and "g10,10" not in text
    assert "# Methods\nDESeq2." in text
    assert "library(DESeq2)" in text and "old notes" not in text
    assert snapshot.snapshot(data, work, outputs, 100).endswith("<snapshot truncated>")


def test_react_loop_critiques_at_boundaries_and_accepts_second_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("data", "work", "outputs"):
        (tmp_path / name).mkdir()
    (tmp_path / "outputs" / "counts.csv").write_text("gene,S1\ng1,3\n")
    monkeypatch.setattr(critic_module, "SANDBOX_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(critic_module, "SANDBOX_WORK", str(tmp_path / "work"))
    monkeypatch.setattr(critic_module, "SANDBOX_OUTPUTS", str(tmp_path / "outputs"))
    monkeypatch.setattr(critic_module, "SANDBOX_SNAPSHOT_PATH", str(tmp_path / "snapshot.py"))
    # One queue serves the agent and the critic, in call order.
    model = get_model("mockllm/model", custom_outputs=[
        ModelOutput.for_tool_call("mockllm/model", "request_critique", {"stage": "counting"}),
        ModelOutput.from_content("mockllm/model", "No deviations found."),
        ModelOutput.for_tool_call("mockllm/model", "submit", {"answer": "done"}),
        ModelOutput.from_content("mockllm/model", "- METHODS.md does not name the DESeq2 version"),
        ModelOutput.for_tool_call("mockllm/model", "submit", {"answer": "done"}),
    ])
    task = Task(
        dataset=[Sample(input="# Task\nUse DESeq2 1.28.1.")],
        setup=critic_setup(),
        solver=react(tools=[request_critique()], submit=AgentSubmit(tool=critic_submit())),
        sandbox="local",
    )
    log = eval(task, model=model, display="none", log_dir=str(tmp_path / "logs"))[0]
    assert log.status == "success"
    sample = log.samples[0]
    assert sample.output.completion.endswith("done")
    # react strips submit calls from the final transcript; the tool events keep what the agent saw.
    tools = [event for event in sample.events if event.event == "tool"]
    assert [event.function for event in tools] == ["request_critique", "submit", "submit"]
    assert tools[0].result == "No deviations found."
    assert tools[1].error is not None and "DESeq2 version" in tools[1].error.message
    assert tools[2].error is None and tools[2].result == "done"
    assert [entry["stage"] for entry in sample.store[LOG_KEY]] == ["counting", "pre_submit"]
    assert sample.store[PROMPT_KEY] == "# Task\nUse DESeq2 1.28.1."
    assert "## Stage Critic" in next(message.text for message in sample.messages if message.role == "user")
    notes = (tmp_path / "work" / "critic_notes.md").read_text()
    assert "## counting (critique 1/2)" in notes and "## pre_submit (critique 1/2)" in notes

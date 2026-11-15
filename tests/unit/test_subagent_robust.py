"""v5: an unreadable sandbox reply (truncated tool-support JSON) must not end a sub-agent."""

from __future__ import annotations

import asyncio

import pytest
from inspect_ai.model._call_tools import tool_params
from inspect_ai.tool import Tool, ToolDef, ToolError, tool
from pydantic import BaseModel

from bixbench3.inspect_harness.tools import subagent


class _Reply(BaseModel):
    id: int


@tool
def _flaky_bash() -> Tool:
    async def execute(input: str) -> str:
        """Run a command.

        Args:
          input: Command.
        """
        if input == "flood":
            # what Inspect raises when the 10 MiB output buffer cut the start of the JSON-RPC reply
            _Reply.model_validate_json('Warning: Encountered reference sequence with only gaps\n", "id": 780}')
        return f"ran {input}"

    return execute


def test_robust_tool_keeps_name_parameters_and_arguments() -> None:
    wrapped = subagent._robust(_flaky_bash())
    assert ToolDef(wrapped).name == ToolDef(_flaky_bash()).name
    assert ToolDef(wrapped).parameters == ToolDef(_flaky_bash()).parameters
    params = tool_params({"input": "ls"}, wrapped)  # how Inspect calls it
    assert params == {"input": "ls"}
    assert asyncio.run(wrapped(**params)) == "ran ls"


def test_unreadable_reply_becomes_tool_error() -> None:
    wrapped = subagent._robust(_flaky_bash())
    with pytest.raises(ToolError, match="could not be read"):
        asyncio.run(wrapped(input="flood"))


def test_subagent_tools_are_robust_and_instructions_ask_for_log_redirects() -> None:
    import inspect as pyinspect

    source = pyinspect.getsource(subagent._sub_tools)
    assert source.count("_robust(") == 2 and "bash_session(" in source and "python(" in source
    assert "> step.log 2>&1" in subagent.SUBAGENT_INSTRUCTIONS

"""Experiment v3e: compact snapshot of the agent workspace for the stage critic.

Runs inside the sandbox. Prints the staged input listing, the agent's most recent
code files and the head of each output file, capped to a character budget. It
reads only what the agent itself can read (/data, /workspace/work, /outputs).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

CODE_SUFFIXES = {".py", ".r", ".R", ".sh", ".rmd", ".Rmd", ".sql", ".nf", ".smk"}
TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".tab"}
SKIP_NAMES = {"critic_notes.md"}
MAX_CODE_FILES = 8
CODE_CHARS = 3_000
TABLE_LINES = 6
LINE_CHARS = 300
METHODS_CHARS = 3_000
DATA_ENTRIES = 60


def _read(path: Path, limit: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(limit + 1)
    except OSError as error:
        return f"<unreadable: {error}>"
    return text if len(text) <= limit else text[:limit] + "\n<truncated>"


def _head(path: Path) -> str:
    lines = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(TABLE_LINES):
                line = handle.readline()
                if not line:
                    break
                line = line.rstrip("\n")
                lines.append(line if len(line) <= LINE_CHARS else line[:LINE_CHARS] + " <truncated>")
    except OSError as error:
        return f"<unreadable: {error}>"
    return "\n".join(lines)


def _line_count(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def data_section(data: Path) -> str:
    if not data.exists():
        return "(no staged inputs found)"
    entries = []
    for root, dirs, files in os.walk(data, followlinks=True):
        dirs.sort()
        depth = Path(root).relative_to(data).parts
        if len(depth) > 2:
            dirs[:] = []
            continue
        for name in sorted(files):
            path = Path(root) / name
            try:
                size = path.stat().st_size
            except OSError:
                size = -1
            entries.append(f"{path.relative_to(data)}  ({size} bytes)")
    shown = entries[:DATA_ENTRIES]
    if len(entries) > DATA_ENTRIES:
        shown.append(f"... {len(entries) - DATA_ENTRIES} more files")
    return "\n".join(shown) or "(empty)"


def code_section(work: Path) -> str:
    if not work.exists():
        return "(no ./work directory)"
    files = [
        path for path in work.rglob("*")
        if path.is_file() and path.suffix in CODE_SUFFIXES and path.name not in SKIP_NAMES
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return "(no code files under ./work)"
    blocks = [f"### work/{path.relative_to(work)}\n```\n{_read(path, CODE_CHARS)}\n```" for path in files[:MAX_CODE_FILES]]
    if len(files) > MAX_CODE_FILES:
        blocks.append(f"({len(files) - MAX_CODE_FILES} older code files not shown)")
    return "\n\n".join(blocks)


def outputs_section(outputs: Path) -> str:
    if not outputs.exists():
        return "(no ./outputs directory)"
    files = sorted(path for path in outputs.rglob("*") if path.is_file())
    if not files:
        return "(no output files yet)"
    blocks = []
    for path in files:
        name = path.relative_to(outputs)
        size = path.stat().st_size
        if path.name == "METHODS.md":
            blocks.append(f"### outputs/{name} ({size} bytes)\n{_read(path, METHODS_CHARS)}")
        elif path.suffix.lower() in TABLE_SUFFIXES:
            blocks.append(f"### outputs/{name} ({size} bytes, {_line_count(path)} lines)\n```\n{_head(path)}\n```")
        else:
            blocks.append(f"### outputs/{name} ({size} bytes)")
    return "\n\n".join(blocks)


def snapshot(data: Path, work: Path, outputs: Path, budget: int) -> str:
    text = (
        f"## Staged inputs (./data)\n{data_section(data)}\n\n"
        f"## Output files (./outputs)\n{outputs_section(outputs)}\n\n"
        f"## Most recent code (./work)\n{code_section(work)}\n"
    )
    return text if len(text) <= budget else text[:budget] + "\n<snapshot truncated>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("/data"))
    parser.add_argument("--work", type=Path, default=Path("/workspace/work"))
    parser.add_argument("--outputs", type=Path, default=Path("/outputs"))
    parser.add_argument("--budget", type=int, default=24_000)
    args = parser.parse_args()
    print(snapshot(args.data, args.work, args.outputs, args.budget))


if __name__ == "__main__":
    main()

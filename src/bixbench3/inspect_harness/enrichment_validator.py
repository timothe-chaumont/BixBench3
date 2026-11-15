"""v2f enrichment-validator: structural and method-consistency checks for enrichment outputs.

Only the task prompt (output contract and method guidance) and the agent's own output
files are read. No ground truth, reference outputs or grader-derived values are used.
Severe findings can block the submit tool (a bounded number of times); warnings are
only reported to the agent.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from inspect_ai.agent import AgentSubmit
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, ToolError, tool
from inspect_ai.util import sandbox, store

STORE_KEY = "v2f_enrichment_spec"
BLOCKS_KEY = "v2f_submit_blocks"
MAX_SUBMIT_BLOCKS = 2
LOG_PATH = "/workspace/work/enrichment_validation.jsonl"
BROAD_ROWS_PER_GROUP = 300

_ENRICHMENT_PATTERN = re.compile(
    r"enrich|gsea|pathway|hypergeometric|over-?representation|\bgo\b|gene[ _-]?set",
    re.IGNORECASE,
)
_DE_PATTERN = re.compile(r"deg|deseq|differential", re.IGNORECASE)
_PVALUE_COLUMN = re.compile(r"^(p|p_?value|pval|padj|fdr|q_?value|adj_?p(_?value)?)(_|$)", re.IGNORECASE)
_COUNT_COLUMN = re.compile(r"^(significant_in_gene_set|genes_(total|up|down)|overlap|set_size)", re.IGNORECASE)
_PERCENT_COLUMN = re.compile(r"^percent_", re.IGNORECASE)
_DIRECTIONS = ("non_directional", "up", "down")
_PLACEHOLDER = re.compile(r"\b(TODO|dummy|synthetic|placeholder|lorem)\b", re.IGNORECASE)
_THRESHOLD = re.compile(r"FDR\s*(?:below|<|less than)\s*(\d*\.\d+|\d+\s*%)", re.IGNORECASE)
_SIZE_RANGE = re.compile(r"gene sets with (\d+) to (\d+)", re.IGNORECASE)


@dataclass
class ArtifactSpec:
    artifact_id: str
    path: str
    row_key: str | None = None
    required_columns: list[str] = field(default_factory=list)
    key_template: list[str] = field(default_factory=list)
    description: str = ""
    fdr_threshold: float | None = None
    crossed_grid: bool = False
    directions: list[str] = field(default_factory=list)


@dataclass
class Finding:
    artifact: str
    severity: str  # "severe" | "warning"
    message: str


def parse_output_contract(prompt: str) -> list[ArtifactSpec]:
    """Parse the "Required Outputs" section of a BixBench3 task prompt."""
    section = prompt.split("## Required Outputs", 1)
    if len(section) < 2:
        return []
    body = re.split(r"\n## (?!#)", section[1], maxsplit=1)[0]
    specs: list[ArtifactSpec] = []
    for block in re.split(r"\n### ", "\n" + body)[1:]:
        header, _, text = block.partition("\n")
        artifact_id = header.strip().strip("`")
        path_match = re.search(r"- Path: `([^`]+)`", text)
        if not path_match:
            continue
        spec = ArtifactSpec(artifact_id=artifact_id, path=path_match.group(1))
        if row_key := re.search(r"- Row key: `([^`]+)`", text):
            spec.row_key = row_key.group(1)
        if required := re.search(r"- Required columns: (.+)", text):
            spec.required_columns = re.findall(r"`([^`]+)`", required.group(1))
        if template := re.search(r"must be formatted as ([A-Za-z_]+(?:\|[A-Za-z_]+)+)", text):
            spec.key_template = template.group(1).split("|")
        description = re.search(r"- Description: (.+)", text)
        spec.description = description.group(1) if description else ""
        if threshold := _THRESHOLD.search(spec.description):
            spec.fdr_threshold = _parse_threshold(threshold.group(1))
        spec.crossed_grid = "crossed with" in text
        spec.directions = [d for d in _DIRECTIONS if re.search(rf"\b{d}\b", text)]
        specs.append(spec)
    return specs


def gene_set_size_limits(prompt: str) -> tuple[int, int] | None:
    match = _SIZE_RANGE.search(prompt)
    return (int(match.group(1)), int(match.group(2))) if match else None


def enrichment_targets(specs: list[ArtifactSpec]) -> list[ArtifactSpec]:
    return [
        spec
        for spec in specs
        if _ENRICHMENT_PATTERN.search(spec.artifact_id + " " + spec.description)
        and not _DE_PATTERN.search(spec.artifact_id)
    ]


def validate(
    specs: list[ArtifactSpec],
    files: dict[str, str | None],
    size_limits: tuple[int, int] | None = None,
) -> list[Finding]:
    """Validate enrichment artifacts. ``files`` maps contract path -> text (None if missing)."""
    findings: list[Finding] = []
    contrasts = _de_contrasts(specs, files)
    for spec in enrichment_targets(specs):
        findings.extend(_validate_one(spec, files.get(spec.path), contrasts, size_limits))
    return findings


def _validate_one(
    spec: ArtifactSpec,
    text: str | None,
    contrasts: set[tuple[str, str]] | None,
    size_limits: tuple[int, int] | None,
) -> list[Finding]:
    out: list[Finding] = []

    def add(severity: str, message: str) -> None:
        out.append(Finding(spec.artifact_id, severity, message))

    if text is None:
        add("severe", f"{spec.path} does not exist.")
        return out
    if not text.strip():
        add("severe", f"{spec.path} is empty.")
        return out
    delimiter = "\t" if spec.path.endswith((".tsv", ".txt")) else ","
    try:
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
        header = next(csv.reader(io.StringIO(text), delimiter=delimiter))
    except (csv.Error, StopIteration) as error:
        add("severe", f"{spec.path} does not parse as {'TSV' if delimiter == chr(9) else 'CSV'}: {error}")
        return out
    if not rows:
        add("warning", f"{spec.path} has a header but no data rows. Check that this is a real result, not a failed step.")
        return out

    missing = [c for c in spec.required_columns if c not in header]
    if missing:
        add("severe", f"missing required columns: {', '.join(missing)}.")
    if spec.row_key and header[0] != spec.row_key:
        add("severe", f"first column is '{header[0]}' but the row key '{spec.row_key}' must be the first column.")

    key = spec.row_key if spec.row_key in header else header[0]
    keys = [(row.get(key) or "").strip() for row in rows]
    empty = sum(1 for k in keys if not k)
    if empty:
        add("severe", f"{empty} rows have an empty '{key}'.")
    duplicates = len(keys) - len(set(keys))
    if duplicates:
        add("severe", f"{duplicates} duplicate '{key}' values (one row per contrast/direction/gene set is required).")

    if spec.key_template:
        bad_shape, bad_parts = 0, 0
        for row, value in zip(rows, keys, strict=True):
            parts = value.split("|")
            if len(parts) != len(spec.key_template):
                bad_shape += 1
                continue
            for name, part in zip(spec.key_template, parts, strict=True):
                if name in row and (row[name] or "").strip() != part:
                    bad_parts += 1
                    break
        template = "|".join(spec.key_template)
        if bad_shape:
            add("severe", f"{bad_shape} '{key}' values do not have the form {template}.")
        if bad_parts:
            add("severe", f"{bad_parts} '{key}' values disagree with their own {', '.join(n for n in spec.key_template if n in header)} columns.")

    placeholders = sum(1 for row in rows for v in row.values() if isinstance(v, str) and _PLACEHOLDER.search(v))
    if placeholders:
        add("severe", f"{placeholders} cells contain placeholder text (TODO/dummy/synthetic/placeholder).")

    if "gene_set" in header:
        blank_sets = sum(1 for row in rows if not (row.get("gene_set") or "").strip())
        if blank_sets:
            add("severe", f"{blank_sets} rows have an empty gene_set name.")

    if "direction" in header and spec.directions:
        bad = sorted({(row.get("direction") or "").strip() for row in rows} - set(spec.directions))
        if bad:
            add("severe", f"invalid direction labels {bad}; allowed: {spec.directions}.")

    p_columns = [c for c in header if _PVALUE_COLUMN.match(c)]
    for column in p_columns:
        nonnumeric, outside, blank = 0, 0, 0
        for row in rows:
            raw = (row.get(column) or "").strip()
            if raw == "" or raw.upper() in {"NA", "NAN"}:
                blank += 1
                continue
            value = _to_float(raw)
            if value is None:
                nonnumeric += 1
            elif not 0.0 <= value <= 1.0:
                outside += 1
        if nonnumeric:
            add("severe", f"column '{column}' has {nonnumeric} non-numeric values.")
        if outside:
            add("severe", f"column '{column}' has {outside} values outside [0, 1].")
        if blank:
            add("warning", f"column '{column}' has {blank} blank/NA values. If a test had no overlap, its p-value is 1, not missing.")

    _fdr_checks(spec, rows, header, add)

    for column in (c for c in header if _COUNT_COLUMN.match(c)):
        bad = sum(1 for row in rows if not _is_nonneg_int((row.get(column) or "").strip()))
        if bad:
            add("warning", f"count column '{column}' has {bad} values that are not non-negative integers.")
    for column in (c for c in header if _PERCENT_COLUMN.match(c)):
        bad = sum(1 for row in rows if (v := _to_float(row.get(column) or "")) is None or not 0 <= v <= 100)
        if bad:
            add("warning", f"percentage column '{column}' has {bad} values outside [0, 100].")

    if size_limits and "genes_total" in header:
        low, high = size_limits
        bad = sum(1 for row in rows if (v := _to_float(row.get("genes_total") or "")) is not None and not low <= v <= high)
        if bad:
            add("warning", f"{bad} rows have genes_total outside the {low}-{high} gene-set size range in the method guidance.")

    if contrasts is not None and {"timepoint", "concentration"} <= set(header):
        seen = {((row.get("timepoint") or "").strip(), (row.get("concentration") or "").strip()) for row in rows}
        unknown = sorted(seen - contrasts)
        if unknown:
            add("warning", f"timepoint/concentration pairs not present in the DE output: {unknown[:8]}.")

    group_columns = [c for c in ("timepoint", "concentration", "direction") if c in header]
    if group_columns and spec.fdr_threshold is not None:
        groups: dict[tuple[str, ...], int] = {}
        for row in rows:
            group = tuple((row.get(c) or "").strip() for c in group_columns)
            groups[group] = groups.get(group, 0) + 1
        broad = {"|".join(g): n for g, n in groups.items() if n > BROAD_ROWS_PER_GROUP}
        if broad:
            add("warning", f"suspiciously broad results (> {BROAD_ROWS_PER_GROUP} significant gene sets in one contrast/direction): {dict(list(broad.items())[:5])}. Re-check the universe, gene-set collection, size filter and FDR cutoff against the method guidance.")

    if spec.crossed_grid and "gene_set" in header:
        contrast_columns = [c for c in ("timepoint", "concentration") if c in header]
        per_contrast: dict[tuple[str, ...], set[str]] = {}
        for row in rows:
            per_contrast.setdefault(tuple((row.get(c) or "").strip() for c in contrast_columns), set()).add((row.get("gene_set") or "").strip())
        sizes = {len(v) for v in per_contrast.values()}
        if len(sizes) > 1:
            add("warning", f"the contract describes a full contrast x gene-set grid, but contrasts have different numbers of gene sets: {sorted(sizes)}.")
    return out


def _fdr_checks(spec: ArtifactSpec, rows: list[dict[str, str]], header: list[str], add) -> None:
    for fdr_column in header:
        prefix = re.match(r"^(fdr|padj|q_?value)", fdr_column, re.IGNORECASE)
        if not prefix:
            continue
        suffix = fdr_column[prefix.end():]
        p_column = next((c for c in (f"p_value{suffix}", f"pvalue{suffix}", f"p{suffix}") if c in header), None)
        if spec.fdr_threshold is not None:
            above = sum(1 for row in rows if (v := _to_float(row.get(fdr_column) or "")) is not None and v >= spec.fdr_threshold)
            if above:
                add("severe", f"{above} rows have {fdr_column} >= {spec.fdr_threshold}, but the contract asks only for results with FDR below {spec.fdr_threshold}.")
        if p_column:
            below = sum(
                1
                for row in rows
                if (f := _to_float(row.get(fdr_column) or "")) is not None
                and (p := _to_float(row.get(p_column) or "")) is not None
                and f + 1e-12 < p
            )
            if below:
                add("warning", f"{below} rows have {fdr_column} smaller than {p_column}; Benjamini-Hochberg adjusted values cannot be below the raw p-value. Check for swapped columns.")
    if spec.fdr_threshold is not None and "significant_in_gene_set" in header:
        zero = sum(1 for row in rows if (row.get("significant_in_gene_set") or "").strip() in {"0", "0.0"})
        if zero:
            add("warning", f"{zero} reported significant rows have significant_in_gene_set = 0; an over-representation result with no overlapping genes cannot be significant.")


def _de_contrasts(specs: list[ArtifactSpec], files: dict[str, str | None]) -> set[tuple[str, str]] | None:
    for spec in specs:
        if not _DE_PATTERN.search(spec.artifact_id) or not {"timepoint", "concentration"} <= set(spec.required_columns):
            continue
        text = files.get(spec.path)
        if not text:
            return None
        delimiter = "\t" if spec.path.endswith((".tsv", ".txt")) else ","
        try:
            return {
                ((r.get("timepoint") or "").strip(), (r.get("concentration") or "").strip())
                for r in csv.DictReader(io.StringIO(text), delimiter=delimiter)
            }
        except csv.Error:
            return None
    return None


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "Enrichment validation passed: no structural or method-consistency issues found."
    lines = []
    for severity in ("severe", "warning"):
        items = [f for f in findings if f.severity == severity]
        if items:
            lines.append(f"{severity.upper()} ({len(items)}):")
            lines.extend(f"- [{f.artifact}] {f.message}" for f in items)
    return "\n".join(lines)


def _parse_threshold(raw: str) -> float:
    raw = raw.strip()
    return float(raw.rstrip("% ")) / 100 if raw.endswith("%") else float(raw)


def _to_float(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _is_nonneg_int(raw: str) -> bool:
    value = _to_float(raw)
    return value is not None and value >= 0 and float(value).is_integer()


# --------------------------------------------------------------------------- inspect glue

NOTE = """
## Experiment Note: Enrichment Output Validator

This run includes an automatic validator for the enrichment outputs ({targets}). It checks structure and consistency with the output contract and method guidance only (required columns, row keys, labels, p-value/FDR ranges, stated FDR filters, count fields). It does not know the correct answers.

- Call `validate_enrichment_outputs()` after you write or update any enrichment output, and fix what it reports.
- The `submit()` tool runs the same validator. It refuses submission when there are severe issues (at most {max_blocks} times), and reports warnings without blocking.
"""


@solver
def enrichment_validator_setup() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate
        prompt = state.input_text
        specs = parse_output_contract(prompt)
        targets = enrichment_targets(specs)
        store().set(
            STORE_KEY,
            {
                "specs": [spec.__dict__ for spec in specs],
                "size_limits": gene_set_size_limits(prompt),
            },
        )
        store().set(BLOCKS_KEY, 0)
        if targets:
            note = NOTE.format(
                targets=", ".join(f"`{t.path}`" for t in targets),
                max_blocks=MAX_SUBMIT_BLOCKS,
            )
            state.user_prompt.text = state.user_prompt.text.rstrip() + "\n" + note
        return state

    return solve


async def run_validation(trigger: str) -> tuple[list[Finding], str]:
    saved = store().get(STORE_KEY) or {}
    specs = [ArtifactSpec(**raw) for raw in saved.get("specs", [])]
    size_limits = tuple(saved["size_limits"]) if saved.get("size_limits") else None
    needed = {spec.path for spec in enrichment_targets(specs)}
    needed |= {spec.path for spec in specs if _DE_PATTERN.search(spec.artifact_id)}
    files: dict[str, str | None] = {}
    for path in needed:
        files[path] = await _read_output(path)
    findings = validate(specs, files, size_limits)  # type: ignore[arg-type]
    report = format_report(findings)
    await _log(trigger, findings)
    return findings, report


async def _read_output(contract_path: str) -> str | None:
    relative = contract_path.split("outputs/", 1)[-1]
    try:
        return await sandbox().read_file(f"/outputs/{relative}")
    except (FileNotFoundError, UnicodeDecodeError, IsADirectoryError, PermissionError):
        return None
    except Exception:  # noqa: BLE001 - sandbox errors must never crash the run
        return None


async def _log(trigger: str, findings: list[Finding]) -> None:
    record = {
        "time": datetime.now(UTC).isoformat(),
        "trigger": trigger,
        "severe": sum(f.severity == "severe" for f in findings),
        "warnings": sum(f.severity == "warning" for f in findings),
        "findings": [f.__dict__ for f in findings],
    }
    try:
        await sandbox().exec(
            ["sh", "-c", f"mkdir -p /workspace/work && cat >> {LOG_PATH}"],
            input=json.dumps(record) + "\n",
        )
    except Exception:  # noqa: BLE001 - logging is best effort
        pass


@tool
def validate_enrichment_outputs() -> Tool:
    async def execute() -> str:
        """Check the enrichment output files against the output contract and method guidance.

        Reports severe issues (which will block submit) and warnings. Checks structure and
        method consistency only; it does not know the correct results.

        Returns:
            A report of issues found, or a pass message.
        """
        _, report = await run_validation("tool")
        return report

    return execute


@tool(name="submit")
def validated_submit() -> Tool:
    async def execute(answer: str) -> str:
        """Submit your final answer once all required outputs and METHODS.md are written.

        The enrichment validator runs first. Severe issues refuse the submission (a limited
        number of times) so you can fix them; warnings are reported but do not block.

        Args:
            answer: Short summary of the completed analysis.

        Returns:
            The submitted answer.
        """
        findings, report = await run_validation("submit")
        severe = [f for f in findings if f.severity == "severe"]
        blocks = int(store().get(BLOCKS_KEY) or 0)
        if severe and blocks < MAX_SUBMIT_BLOCKS:
            store().set(BLOCKS_KEY, blocks + 1)
            raise ToolError(
                "Submission refused by the enrichment validator "
                f"({blocks + 1}/{MAX_SUBMIT_BLOCKS}). Fix these issues, then call submit() again.\n" + report
            )
        return answer

    return execute


def validated_agent_submit() -> AgentSubmit:
    return AgentSubmit(tool=validated_submit())

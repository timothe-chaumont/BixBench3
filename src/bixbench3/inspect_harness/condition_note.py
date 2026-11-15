"""v3d statistical-background-repair: append a process-level experiment note to the task prompt.

The note contains only setup and method guidance derived from the public task prompt
and from our own earlier run logs. It never contains ground truth, reference outputs
or grader-derived values.
"""

from __future__ import annotations

from inspect_ai.solver import Generate, Solver, TaskState, solver

CONDITION = "v3d-statistical-background-repair"

TASK_NOTES: dict[str, str] = {
    "10.1016_j.crtox.2021.01.003_v1": '## Experiment Note: Curated DNA-Damage Enrichment Statistics\n\nFollow the method guidance exactly when producing `outputs/dna_damage_enrichment.csv`:\n- Gene sets: parse the staged workbook, exclude `GO_CELLULAR_RESPONSE_TO_DNA_DAMAGE_STIMULUS` and confirm that 88 sets remain. Check whether the workbook\'s gene identifiers are human or mouse symbols, and map the DE results into the same namespace with the same ortholog mapping used for the pathway analyses.\n- Background (universe): all genes appearing in the 88 retained sets (their union), as the guidance states. Restrict each significant-gene list to genes in this background before counting; genes outside the background cannot be drawn.\n- Significant genes per contrast: DESeq2 padj < 0.10, tested three ways: non-directional (all), up (log2FoldChange > 0) and down (log2FoldChange < 0). Count each gene once; collapse multiple probes per gene.\n- Test: one-sided upper-tail hypergeometric, P(X >= overlap) = `phyper(overlap - 1, set_size, N - set_size, n_significant_in_background, lower.tail = FALSE)`, where N is the background size.\n- Correction: Benjamini-Hochberg across the 88 sets within each contrast x direction.\n- Rows: all 13 tested contrasts x 88 sets, not filtered by significance. Where there is no overlap, the hypergeometric p-value is 1 and the count is 0; write these values rather than leaving cells blank.\n- The guidance says to use "the same hypergeometric overrepresentation procedure" as the pathway step. If PIANO is available, `runGSAhyper(genes, universe = background, gsc = ...)` gives this directly.\n- Sanity-check before writing: p-values in [0, 1], each FDR >= its raw p-value, counts no larger than the set size or the number of significant genes.\n',
}

GENERIC_NOTE = '## Experiment Note: Statistical Background\n\nFor every reported p-value/FDR, use the background (universe), test (e.g. one-sided upper-tail hypergeometric) and multiple-testing correction that the method guidance states. Restrict significant genes to the background, count each gene once, and correct within each contrast x direction. Sanity-check p-value ranges and that each FDR is at least its raw p-value.'


def note_for(task_id: str) -> str:
    return TASK_NOTES.get(task_id, GENERIC_NOTE)


@solver
def condition_note_setup() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate
        task_id = str((state.metadata or {}).get("task_id") or state.sample_id)
        state.user_prompt.text = state.user_prompt.text.rstrip() + "\n\n" + note_for(task_id).strip() + "\n"
        return state

    return solve

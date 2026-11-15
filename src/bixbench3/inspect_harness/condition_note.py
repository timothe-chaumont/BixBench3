"""v3c enrichment-precision: append a process-level experiment note to the task prompt.

The note contains only setup and method guidance derived from the public task prompt
and from our own earlier run logs. It never contains ground truth, reference outputs
or grader-derived values.
"""

from __future__ import annotations

from inspect_ai.solver import Generate, Solver, TaskState, solver

CONDITION = "v3c-enrichment-precision"

TASK_NOTES: dict[str, str] = {
    "10.1016_j.crtox.2021.01.003_v1": '## Experiment Note: Hypergeometric Pathway Over-Representation\n\nApply the method guidance strictly when producing `outputs/hypergeometric_pathway_enrichment.csv`:\n- Gene sets: only the MSigDB v6.2 canonical pathway collections the guidance names (KEGG, Reactome, Hallmark, BioCarta, NABA, PID and other canonical pathways). Do not add other collections, such as chemical and genetic perturbations, GO, motif or computational sets.\n- Size filter: keep gene sets with 5 to 500 genes after mapping to the universe (the same filter as the pre-ranked analysis). Apply it before testing and before multiple-testing correction.\n- Universe: the human genes that represent the probes actually tested by DESeq2 after mouse-to-human mapping, each gene counted once. The significant genes must be a subset of the universe. Collapse multiple probes per gene so that no gene is counted twice.\n- Significant genes per timepoint x concentration: DESeq2 padj < 0.10, tested three ways: `non_directional` (all), `up` (log2FoldChange > 0) and `down` (log2FoldChange < 0).\n- Test: one-sided upper-tail hypergeometric, P(X >= overlap), e.g. `phyper(overlap - 1, set_size, universe_size - set_size, n_significant, lower.tail = FALSE)`. Every size-filtered gene set is part of the correction, including sets with zero overlap (p = 1).\n- Correction: Benjamini-Hochberg across all tested gene sets within each contrast x direction. Report only rows with FDR < 0.10.\n- PIANO\'s `runGSAhyper(genes, universe = ..., gsc = ..., gsSizeLim = c(5, 500), adjMethod = "fdr")` implements this test if PIANO is available in your environment.\n- Before writing, sanity-check the number of significant rows per contrast/direction against the number of gene sets tested, and that no reported row has `significant_in_gene_set = 0`.\n',
}

GENERIC_NOTE = '## Experiment Note: Enrichment Precision\n\nFor over-representation / enrichment outputs, apply exactly the gene-set collections, gene-set size limits, universe (genes actually tested, each counted once), significance definition, one-sided test and multiple-testing correction stated in the method guidance. Apply the size filter before correction and report only rows passing the stated FDR cutoff.'


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

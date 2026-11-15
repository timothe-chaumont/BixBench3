"""v3a named-tool-repair: append a process-level experiment note to the task prompt.

The note contains only setup and method guidance derived from the public task prompt
and from our own earlier run logs. It never contains ground truth, reference outputs
or grader-derived values.
"""

from __future__ import annotations

from inspect_ai.solver import Generate, Solver, TaskState, solver

CONDITION = "v3a-named-tool-repair"

TASK_NOTES: dict[str, str] = {
    "10.1016_j.crtox.2021.01.003_v1": '## Experiment Note: Making PIANO 2.4.0 Work\n\nThe method guidance requires PIANO 2.4.0 pre-ranked enrichment. Do not substitute another GSEA implementation (gseapy, fgsea, clusterProfiler, a custom permutation test) unless PIANO 2.4.0 is proven impossible after the steps below. If you substitute, disclose it in METHODS.md.\n\nKnown setup facts for this sandbox:\n- The system R is 4.2.x (Bioconductor 3.16). PIANO 2.4.0 belongs to Bioconductor 3.11 / R 4.0.x, so `BiocManager::install("piano")` on the system R installs a different version, and compiling its dependencies (fgsea, igraph) from source has failed here before.\n- Bioconda ships a prebuilt `bioconductor-piano=2.4.0`. Create an isolated R 4.0 environment with micromamba (conda-forge and bioconda are pre-approved) instead of compiling:\n  `micromamba create -y -n piano240 -c conda-forge -c bioconda r-base=4.0.2 bioconductor-piano=2.4.0`\n  then check: `micromamba run -n piano240 Rscript -e \'packageVersion("piano")\'` must print 2.4.0. If the solver cannot satisfy `r-base=4.0.2`, retry with `r-base=4.0` and record the exact version installed.\n- Start the environment creation early, in the background, with its output written to a log file under ./work. Keep working on counting and DESeq2 meanwhile, and check on it with a single long wait, not frequent polling.\n- Run the PIANO script with `micromamba run -n piano240 Rscript work/<script>.R`. Exchange data with the rest of the workflow through CSV/TSV files in ./work.\n\nUsing PIANO as the guidance describes:\n- Once per timepoint x concentration contrast: `runGSA(geneLevelStats = <named numeric vector of DESeq2 Wald statistics, one value per human gene>, gsc = loadGSC(<two-column data.frame: gene, gene set>), geneSetStat = "mean", signifMethod = "geneSampling", adjMethod = "fdr", gsSizeLim = c(5, 500), nPerm = 10000)`. Set and record a random seed. Document how multiple probes or orthologs per human gene were collapsed to one value.\n- Read results with `GSAsummaryTable(res)`. Inspect its column names: the directional ("distinct-directional") statistic and its up/down p-values and adjusted p-values give the `up` and `down` rows. Gene counts in the set and up/down come from the same table.\n- Report only rows with directional FDR < 0.10 in the matching direction.\n',
}

GENERIC_NOTE = '## Experiment Note: Use the Named Tools\n\nThe method guidance names specific tools and versions. Do not substitute another implementation for a named statistical or enrichment tool unless it is proven impossible to run. Version conflicts with the system R/Python are not proof: create an isolated environment with micromamba (conda-forge/bioconda are pre-approved) pinned to the named version, or install from the Bioconductor/CRAN archive. Start long installs early in the background and check them with a single long wait. Disclose any remaining substitution in METHODS.md.'


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

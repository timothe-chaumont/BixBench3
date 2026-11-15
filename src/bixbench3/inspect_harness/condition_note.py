"""v3b reference-resource-repair: append a process-level experiment note to the task prompt.

The note contains only setup and method guidance derived from the public task prompt
and from our own earlier run logs. It never contains ground truth, reference outputs
or grader-derived values.
"""

from __future__ import annotations

from inspect_ai.solver import Generate, Solver, TaskState, solver

CONDITION = "v3b-reference-resource-repair"

TASK_NOTES: dict[str, str] = {
    "10.1016_j.crtox.2021.01.003_v1": '## Experiment Note: BioMart / Ensembl 100 Access\n\nThe method guidance requires mouse-to-human ortholog mapping with biomaRt against the Ensembl 100 archive. Do not substitute another ortholog source (babelgene, HCOP, homologene, symbol matching) unless the steps below have failed. If you substitute, disclose it in METHODS.md.\n\nKnown setup facts for this sandbox:\n- All outbound traffic goes through an allow-list proxy (squid). An error such as `CONNECT tunnel failed, response 403` or a response header `X-Squid-Error: ERR_ACCESS_DENIED` for `apr2020.archive.ensembl.org` or `www.ensembl.org` means the proxy has not allow-listed that host yet. It is not an Ensembl outage and not a reason to switch methods.\n- Fix: call `request_web_access(url="https://apr2020.archive.ensembl.org/biomart/martservice", reason="biomaRt ortholog mapping against the Ensembl 100 archive, required by the method guidance")`. If the decision says `delivery: "allowlist"`, rerun the query. `useEnsembl(..., version = 100)` may first contact `www.ensembl.org` to look up archives; request that host too, or connect to the archive directly with `useMart(biomart = "ENSEMBL_MART_ENSEMBL", dataset = "mmusculus_gene_ensembl", host = "https://apr2020.archive.ensembl.org")`.\n- Client version: biomaRt 2.44.x belongs to Bioconductor 3.11 / R 4.0. Bioconda has `bioconductor-biomart=2.44.0`, which can go into an isolated R 4.0 environment with micromamba (`micromamba create -y -n biomart244 -c conda-forge -c bioconda r-base=4.0.2 bioconductor-biomart=2.44.0`). The ortholog content comes from the Ensembl 100 server, so the archive host matters more than the client version. Record the client version you actually used.\n- Query once and cache the result under ./work: mouse `ensembl_gene_id` and `external_gene_name` (or `mgi_symbol`) with `hsapiens_homolog_ensembl_gene`, `hsapiens_homolog_associated_gene_name` and `hsapiens_homolog_orthology_type`. Map the manifest\'s gene symbols, and document how one-to-many and many-to-one orthologs are handled.\n- If the archive host is denied after a request, the next-best source with the same Ensembl 100 content is the Compara homology dump at `https://ftp.ensembl.org/pub/release-100/tsv/ensembl-compara/homologies/` (request the exact file URL via `request_web_access`). Use other resources only after both fail.\n',
}

GENERIC_NOTE = '## Experiment Note: Reference Resources Behind the Proxy\n\nAll outbound traffic goes through an allow-list proxy. A `403` / `CONNECT tunnel failed` / `X-Squid-Error: ERR_ACCESS_DENIED` error means the host is not allow-listed yet. It is not an outage and not a reason to switch resources. Call `request_web_access(url, reason)` with the exact endpoint of the annotation, ortholog or gene-set resource the guidance names, then retry. Use the exact release/version named; cache query results under ./work. Disclose any substitution in METHODS.md.'


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

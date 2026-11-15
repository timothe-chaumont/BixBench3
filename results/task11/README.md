# Task 11 results

**Task 11** (`10.1016_j.crtox.2021.01.003_v1`): TempO-Seq transcriptomics of mouse liver after 1,4-dioxane exposure. The
agent must produce 5 artifacts: filtered counts, DESeq2 DEGs, PIANO preranked GSEA, hypergeometric pathway enrichment and
DNA-damage enrichment. The official score is the mean artifact score. Model: GPT-5.4 Mini at `xhigh`.

## Baseline: Sherlock reproduces the GCP reference

| Setup | Runs | Official score | Source |
|---|---|---|---|
| GCP, 8 vCPU / 32 GB | 1 | 0.589 | [`iterations/baseline-task11`](../../iterations/baseline-task11/) |
| GCP, 6 vCPU / 32 GB | 1 | 0.679 | [`iterations/baseline-task11-6vcpu`](../../iterations/baseline-task11-6vcpu/) |
| **Sherlock, 6 CPU / 32 GB, AMD EPYC 7502** | **4** | **0.630 ± 0.069** (0.654, 0.567, 0.661, 0.636) | [`exp/t11-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t11-baseline) |

The Sherlock runner ([`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner)) runs the unchanged harness on Stanford's HPC
cluster with the GCP VM shape. It took several fixes to reach parity:

- **apt:** apt runs as root inside the fakeroot sandbox.
- **Memory and CPU views:** `/proc/meminfo` and `cpuinfo` report the job's limits.
- **Isolation:** the sandbox cannot signal host processes.
- **Hardware:** every run is pinned to one CPU generation.

The first, unfixed attempt (3 CPU / 16 GB on Broadwell nodes, apt broken) was cancelled as invalid: 3 of its 4 runs hit the
memory limit. With the fixes, Sherlock ran about 25 runs of 6 CPU at once. A 32-vCPU GCP quota allows 5. The GCP 6-vCPU score (0.679) is
inside the Sherlock 95% CI.

## Batch 1 harness variants on GCP (single runs, 6 vCPU)

| Variant | Branch | Idea | Score | Status |
|---|---|---|---|---|
| v2f enrichment validator | [`exp/v2f`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v2f) | Contract and method checks on the 3 enrichment files; `submit()` refuses serious problems at most twice | 0.582 | completed |
| v3c enrichment precision | [`exp/v3c`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3c) | Note applying the hypergeometric guidance strictly (canonical sets, 5–500 size filter, tested-gene background) | 0.592 | completed |
| v3a named-tool repair | [`exp/v3a`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3a) | Note on installing PIANO in a separate R 4.0 environment | – | cancelled (moved to Sherlock) |
| v3b reference-resource repair | [`exp/v3b`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3b) | Note on requesting web access to the Ensembl 100 archive | – | cancelled (moved to Sherlock) |
| v3d statistical-background repair | [`exp/v3d`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3d) | Note on the DNA-damage enrichment background and correction | – | cancelled (moved to Sherlock) |

Per-artifact scores of the completed runs:

| Artifact | v2f | v3c |
|---|---|---|
| Filtered counts | 0.99 | 0.99 |
| DESeq2 DEGs | 0.91 | 0.90 |
| PIANO GSEA | 0.26 | 0.33 |
| Hypergeometric enrichment | 0.18 | 0.19 |
| DNA-damage enrichment | 0.57 | 0.56 |

These are single stochastic runs, so they cannot rank the variants. They do show where task 11 is hard: counts and DEGs are
nearly solved, while the enrichment artifacts stay low. After these runs the team moved to repeated runs on Sherlock and
to task 9 (see [task 9 results](../task9/)).

## Task 11 "lite" proxy study

Timothé's study asks whether a 30-minute downstream-only version of task 11 could stand in for the 2-hour full run. Feasibility is
demonstrated, but ranking preservation is not established. See
[`iterations/proxy-validation-task11`](../../iterations/proxy-validation-task11/).

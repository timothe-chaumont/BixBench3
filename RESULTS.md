# Results: `t9-env-reviewer` (+ Env + Artifact reviewer)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-reviewer.md`](experiments/t9-env-reviewer.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.757 ± 0.291** | 0.500 | 0.929 |
| Mean artifact score (`grade.json` score) | 0.830 ± 0.174 | 0.677 | 0.934 |
| OpenAI cost per run (USD) | 2.24 | 1.49 | 3.48 |
| Wall time per run (h) | 1.76 | 1.19 | 2.39 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Preinstalled env 0.57 / $2.08, + Env + Sub-agents (v4) 0.46 / $10.14. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `e0366e900c` | 0.929 | 0.932 | 0.94 | inefficient_analysis | $1.52 | 1.19 h | – |
| `5097b3eeb4` | 0.500 | 0.677 | 0.95 | inefficient_analysis | $3.13 | 2.39 h | – |
| `f757c71e69` | 0.929 | 0.932 | 0.97 | none | $1.49 | 1.65 h | – |
| `673af775f2` | 0.500 | 0.677 | 0.98 | none | $1.60 | 1.38 h | – |
| `3912f441dd` | 0.929 | 0.934 | 0.95 | none | $3.48 | 2.19 h | – |

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.80 | 0.52–0.99 | 3/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.92 | 0.82–0.99 | 5/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.95 | 0.90–0.99 | 5/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.85 | 0.67–0.97 | 3/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.56 | 0.13–0.87 | 3/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.71 | 0.32–0.97 | 3/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.91 | 0.79–0.99 | 3/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.95 | 0.90–0.98 | 5/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.91 | 0.86–0.94 | 5/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.92 | 0.87–0.96 | 5/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.92 | 0.82–0.99 | 5/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.89 | 0.76–0.98 | 3/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.34 | 0.12–0.48 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

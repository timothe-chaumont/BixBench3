# Results: `t9-env` (+ Preinstalled env)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env.md`](experiments/t9-env.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.571 ± 0.452** | 0.071 | 0.929 |
| Mean artifact score (`grade.json` score) | 0.690 ± 0.315 | 0.334 | 0.931 |
| OpenAI cost per run (USD) | 2.08 | 1.38 | 2.51 |
| Wall time per run (h) | 1.82 | 1.24 | 2.45 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env + Artifact reviewer 0.76 / $2.24, + Env + Sub-agents (v4) 0.46 / $10.14. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `d7272f0ec9` | 0.929 | 0.931 | 0.94 | none | $2.20 | 1.78 h | – |
| `c9de8c42af` | 0.429 | 0.575 | 0.87 | inefficient_analysis | $2.20 | 2.45 h | – |
| `d33fc40b28` | 0.071 | 0.334 | 0.92 | none | $1.38 | 1.24 h | – |
| `94f6c0254c` | 0.929 | 0.931 | 0.97 | none | $2.12 | 1.81 h | – |
| `0a7ce439b0` | 0.500 | 0.677 | 0.85 | inefficient_analysis, repetitive_retry_loop | $2.51 | 1.80 h | – |

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.64 | 0.21–0.99 | 2/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.79 | 0.32–0.99 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.86 | 0.50–0.99 | 4/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.69 | 0.21–0.97 | 2/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.37 | 0.00–0.87 | 2/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.45 | 0.00–0.97 | 2/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.80 | 0.47–0.99 | 2/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.83 | 0.39–0.98 | 4/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.82 | 0.46–0.94 | 4/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.66 | 0.00–1.00 | 3/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.80 | 0.37–0.99 | 4/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.76 | 0.29–0.98 | 2/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.20 | 0.00–0.48 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

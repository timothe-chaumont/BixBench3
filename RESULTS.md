# Results: `t9-env-reviewer-pastdev` (+ Env + Reviewer + past.dev)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-reviewer-pastdev.md`](experiments/t9-env-reviewer-pastdev.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.500 ± 0.376** | 0.071 | 0.929 |
| Mean artifact score (`grade.json` score) | 0.663 ± 0.265 | 0.333 | 0.930 |
| OpenAI cost per run (USD) | 2.13 | 1.83 | 2.46 |
| Wall time per run (h) | 2.32 | 1.86 | 2.95 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env 0.57 / $2.08, + Env + Reviewer 0.76 / $2.24, + Env + Dual reviewer + past.dev 0.24 / $2.00, + Env + Sub-agents (v4) 0.46 / $10.14, + Env + Sub-agents v5 0.41 / $3.60, + Env + Sub-agents v5 + past.dev 0.50 / $3.21. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `04f6680429` | 0.500 | 0.677 | 0.96 | none | $2.14 | 2.95 h | – |
| `9f9eb36036` | 0.929 | 0.930 | 0.94 | inefficient_analysis | $2.46 | 2.31 h | – |
| `c8b35747b9` | 0.071 | 0.333 | 0.95 | inefficient_analysis | $1.83 | 1.99 h | – |
| `156803f975` | 0.500 | 0.677 | 0.90 | inefficient_analysis | $2.29 | 2.47 h | – |
| `bf7cb92303` | 0.500 | 0.701 | 0.90 | inefficient_analysis | $1.96 | 1.86 h | – |

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.55 | 0.21–0.99 | 1/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.75 | 0.32–0.99 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.84 | 0.50–0.99 | 4/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.63 | 0.20–0.97 | 1/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.24 | 0.00–0.83 | 1/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.39 | 0.00–0.97 | 1/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.76 | 0.47–0.99 | 1/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.82 | 0.39–0.98 | 4/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.80 | 0.46–0.93 | 4/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.80 | 0.45–0.95 | 4/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.77 | 0.37–0.98 | 4/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.71 | 0.29–0.98 | 1/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.23 | 0.00–0.48 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

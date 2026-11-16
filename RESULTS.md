# Results: `t9-env-reviewer-dual-pastdev` (+ Env + Dual reviewer + past.dev)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-reviewer-dual-pastdev.md`](experiments/t9-env-reviewer-dual-pastdev.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.243 ± 0.291** | 0.071 | 0.500 |
| Mean artifact score (`grade.json` score) | 0.481 ± 0.224 | 0.332 | 0.677 |
| OpenAI cost per run (USD) | 2.00 | 1.50 | 2.43 |
| Wall time per run (h) | 1.91 | 1.70 | 2.10 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env 0.57 / $2.08, + Env + Reviewer 0.76 / $2.24, + Env + Reviewer + past.dev 0.50 / $2.13, + Env + Sub-agents (v4) 0.46 / $10.14, + Env + Sub-agents v5 0.41 / $3.60, + Env + Sub-agents v5 + past.dev 0.50 / $3.21. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `6b5b958922` | 0.071 | 0.333 | 0.94 | none | $1.93 | 1.94 h | – |
| `2359e92e90` | 0.500 | 0.677 | 0.93 | none | $2.36 | 2.10 h | – |
| `f7ec7c7310` | 0.071 | 0.332 | 0.83 | inefficient_analysis, repetitive_retry_loop | $2.43 | 1.90 h | – |
| `0e52da0187` | 0.071 | 0.388 | 0.92 | method_misconfigured | $1.80 | 1.70 h | – |
| `a9a9f0dbe8` | 0.500 | 0.677 | 0.94 | none | $1.50 | 1.90 h | – |

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.37 | 0.21–0.52 | 0/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.54 | 0.32–0.82 | 2/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.67 | 0.50–0.90 | 2/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.41 | 0.20–0.67 | 0/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.15 | 0.00–0.46 | 0/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.13 | 0.00–0.32 | 0/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.54 | 0.21–0.79 | 0/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.56 | 0.18–0.90 | 2/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.57 | 0.21–0.86 | 2/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.67 | 0.44–0.87 | 2/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.57 | 0.37–0.82 | 2/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.52 | 0.28–0.77 | 0/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.05 | 0.00–0.12 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

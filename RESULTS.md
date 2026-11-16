# Results: `t9-env-subagents-v5-pastdev` (+ Env + Sub-agents v5 + past.dev)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-subagents-v5-pastdev.md`](experiments/t9-env-subagents-v5-pastdev.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.500 ± 0.109** | 0.357 | 0.571 |
| Mean artifact score (`grade.json` score) | 0.681 ± 0.034 | 0.649 | 0.723 |
| OpenAI cost per run (USD) | 3.21 | 2.80 | 3.69 |
| Wall time per run (h) | 3.45 | 2.58 | 6.07 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env 0.57 / $2.08, + Env + Reviewer 0.76 / $2.24, + Env + Reviewer + past.dev 0.50 / $2.13, + Env + Dual reviewer + past.dev 0.24 / $2.00, + Env + Sub-agents (v4) 0.46 / $10.14, + Env + Sub-agents v5 0.41 / $3.60. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `288c9ed0d7` | 0.500 | 0.668 | 0.90 | output_format_violation, inefficient_analysis | $2.80 | 2.90 h | 33 |
| `c91ce4558c` | 0.571 | 0.723 | 0.90 | inefficient_analysis | $3.69 | 6.07 h | 29 |
| `eac99c6329` | 0.571 | 0.687 | 0.91 | inefficient_analysis | $3.23 | 2.99 h | 43 |
| `fcc60195e1` | 0.357 | 0.649 | 0.91 | inefficient_analysis | $3.21 | 2.70 h | 56 |
| `4a01a0c552` | 0.500 | 0.677 | 0.92 | inefficient_analysis | $3.14 | 2.58 h | 44 |

Judge score and failure-mode tags come from the process judge re-run on the full trace (`judge_fulltrace.json`), because the official judge only sees the orchestrator's messages.

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.50 | 0.44–0.52 | 0/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.80 | 0.75–0.82 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.89 | 0.85–0.90 | 5/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.64 | 0.58–0.67 | 0/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.11 | 0.00–0.15 | 0/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.29 | 0.20–0.32 | 0/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.81 | 0.78–0.89 | 1/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.92 | 0.90–0.98 | 5/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.87 | 0.86–0.93 | 5/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.65 | 0.00–0.87 | 3/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.89 | 0.82–0.99 | 5/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.83 | 0.76–0.93 | 2/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.33 | 0.12–0.65 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

# Results: `t9-env-subagents-v5` (+ Env + Sub-agents v5)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-subagents-v5.md`](experiments/t9-env-subagents-v5.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.414 ± 0.238** | 0.071 | 0.500 |
| Mean artifact score (`grade.json` score) | 0.640 ± 0.126 | 0.460 | 0.699 |
| OpenAI cost per run (USD) | 3.60 | 2.20 | 4.25 |
| Wall time per run (h) | 3.38 | 2.70 | 4.11 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env 0.57 / $2.08, + Env + Reviewer 0.76 / $2.24, + Env + Reviewer + past.dev 0.50 / $2.13, + Env + Dual reviewer + past.dev 0.24 / $2.00, + Env + Sub-agents (v4) 0.46 / $10.14, + Env + Sub-agents v5 + past.dev 0.50 / $3.21. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `b1805c6458` | 0.500 | 0.699 | 0.95 | none | $4.02 | 3.55 h | 54 |
| `eea4c59338` | 0.500 | 0.677 | 0.87 | inefficient_analysis, repetitive_retry_loop | $3.65 | 2.70 h | 57 |
| `d6dc979173` | 0.500 | 0.666 | 0.88 | incomplete_data, inefficient_analysis, repetitive_retry_loop | $3.89 | 4.11 h | 53 |
| `e9f84feb82` | 0.071 | 0.460 | 0.91 | method_misconfigured, inefficient_analysis | $4.25 | 3.34 h | 62 |
| `15229c06c7` | 0.500 | 0.699 | 0.81 | inefficient_analysis, repetitive_retry_loop | $2.20 | 3.23 h | 18 |

Judge score and failure-mode tags come from the process judge re-run on the full trace (`judge_fulltrace.json`), because the official judge only sees the orchestrator's messages.

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 0.98 | 0.89–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.50 | 0.44–0.52 | 0/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.79 | 0.70–0.82 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.88 | 0.78–0.90 | 4/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.63 | 0.56–0.67 | 0/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.14 | 0.12–0.17 | 0/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.23 | 0.00–0.32 | 0/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.67 | 0.21–0.79 | 0/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.80 | 0.38–0.90 | 4/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.78 | 0.46–0.86 | 4/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.79 | 0.49–0.87 | 4/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.79 | 0.64–0.83 | 4/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.73 | 0.59–0.76 | 0/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.25 | 0.00–0.43 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

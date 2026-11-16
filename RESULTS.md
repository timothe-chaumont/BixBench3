# Results: `t9-env-subagents-pastdev` (+ Env + Sub-agents + past.dev)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 1 independent run of this branch's code.
What this branch changes: [`experiments/t9-env-subagents-pastdev.md`](experiments/t9-env-subagents-pastdev.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

**Only 1 of 5 planned runs completed:** the others were cancelled when the API budget ran out, and the project ended on 2026-11-16. These numbers are not a claim.

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.500** | 0.500 | 0.500 |
| Mean artifact score (`grade.json` score) | 0.667 | 0.667 | 0.667 |
| OpenAI cost per run (USD) | 10.83 | 10.83 | 10.83 |
| Wall time per run (h) | 6.49 | 6.49 | 6.49 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Env 0.57 / $2.08, + Env + Reviewer 0.76 / $2.24, + Env + Reviewer + past.dev 0.50 / $2.13, + Env + Dual reviewer + past.dev 0.24 / $2.00, + Env + Sub-agents (v4) 0.46 / $10.14, + Env + Sub-agents v5 0.41 / $3.60, + Env + Sub-agents v5 + past.dev 0.50 / $3.21. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `ef725eb519` | 0.500 | 0.667 | 0.97 | output_format_violation, inefficient_analysis | $10.83 | 6.49 h | 37 |

Judge score and failure-mode tags come from the process judge re-run on the full trace (`judge_fulltrace.json`), because the official judge only sees the orchestrator's messages.

## Per-artifact score (mean over the 1 run, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 1/1 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.52 | 0.52–0.52 | 0/1 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.81 | 0.81–0.81 | 1/1 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.90 | 0.90–0.90 | 1/1 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.66 | 0.66–0.66 | 0/1 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.12 | 0.12–0.12 | 0/1 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.32 | 0.32–0.32 | 0/1 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.79 | 0.79–0.79 | 0/1 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.90 | 0.90–0.90 | 1/1 |
| HEK293 shared (`hek293_shared_degs`) | 0.87 | 0.87–0.87 | 1/1 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.87 | 0.87–0.87 | 1/1 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.83 | 0.83–0.83 | 1/1 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.75 | 0.75–0.75 | 0/1 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.00 | 0.00–0.00 | 0/1 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

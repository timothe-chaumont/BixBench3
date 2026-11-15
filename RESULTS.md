# Results: `t9-env-subagents` (+ Env + Sub-agents (v4))

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-env-subagents.md`](experiments/t9-env-subagents.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.457 ± 0.049** | 0.429 | 0.500 |
| Mean artifact score (`grade.json` score) | 0.664 ± 0.015 | 0.653 | 0.677 |
| OpenAI cost per run (USD) | 10.14 | 7.58 | 13.61 |
| Wall time per run (h) | 5.71 | 3.91 | 7.73 |

Other versions, task score and cost per run: Baseline 0.39 / $2.91, + Preinstalled env 0.57 / $2.08, + Env + Artifact reviewer 0.76 / $2.24. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `4c581483b6` | 0.429 | 0.653 | 0.97 | inefficient_analysis | $12.46 | 7.73 h | 85 |
| `1c363a0320` | 0.429 | 0.662 | 0.92 | inefficient_analysis | $13.61 | 6.77 h | 60 |
| `7128a650e6` | 0.500 | 0.677 | 0.93 | inefficient_analysis | $8.88 | 3.91 h | 17 |
| `aa4dc4b164` | 0.429 | 0.653 | 0.89 | inefficient_analysis | $7.58 | 5.04 h | 62 |
| `96578339a2` | 0.500 | 0.677 | 0.93 | inefficient_analysis | $8.20 | 5.08 h | 31 |

Judge scores and tags for this version come from the process judge re-run on the full trace, including every sub-agent's tool calls. The official judge sees only the orchestrator and returned 0 tags for every run. The official `judge.json` files are unchanged.

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.50 | 0.44–0.52 | 0/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.80 | 0.75–0.82 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.89 | 0.84–0.90 | 5/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.64 | 0.60–0.67 | 0/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.15 | 0.13–0.19 | 0/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.27 | 0.15–0.32 | 0/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.79 | 0.79–0.79 | 0/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.90 | 0.90–0.90 | 5/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.86 | 0.86–0.86 | 5/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.87 | 0.87–0.87 | 5/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.79 | 0.75–0.83 | 3/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.74 | 0.69–0.77 | 0/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.10 | 0.00–0.13 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

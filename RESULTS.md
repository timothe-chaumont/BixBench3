# Results: `t9-baseline` (Baseline)

Task 9 (`10_1186_s12915_024_01879_0_v1`), GPT-5.4 Mini at xhigh, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 5 independent runs of this branch's code.
What this branch changes: [`experiments/t9-baseline.md`](experiments/t9-baseline.md). Comparison with the other versions, figures and analysis: [results/task9 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task9).

## Summary

| | Mean ± 95% CI | Min | Max |
|---|---|---|---|
| Task score (share of 14 artifacts with score ≥ 0.80, the paper's metric) | **0.386 ± 0.223** | 0.071 | 0.500 |
| Mean artifact score (`grade.json` score) | 0.566 ± 0.173 | 0.335 | 0.677 |
| OpenAI cost per run (USD) | 2.91 | 1.56 | 4.09 |
| Wall time per run (h) | 2.76 | 1.67 | 4.80 |

Other versions, task score and cost per run: + Preinstalled env 0.57 / $2.08, + Env + Artifact reviewer 0.76 / $2.24, + Env + Sub-agents (v4) 0.46 / $10.14. Paper, GPT-5.4 Mini on task 9: 0.71 (one run).

## Runs

| Run (id suffix) | Task score | Mean artifact score | Judge score | Failure-mode tags | Cost | Time | Sub-agents |
|---|---|---|---|---|---|---|---|
| `5cf21bd51c` | 0.500 | 0.677 | 0.92 | inefficient_analysis | $1.56 | 2.10 h | – |
| `d41a3f32f5` | 0.500 | 0.675 | 0.92 | inefficient_analysis | $2.13 | 1.67 h | – |
| `ad6f6b64e3` | 0.071 | 0.335 | 0.87 | environment_setup_failure, inefficient_analysis | $3.77 | 3.06 h | – |
| `fe71f73ac3` | 0.429 | 0.576 | 0.84 | environment_setup_failure, wrong_method_substitution, method_misconfigured, inefficient_analysis | $3.00 | 2.15 h | – |
| `ad8444bd50` | 0.429 | 0.569 | 0.88 | environment_setup_failure, wrong_method_substitution, method_misconfigured, inefficient_analysis | $4.09 | 4.80 h | – |

## Per-artifact score (mean over the 5 runs, min–max)

| Artifact | Mean | Min–max | Runs passing (≥ 0.80) |
|---|---|---|---|
| Count matrix (`tagseq_featurecounts_matrix`) | 1.00 | 1.00–1.00 | 5/5 |
| T98G C10 DEGs (`t98g_c10_vs_control_degs`) | 0.46 | 0.21–0.52 | 0/5 |
| T98G F7 DEGs (`t98g_f7_vs_control_degs`) | 0.72 | 0.32–0.82 | 4/5 |
| T98G G2 DEGs (`t98g_g2_vs_control_degs`) | 0.82 | 0.50–0.90 | 4/5 |
| T98G slow shared (`t98g_slow_shared_degs`) | 0.57 | 0.21–0.67 | 0/5 |
| T98G slow up GO (`t98g_slow_upregulated_go`) | 0.05 | 0.00–0.13 | 0/5 |
| T98G slow down GO (`t98g_slow_downregulated_go`) | 0.13 | 0.00–0.32 | 0/5 |
| HEK293 D10 DEGs (`hek293_d10_vs_control_degs`) | 0.71 | 0.47–0.79 | 0/5 |
| HEK293 E6 DEGs (`hek293_e6_vs_control_degs`) | 0.80 | 0.39–0.90 | 4/5 |
| HEK293 shared (`hek293_shared_degs`) | 0.77 | 0.46–0.86 | 4/5 |
| HEK293 up GO (`hek293_upregulated_go`) | 0.45 | 0.02–0.87 | 2/5 |
| T98G D4 DEGs (`t98g_d4_vs_control_degs`) | 0.73 | 0.37–0.83 | 4/5 |
| T98G D4 specific up (`t98g_d4_specific_upregulated_genes`) | 0.67 | 0.29–0.77 | 0/5 |
| T98G D4 vs slow up GO (`t98g_d4_vs_slow_upregulated_go`) | 0.05 | 0.00–0.12 | 0/5 |

Only runs that completed normally are counted. Raw run bundles (grades, judge, Inspect logs) are kept on Sherlock scratch (/scratch/users/sbennani/bixbench3/runs).

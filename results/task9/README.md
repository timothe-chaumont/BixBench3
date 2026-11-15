# Task 9 results: which harness changes help GPT-5.4 Mini reproduce a study?

**Task 9** (`10_1186_s12915_024_01879_0_v1`): REST loss in T98G and HEK293 cells, Tag-Seq. The agent starts from raw FASTQs and must
build 14 artifacts: a HISAT2 index and featureCounts matrix, 9 DESeq2 contrast tables, shared-gene sets and 4 GO enrichments.

**Setup for every run:** GPT-5.4 Mini at `xhigh`, official v1.0.0 prompt, 6 CPU / 32 GB (the GCP VM shape) on identical
AMD EPYC 7502 Sherlock nodes, 24 h / 5,000 messages. **5 independent runs per version**, graded by the official BixBench3
grader. The task score is the paper's: the share of the 14 artifacts with a grader score of at least 0.80.

![Headline](figures/headline.png)

## Summary

| Version | Branch | Task score (pass rate), mean ± 95% CI | Mean artifact score | Best / worst run | Cost / run | Time / run | Failure tags / run |
|---|---|---|---|---|---|---|---|
| Baseline | [`exp/t9-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-baseline) | 0.39 ± 0.22 | 0.57 | 0.50 / 0.07 | $2.91 | 2.8 h | 2.4 |
| + Preinstalled env | [`exp/t9-env`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env) | 0.57 ± 0.45 | 0.69 | 0.93 / 0.07 | $2.08 | 1.8 h | 0.6 |
| **+ Env + Artifact reviewer** | [`exp/t9-env-reviewer`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer) | **0.76 ± 0.29** | **0.83** | **0.93 / 0.50** | $2.24 | 1.8 h | 0.4 |
| + Env + Sub-agents (v4) | [`exp/t9-env-subagents`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents) | 0.46 ± 0.05 | 0.66 | 0.50 / 0.43 | $10.14 | 5.7 h | 1.0 † |
| *+ Env + Sub-agents v5 (preliminary, 1 of 5 runs)* | [`exp/t9-env-subagents-v5`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5) | *0.50* | *0.68* | *–* | *$3.65* | *2.7 h* | *2.0 †* |
| *+ Env + Sub-agents v5 + past.dev (preliminary, 3 of 5 runs)* | [`exp/t9-env-subagents-v5-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5-pastdev) | *0.48 ± 0.27* | *0.67* | *0.57 / 0.36* | *$3.08* | *2.9 h* | *1.5 † (2 runs re-judged)* |
| *Paper: GPT-5.4 Mini, task 9* | – | *0.71 (one run)* | *not reported* | – | *$8.47 (mean over all 20 tasks)* | – | *3.25 (all tasks)* |

† Judged on the full logs. See [the judge blind spot](#3-the-official-process-judge-cannot-see-sub-agents) below.
Rows in *italics* are versions whose 5 runs are not all finished yet. They make no claim and are not tested.

**Statistics.** Exact one-sided permutation tests against the baseline (5 vs 5 runs, all 252 relabellings):

| Version | Task score | Mean artifact score |
|---|---|---|
| Reviewer | **p = 0.024** | **p = 0.012** |
| Env | p = 0.20 | p = 0.16 |
| Sub-agents | p = 0.42 | p = 0.07 |

The figures below show every run.

## What we learned

### 1. A format reviewer nearly doubles the task score, at no extra cost
Before a table goes to `outputs/`, a second call to the same model checks it against the artifact's specification. The
reviewer sees a computed summary of the file (shape, header, head and tail rows, key uniqueness, sampled identifiers). It
never sees ground truth, grader output or reference answers, and it judges format only.

- **Score:** the task score rises from **0.39 to 0.76** and the mean artifact score from 0.57 to 0.83.
- **Reliability:** no reviewer run scored below 0.50, while the baseline's worst run scored 0.07. 3 of the 5 reviewer runs
  passed 13 of 14 artifacts.
- **Cost and time:** $2.24 and 1.8 h per run, against $2.91 and 2.8 h for the baseline.
- **Versus the paper:** this is the only version whose mean is above the paper's GPT-5.4 Mini result on this task (0.71).

### 2. A preinstalled environment makes runs cheaper and cleaner, but not reliably better
Preinstalling HISAT2 2.2.1, Subread, DESeq2 1.30.1, clusterProfiler and the matching annotation packages, all first on PATH,
has three effects:

- **Cost and time:** 28% cheaper ($2.08 against $2.91) and 34% faster (1.8 h against 2.8 h).
- **Failure tags:** 2.4 per run down to 0.6. Environment-setup failures disappear.
- **Score:** spread out in both directions (0.07 to 0.93). The mean gain (+0.19) is not significant with 5 runs.

What remains after the environment is fixed is scientific choices, not tooling.

### 3. The official process judge cannot see sub-agents
The official process judge reads only the main agent's messages (`samples[0].messages`). In the sub-agent versions that
agent is the orchestrator, so the judge saw 103–189 orchestrator messages, while the sub-agents made **810–1,757 tool calls**
it never saw. The result was **0 failure tags in every sub-agent run**.

We re-ran the same judge (same prompt, model and 120k-character budget) on the full trace rebuilt from the eval logs. Every
run then gets an "inefficient analysis" tag. The official `judge.json` files are left unchanged, and the re-judged results
are stored next to them as `judge_fulltrace.json`. Any benchmark that grades process from the top-level transcript will
over-credit multi-agent harnesses in the same way.

### 4. Sub-agents cost 3.5× more without improving the score
The v4 sub-agent design has an orchestrator, a dependency planner and one sub-agent per artifact. Its runs are the most
consistent (pass rate 0.43–0.50) but cost **$10.14 per run**, and the score does not improve. We traced where the money went
in a $8.88 run:

- **Polling:** **$3.18 (36%) went on 268 status checks** while `hisat2-build` ran for about an hour. Each check is a full
  xhigh-reasoning model call that re-reads a context of about 150k tokens.
- **Per-agent overhead:** about $1.5. Every new sub-agent starts with an empty context, so it re-reads the brief, the files
  and the environment manifest.
- **Duplicates and planning:** $0.34 on two artifacts the orchestrator rebuilt although they were already valid, and $0.48
  on the planner.

These findings shaped **v5** (blocking waits, no rebuilding valid artifacts, parallel dependency levels, sub-agents at
`medium` effort, no planner) and a **past.dev run memory**, so that sub-agents share what earlier agents found.

**First v5 results (preliminary, 4 of 10 runs finished):** cost drops from $10.14 to **$3.65 (v5, 1 run)** and **$3.08
(v5 + past.dev, mean of 3 runs)**, and time from 5.7 h to about 2.8 h. The score stays at the v4 level (task score 0.50 and
0.48). The cost fixes work, but sub-agents still do not beat the single-agent reviewer.

### 5. One ambiguous sentence in the prompt drives most of the error left in the T98G artifacts
The count matrix is correct (score 1.00) in **every** run. The T98G differential-expression and GO artifacts then split by
a single modelling choice. The prompt says *"Run DESeq2 … separately by cell line and clone contrast"*, which agents read
in two ways:

| How the agent fits DESeq2 | C10 DEGs | D4 DEGs | D4-vs-slow GO |
|---|---|---|---|
| One model per cell line (all 10 T98G samples), one contrast per clone | 0.99 | 0.98 | 0.40–0.48 |
| A separate 2-vs-2 model for each comparison | 0.44–0.52 | 0.75–0.83 | 0–0.13 |
| As above, but samples filtered on condition only, so HEK293 controls leak into T98G (agent bug) | 0.21 | 0.37 | 0 |

The reference was built the first way. With only 2 vs 2 samples, DESeq2 estimates dispersion poorly and about 25% fewer
genes reach significance. The error then compounds through D4 DEGs, the shared slow-clone set, D4-specific genes and D4 GO.
This is why **"T98G D4 vs slow up GO" is the weakest artifact in every version** (heatmap below).

We did **not** add a hint to the prompt. It would come too close to giving the answer. This is a property of the benchmark
item worth reporting.

## Figures

**Per-artifact scores** (mean, min–max underneath; cf. paper Supp. Fig. 4B). The reviewer improves almost every column,
most strongly the T98G DE tables and the GO enrichments. The count matrix is solved in every run.

![Heatmap of artifact scores](figures/fig_C_heatmap_scores.png)

**Task score per run, with mean and 95% CI.** Left: pass rate, the paper's score. Right: mean artifact score. Versions marked *preliminary* have fewer than 5 runs.

![Task scores](figures/fig_D_task_scores.png)

**Process-judge failure modes per run** (cf. paper Fig. 5A–B). The environment removes setup failures, and the reviewer
leaves only occasional "inefficient analysis" tags. † marks the full-trace re-judge.

![Failure modes](figures/fig_A_B_failure_modes.png)

**Cost against score** (complete versions only). The reviewer version sits in the top-left corner: higher score, low cost.

![Cost vs score](figures/fig_F_cost_vs_score.png)

**Cost and wall time per run.**

![Cost and time](figures/fig_E_cost_time.png)

Also: [pass frequency per artifact](figures/fig_C_heatmap_pass_frequency.png) and [summary table](figures/summary.md).
PDFs sit next to each PNG.

## Versions still running (results are added as runs finish)

| Version | Branch | Idea |
|---|---|---|
| + Env + Reviewer + past.dev | [`exp/t9-env-reviewer-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-pastdev) | The reviewer also sees the tables it already accepted in this run, for cross-table format consistency |
| + Env + Dual reviewer + past.dev | [`exp/t9-env-reviewer-dual-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-dual-pastdev) | Local reviewer plus a consistency reviewer with a rolling run memory; both must accept |
| + Env + Sub-agents v5 (1/5 done) | [`exp/t9-env-subagents-v5`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5) | The cost fixes from finding 4 |
| + Env + Sub-agents + past.dev | [`exp/t9-env-subagents-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-pastdev) | v4 plus a shared past.dev memory of inspections, files and conventions |
| + Env + Sub-agents v5 + past.dev (3/5 done) | [`exp/t9-env-subagents-v5-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5-pastdev) | Both of the above |

## Method notes and caveats

- **Run counting:** only runs that completed normally are counted. Smoke tests, and 13 runs lost to an API rate limit
  and a relay outage in the first hour of the night batch, are excluded. Every completed run is
  included, whatever its score.
- **Paper reference:** the paper reports one GPT-5.4 Mini attempt on task 9: 10 of 14 artifacts passed (Fig. 1B), which
  is 0.71. It does not say which artifacts passed, so that heatmap row is left empty. Its failure-mode counts and its $8.47
  cost are means over all 20 tasks, not task 9 alone. No paper number here is estimated.
- **Why GPT-5.4 Mini:** it is a cheap model, so 5 repeats per version fit the budget. With this much run-to-run spread,
  single runs would be misleading.
- **Platform parity:** our Sherlock task 9 baseline (0.566 mean artifact score) matches the team's GCP reference run
  (0.575), so the cluster does not bias the comparison.

## Reproduce the figures

```bash
cd results/task9
./update_data.sh   # pulls completed runs from Sherlock into data/runs.jsonl (needs `ssh sherlock`)
uv run --no-project --with matplotlib python make_figures.py
uv run --no-project --with matplotlib python make_headline.py
```

`data/runs.jsonl` holds one record per completed run: grades, per-artifact scores, judge tags, tokens, cost and time. It
contains no credentials, prompts or transcripts.

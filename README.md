# Can a cheap AI scientist do better with a better lab around it?

*AI Research Hackathon, Track 3: AI Scientist Swarms*

**Short answer: yes.** One well-placed reviewer nearly doubled our agent's score. A swarm of sub-agents cost 3.5× more
and did not help.

![Task 9 headline results](results/task9/figures/headline.png)
<sub>Each light dot is one run, and each dark dot is the mean of 5 runs with a 95% confidence interval. Red line: the
BixBench3 paper's result for the same model on the same task. Score = share of the 14 required result tables that match
the paper's (grader score ≥ 0.80).</sub>

## The problem

[BixBench3](https://arxiv.org/abs/2608.25286) tests whether AI agents can do real computational biology. The agent gets
the raw sequencing data and the methods of a published paper, and must reproduce the paper's result tables. It has to
align reads, count genes, run differential expression and GO enrichment. Even the best model in the paper scores only
0.48 on average.

Most work improves the **model**. We asked the opposite question: **keep a small, cheap model (GPT-5.4 Mini) fixed, and
change only the "lab" around it, meaning its tools, its environment and its colleagues. What actually helps, and at
what cost?**

## What we did

1. **Made measurements trustworthy first.** The same setup run twice can score 0.07 and then 0.93, so single runs prove
   nothing. We built a runner for Stanford's Sherlock cluster that reproduces the benchmark's cloud setup: same machine
   size, same scores within error. It let us run every version **5 times**, up to 24 runs at once.
2. **Picked one task and tested three ideas, each on top of the previous one.** Task 9 is the REST knockout study: raw
   reads to 14 tables. Baseline logs showed agents losing time and money installing tools, so we started there:
   - **a preinstalled environment** with the exact tool versions the paper used;
   - **a format reviewer:** before a table is published, a second call to the same model checks it against the table's
     specification. The reviewer never sees the answers;
   - **a swarm:** an orchestrator that hands each table to its own sub-agent.
3. **Audited every run** for score, cost, time and failure modes, then fixed what the audit revealed and ran again.

## What we found

| What we added | Score (mean of 5 runs) | Cost per run | Time per run |
|---|---|---|---|
| Nothing (baseline) | 0.39 | $2.91 | 2.8 h |
| Preinstalled environment | 0.57 | $2.08 | 1.8 h |
| **Environment + format reviewer** | **0.76** | **$2.24** | **1.8 h** |
| Environment + sub-agent swarm | 0.46 | $10.14 | 5.7 h |
| *Paper, same model (one run)* | *0.71* | | |

- **The reviewer is the winner.** The score nearly doubles (0.39 → 0.76, p = 0.024) and ends above the paper's 0.71. It
  costs less than the baseline, and no reviewer run fell below 0.50. A second pair of eyes beats more compute.
- **The environment makes the agent faster and cheaper, not smarter.** Setup failures vanish, but the score still swings
  from 0.07 to 0.93. What remains is scientific judgment, not tooling.
- **The swarm is expensive and no better.** The audit showed why: one sub-agent spent $3.18 checking 268 times whether a
  genome index had finished building. Our redesigned swarm (v5) cuts the cost to about $3–4 per run in its first finished
  runs, but still does not beat the single agent with a reviewer *(preliminary: 4 of 10 runs done)*.
- **The benchmark's process judge is blind to swarms.** It only reads the top-level conversation. It gave every swarm run
  0 failure tags while missing up to 1,757 actions taken by sub-agents. Re-judged on the full trace, every
  swarm run is flagged.
- **One ambiguous sentence in the task explains most of the remaining errors.** *"Run DESeq2 separately by cell line and
  clone contrast"* leads most agents to a valid but different statistical design from the paper's. The error then flows
  into every downstream table.

## Why it matters

Better harnesses are a cheap lever: about 500 lines of reviewer code moved a small model past the paper's result.
And as AI scientists become multi-agent systems, benchmarks must grade the whole trace, or they will reward agents for
hiding their mistakes in sub-agents.

## Dig deeper

- **[Full task 9 analysis](results/task9/):** every figure (per-table heatmap, failure modes, cost), statistics and
  caveats.
- **[Task 11 results](results/task11/):** the check that the Sherlock runner matches the cloud setup (0.630 ± 0.069
  against 0.679).
- **Each experiment's branch:** exactly what changed (`experiments/<version>.md`) and its per-run numbers (`RESULTS.md`).
  See the branch map below.
- **[Raw per-run data](results/task9/data/runs.jsonl)** behind every number on this page.

<details>
<summary><b>How we ran it (identical for every version)</b></summary>

- **Model and limits:** GPT-5.4 Mini at `xhigh` reasoning, the official v1.0.0 task prompt, 24 h / 5,000-message limits.
- **Grading:** the official BixBench3 grader and process judge.
- **Hardware:** 6 CPU / 32 GB per run (the benchmark's cloud VM shape), on identical AMD EPYC 7502 Sherlock nodes.
- **Score:** the task score is the paper's metric, the share of the 14 artifacts with a grader score of at least 0.80.
- **Statistics:** exact one-sided permutation tests against the baseline, 5 runs vs 5. Reviewer: p = 0.024 on task score
  and p = 0.012 on mean artifact score. Environment: p = 0.20. Swarm: p = 0.42.
- **Which runs count:** every completed run, whatever its score. Smoke tests and runs killed by infrastructure problems
  (API rate limit, relay outage) are excluded. Versions with fewer than 5 finished runs are marked preliminary and make no
  claims.
- **Paper numbers:** quoted, never estimated. The paper reports one GPT-5.4 Mini run on task 9 (10 of 14 tables passed),
  and $8.47 average cost over its 20 tasks.

</details>

<details>
<summary><b>Infrastructure we built</b></summary>

- **Sherlock runner** ([`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner)): runs the unchanged benchmark on Stanford's HPC cluster
  with the cloud VM shape. Sandbox parity fixes: root apt, memory and CPU views, isolation from host processes. A key
  relay switches OpenAI keys mid-run without interrupting the agent.
- **Preinstalled task environments** ([`feat/task-envs-sherlock`](https://github.com/timothe-chaumont/BixBench3/tree/feat/task-envs-sherlock)): per-task images with the
  tool versions the method asks for.
- **Live dashboard** ([`tools/bixdash`](tools/bixdash/)): every run's phase, cost and score, shared across the team.
- **6 vCPU team profile** ([TEAM_SETUP.md](TEAM_SETUP.md)) and the adapted GCP runner ([ADAPTED_RUNNER.md](ADAPTED_RUNNER.md)).
- **Task 11 "lite" proxy study** ([iterations/proxy-validation-task11](iterations/proxy-validation-task11/)): can a
  30-minute downstream-only task stand in for the 2-hour full run? It is feasible, but ranking preservation is not
  established.

</details>

<details>
<summary><b>Branch map: one branch per experiment</b></summary>

| Branch | What it adds | Status |
|---|---|---|
| `main` | Benchmark code, team setup, [results/](results/), run records ([iterations/](iterations/)) | |
| [`exp/t9-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-baseline) | Task 9 baseline | 5/5 runs done |
| [`exp/t9-env`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env) | + preinstalled task 9 environment | 5/5 done |
| [`exp/t9-env-reviewer`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer) | + artifact format reviewer (**best**) | 5/5 done |
| [`exp/t9-env-subagents`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents) | + orchestrator and sub-agents (v4) | 5/5 done |
| [`exp/t9-env-subagents-v5`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5) | Sub-agents v5: the cost fixes | 1/5 done, running |
| [`exp/t9-env-subagents-v5-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5-pastdev) | Sub-agents v5 + past.dev shared run memory | 3/5 done, running |
| [`exp/t9-env-subagents-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-pastdev) | Sub-agents v4 + past.dev shared run memory | running |
| [`exp/t9-env-reviewer-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-pastdev) | Reviewer that remembers the tables it already accepted | running |
| [`exp/t9-env-reviewer-dual-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-dual-pastdev) | Local reviewer + consistency reviewer with memory | running |
| [`exp/t11-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t11-baseline) | Task 11 baseline on Sherlock | 4/4 done |
| [`exp/v2f`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v2f), [`exp/v3a`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3a)–[`v3e`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3e) | Task 11 batch 1 harness variants on GCP | single runs, see [results/task11](results/task11/) |
| [`exp/t11-v4-dag-orchestrator`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t11-v4-dag-orchestrator) | First sub-agent orchestrator (source of t9 v4) | code only |
| [`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner), [`feat/task-envs-sherlock`](https://github.com/timothe-chaumont/BixBench3/tree/feat/task-envs-sherlock) | Sherlock runner; per-task environment images | infrastructure |
| [`setup/adapted-runner`](https://github.com/timothe-chaumont/BixBench3/tree/setup/adapted-runner), [`tools/bixdash`](https://github.com/timothe-chaumont/BixBench3/tree/tools/bixdash) | Earlier snapshots, already merged into `main` | archived |

</details>

**Run the benchmark yourself:** see the upstream documentation below, [TEAM_SETUP.md](TEAM_SETUP.md) for GCP and
[`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner) for HPC. Upstream baseline commit `d0e0bbb41222335b1b8878f533a58466a3a782dc`.

---

# BixBench3 (upstream documentation)

BixBench3 evaluates whether AI agents can reproduce research-scale computational biology analyses from public raw data. Each task supplies a biological objective, method guidance, raw inputs, and exact structured output contracts. Agents run on a GCP VM, analyze the data, and produce the required artifacts. Agent artifacts are graded deterministically against published ground truth artifacts, and a PhDval-compatible process judge scores instruction following, transparency, analytical rigor, and run-level failure modes.

This repository contains the public runner and grader code. The 20-task benchmark is on huggingface [BixBench3 Hugging Face dataset](https://huggingface.co/datasets/EdisonScientific/BixBench3). Raw inputs data and ground truth artfiacts are stored Google Cloud Storage buckets.

```text
BixBench3 github repo  
└── runner code, grader code

Hugging Face  EdisonScientific/BixBench3
├── prompts + artifact output contracts
├── cases/{paper_id}/agent/ 
├── cases/{paper_id}/runtime/
└── manifests/   (task map, GCS package URLs)

GCS inputs   gs://bixbench3-inputs/releases/v1.0.0/tasks/{paper_id}/
├── data/raw/         agent-visible raw inputs (FASTQs, etc.)
└── data/metadata/    non-answer metadata

GCS ground truth   gs://bixbench3-ground-truth/releases/v1.0.0/tasks/{paper_id}/
├── artifacts_grading.json   which checks (F1, CCC, ...) each artifact uses
└── artifacts/               golden published tables used for grading
```



# Running the benchmark



## 1. Install prerequisites

Install Python 3.12, `uv`, and the Google Cloud CLI. Clone this repository and install its locked dependencies:

```bash
git clone https://github.com/EdisonScientific/BixBench3.git
cd BixBench3
uv sync --locked
```



## 2. Authenticate a GCP project

Authentice with Google Cloud CLI:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT
```

The project must have billing and the Compute Engine API, and quota for an `n2-standard-32` VM in `us-central1-a` (or change the code to use your desired region). 

## 3. Export API keys

Export the provider key for the model you want to test. The benchmark network adjudicator and process judge use GPT-5.5, so every run also requires `OPENAI_API_KEY`.

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

Other supported provider variables are `GOOGLE_API_KEY` and `OPENROUTER_API_KEY`. Keys are accepted only through environment variables and are streamed into memory on the VM. 

## 4. Obtain licensed 10x software

For use in the agent's docker container, download [Cell Ranger 6.0.2](https://www.10xgenomics.com/support/software/cell-ranger/downloads/previous-versions) and [Cell Ranger ARC 2.0.2](https://www.10xgenomics.com/support/software/cell-ranger-arc/downloads/previous-versions) from 10x Genomics after reviewing and accepting its End User Software License Agreement. This repository does not host or redistribute the tarballs, and BixBench3 does not verify that you accepted the license.

Expected files:

```text
cellranger-6.0.2.tar.gz
cellranger-arc-2.0.2.tar.gz
```



## 5. Build the runtime (done once)

```bash
uv run bixbench3 setup-runtime \
  --project YOUR_PROJECT \
  --cellranger-tarball /path/to/cellranger-6.0.2.tar.gz \
  --cellranger-arc-tarball /path/to/cellranger-arc-2.0.2.tar.gz
```

This creates a VM which builds and tests the Docker image, stores it as a private image in your project, and then deletes the VM. The image is versioned with the benchmark release. Each agent runs inside this image in subsequent runs.

The build typically takes 30–60 minutes. Add `--dry-run` to validate the archives and inspect the planned cloud operations without creating resources.

## 6. Run a task

```bash
uv run bixbench3 run \
  --task 1 \
  --model openai/gpt-5.5 \
  --effort max \
  --project YOUR_PROJECT \
  --results-bucket gs://YOUR_BUCKET/bixbench3 # optional
```

On the first run of a task, the runner copies that task's raw input data from `gs://bixbench3-inputs` onto a persistent disk in your GCP project, checks the disk against the expected checksum, and attaches it read-only to the VM where the agent will run. Later runs of the same task reuse that disk in your project instead of re-downloading from GCS.

After provisioning the VM, `run` starts the benchmark as a detached service and returns. It prints a run ID and exact commands for checking, completing, or cancelling the run. Your workstation does not need to remain connected. Runs take up to 24 hours, with an average of approximately 8 hours.

### Run outputs and retention

Local outputs are stored under `runs/{paper_id}/{model_slug}/{timestamp}/`. When `--results-bucket gs://BUCKET/PREFIX` is set, retained cloud outputs are uploaded under `gs://BUCKET/PREFIX/{paper_id}/{model_slug}/{timestamp}/`.


| Output                                   | Contents                                                                 | Without `--results-bucket`                      | With `--results-bucket`                                       |
| ---------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------- | ------------------------------------------------------------- |
| `grade.json`                             | Overall paper score and all artifact results                             | Downloaded locally by `complete`                | Downloaded locally and uploaded to GCS                        |
| `judge.json`                             | PhDval-compatible process score, rubric evidence, and failure-mode tags  | Downloaded locally by `complete`                | Downloaded locally and uploaded to GCS                        |
| `artifact_grades/`                       | One grading JSON file per requested artifact                             | Downloaded locally by `complete`                | Downloaded locally and uploaded to GCS                        |
| `inspect_logs/`                          | Inspect eval log, trajectory, model events, and available usage metadata | Downloaded locally by `complete`                | Downloaded locally and uploaded to GCS                        |
| `run_manifest.json`                      | Local run identity, model settings, lifecycle state, and cleanup result  | Retained locally                                | Retained locally; the remote manifest is also uploaded to GCS |
| `remote_run_manifest.json`               | Final manifest copied back from the VM                                   | Downloaded locally by `complete`                | Downloaded locally; represented as `run_manifest.json` in GCS |
| `cleanup.json`                           | VM deletion result                                                       | Written locally by `complete` or `cancel`       | Written locally by `complete` or `cancel`                     |
| `outputs/`                               | Files written directly by the agent                                      | Deleted with the VM                             | Uploaded to GCS                                               |
| `agent_artifacts/`                       | Agent outputs copied into the deterministic grading input directory      | Deleted with the VM                             | Uploaded to GCS                                               |
| `broker_logs/`                           | Network gateway request and adjudication logs                            | Deleted with the VM                             | Uploaded to GCS                                               |
| `workspace/`                             | Agent working files and approved web downloads                           | Deleted with the VM                             | Deleted with the VM                                           |
| `broker_cache/` and `broker/policy.json` | Network cache and effective access policy                                | Deleted with the VM                             | Deleted with the VM                                           |
| `dataset/`                               | Staged one-task prompt and runtime metadata                              | Deleted with the VM                             | Deleted with the VM                                           |
| `host_ground_truth/`                     | Temporary host-only grading package                                      | Removed after grading, then deleted with the VM | Removed after grading, then deleted with the VM               |
| `run.sh` and `status.json`               | Detached service script and live phase state                             | Deleted with the VM                             | Deleted with the VM                                           |
| `/dev/shm/bixbench3.env`                 | In-memory provider API keys                                              | Deleted when the run exits                      | Deleted when the run exits                                    |




## 7. Monitor and grade a task

```bash
uv run bixbench3 status \
  --run RUN_ID \
  --project YOUR_PROJECT

uv run bixbench3 complete \
  --run RUN_ID \
  --project YOUR_PROJECT
```

You can check the status of a run with `status` and grade it with `complete`.

`status` is read-only and reports the remote phase, exit status, and VM state, including the `grading` and `judging` phases that follow the analyst run. Once it reports `succeeded` or `failed`, run `complete` to copy `grade.json`, `judge.json`, the `artifact_grades/` directory, Inspect logs under `inspect_logs/`, and the final manifest locally and delete the VM. The VM remains running and billable until you complete or cancel it.

To stop an active run, collect any available state, and delete its VM:

```bash
uv run bixbench3 cancel \
  --run RUN_ID \
  --project YOUR_PROJECT
```

By default, `complete` copies the overall `grade.json`, process report `judge.json`, per-artifact JSON files under `artifact_grades/`, Inspect logs under `inspect_logs/`, and the run manifest to your local machine. Pass `--results-bucket` when launching to also upload agent outputs, the copied agent artifacts, network broker logs, and the same grade, judge, and Inspect files to a GCS prefix you already own. Without this option, those additional run files are lost when `complete` or `cancel` deletes the VM. The project's default Compute Engine service account must be able to write to that bucket.

### Process judging

Every cloud run automatically invokes `openai/gpt-5.5` with requested effort `max` (resolved to `xhigh`) and temperature 0 after deterministic artifact grading. The implementation pins the same prompt, eight per-artifact rubrics, ten failure-mode tags, trace compaction, response schema, normalization, and single validation retry used by PhDval-1. A process-judge API or parsing failure is recorded in `judge.json` without replacing or invalidating the deterministic artifact grade.

### Grading existing artifacts

```bash
uv run bixbench3 grade \
  --task 1 \
  --artifacts-dir /path/to/outputs
```

The command prints the overall paper score, every artifact score, and each output path. It writes the overall result to `grade.json` beside the supplied artifacts directory and writes one JSON file per artifact under `artifact_grades/`.

## Model effort

Every run requires an explicit effort. `src/bixbench3/reference_models.yaml` records the exact models and non-effort settings used in the paper.

- OpenAI GPT-5.6 models preserve native `max` with high verbosity. GPT-5.5 and earlier models resolve `max` to `xhigh` with high verbosity.
- Google and Gemini `max` or `xhigh` resolve to `high`.
- OpenRouter GLM 5.2 and DeepSeek V4 Flash resolve `max` to `xhigh`.
- Grok 4.5 resolves `max` or `xhigh` to its highest supported effort, `high`.
- OpenRouter Kimi K3 preserves `max`.
- Claude Fable 5, Claude Opus 5, Claude Opus 4.8, and Claude Sonnet 4.6 use `--effort max`. Claude Fable 5 does not set Anthropic `fallbacks`, so a classifier content restriction is returned as a refusal instead of retrying another model.
- Claude Haiku 4.5 uses 63,999 reasoning tokens for `max`.

The run manifest records both the requested and resolved effort.

## Tasks

Task numbers map to stable paper IDs in the Hugging Face release manifest:

1. `10.1101_2025.06.17.659900_v1` — The chromatin remodeler LET-418/Mi-2 regulates the intracellular pathogen response in the C. elegans intestine
2. `10.64898_2026.02.11.704850_v1` — Contact-dependent regulation of UV-B/C-induced cell fate by neighbouring intact cells
3. `10.1101_2025.08.16.670679_v1` — An interneuronal CRH and CRHBP circuit stabilizes birdsong performance
4. `10.64898_2026.02.03.703548_v1` — How many are you? Open data and bioinformatics reveal species misidentification and potential introgression in Chordodes
5. `10.1101_2025.07.20.665670_v1` — A conserved small RNA-generating gene cluster undergoes sequence diversification and contributes to plant immunity
6. `10.1101_2025.07.08.663208_v1` — MitoPerturb-Seq identifies common and gene-specific single-cell responses to mitochondrial DNA depletion and heteroplasmy
7. `10.1101_2025.07.28.666515_v1` — Methylomic signatures of tau and amyloid-beta in transgenic mouse models of Alzheimer's disease neuropathology
8. `10.1038_s42003-022-03654-9_v1` — Combined MEK and JAK/STAT3 pathway inhibition effectively decreases SHH medulloblastoma tumor progression
9. `10_1186_s12915_024_01879_0_v1` — Targeting of REST with rationally-designed small molecule compounds exhibits synergetic therapeutic potential in human glioblastoma cells
10. `10.1038_s41467-023-44243-6_v1` — Structure-guided design of a selective inhibitor of the methyltransferase KMT9 with cellular activity
11. `10.1016_j.crtox.2021.01.003_v1` — Transcriptomic analyses of livers from mice exposed to 1,4-dioxane for up to 90 days to assess potential modes of action underlying liver tumor development
12. `10.1101_2025.06.02.657493_v1` — A microbiota-derived bile acid modulates biofilm formation by the probiotic strain Escherichia coli Nissle 1917
13. `10.64898_2026.03.10.709901_v1` — High-resolution retrospective single cell lineage tracing with mutable homopolymers
14. `10.1101_2025.07.21.665972_v1` — RUNX2 inhibition disrupts a PAX3::FOXO1-RUNX2 feed-forward loop and dismantles oncogenic gene programs in fusion-positive rhabdomyosarcoma
15. `10.64898_2026.01.09.698641_v1` — TDP-43 dysfunction leads to the accumulation of cryptic transposable element-derived exons, crypTEs, in iPSC derived neurons and ALS/FTD patient tissues
16. `10.1101_2025.07.31.667834_v1` — Antifungal exposure can enhance Candida glabrata pathogenesis
17. `10.1101_2025.07.18.664654_v1` — Polycomb repression works without Siesta
18. `10.64898_2026.01.02.697332_v1` — A Glycosylation-Dependent Checkpoint Restrains Intestinal Intra-Epithelial Lymphocyte Activation
19. `10.64898_2026.01.31.702960_v1` — A TCER-1-siRNA Regulatory Axis Suppresses Antibacterial Innate Immunity in C. elegans
20. `10.64898_2026.02.04.703711_v1` — Habitat fragmentation controls bacterial community composition outcomes



## License

Edison-authored code and benchmark materials are licensed under CC BY-SA 4.0. Mirrored raw scientific data and published artifacts retain their original upstream terms (see `NOTICE`).
## Outils

- [`tools/bixdash`](tools/bixdash/) : dashboard des runs (collecteur en lecture seule sur chaque VM, site web, import des runs terminés). Voir son README.

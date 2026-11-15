# Harness engineering for AI scientists on BixBench3

**AI Research Hackathon, Track 3: AI Scientist Swarms.** [BixBench3](https://arxiv.org/abs/2608.25286) asks whether an AI
agent can reproduce a published computational-biology study from the raw public data: align the reads, count, run
DE and enrichment, and produce exact output tables that are graded against the paper's artifacts. The best model in the
paper averages 0.48. Our question: **with a fixed, cheap model (GPT-5.4 Mini), which changes to the agent's harness and
environment actually raise the score, and at what cost?** Each version runs 5 times, because single runs of the same
setup range from 0.07 to 0.93.

![Task 9 headline results](results/task9/figures/headline.png)

### Main results (task 9, Tag-Seq REST knockout, 14 artifacts, 5 runs per version)

- **A format reviewer nearly doubles the score, at no extra cost.** Before a table is published, a second call to the
  same model checks its format against the artifact's specification. It never sees ground truth. The task score rises
  from **0.39 to 0.76** (p = 0.024, exact permutation test), above the paper's GPT-5.4 Mini result on this task (0.71). No
  reviewer run falls below 0.50, and the cost is **$2.24 per run** against $2.91.
- **A preinstalled task environment cuts cost and failures, but not the variance.** Runs get a third cheaper and faster,
  and failure-mode tags drop from 2.4 to 0.6 per run. The score now spans 0.07 to 0.93: what remains is scientific
  choices, not tooling.
- **Sub-agent swarms cost 3.5× more for no gain.** A per-artifact sub-agent design costs $10 per run and takes 5.7 h,
  with no score improvement. A trace audit shows that 36% of one run's cost went on 268 polling calls during a single
  index build. These findings shaped the v5 design and the past.dev shared-memory variants, which are running now.
- **The official process judge cannot see sub-agents.** It reads only the top-level transcript and gave **0 failure
  tags** to every sub-agent run, while the sub-agents made up to 1,757 tool calls it never saw. Re-judged on the full
  trace, every run is tagged. Process grading of multi-agent systems needs the full trace.
- **One ambiguous prompt sentence explains most of the error left in the T98G artifacts.** *"Run DESeq2 separately by cell
  line and clone contrast"* leads most agents to fit 2-vs-2 models. The reference uses one model per cell line, and the
  error compounds into the GO artifacts.

| Task 9 version | Task score (5 runs) | Cost / run | Time / run |
|---|---|---|---|
| Baseline | 0.39 ± 0.22 | $2.91 | 2.8 h |
| + Preinstalled env | 0.57 ± 0.45 | $2.08 | 1.8 h |
| **+ Env + Artifact reviewer** | **0.76 ± 0.29** | **$2.24** | **1.8 h** |
| + Env + Sub-agents | 0.46 ± 0.05 | $10.14 | 5.7 h |
| *Paper, GPT-5.4 Mini (1 run)* | *0.71* | *$8.47 (all-task mean)* | |

**Full analysis, all figures and caveats: [results/task9](results/task9/).** Task 11 results and the Sherlock/GCP parity
check: [results/task11](results/task11/). Task 11 "lite" proxy study: [iterations/proxy-validation-task11](iterations/proxy-validation-task11/).

### Infrastructure we built

- **Sherlock runner** ([`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner)): runs the unchanged benchmark on Stanford's HPC cluster
  with the GCP VM shape (6 CPU / 32 GB, one CPU generation). Sandbox parity fixes: root apt, memory and CPU views,
  isolation from host processes. A key relay switches OpenAI keys mid-run without interrupting the agent. About 25 runs
  of 6 CPU can run at once, against 5 on a 32-vCPU GCP quota.
- **Preinstalled task environments** ([`feat/task-envs-sherlock`](https://github.com/timothe-chaumont/BixBench3/tree/feat/task-envs-sherlock)): per-task images with the
  tool versions the method asks for.
- **Live dashboard** ([`tools/bixdash`](tools/bixdash/)): every run's phase, cost and score, shared across the team.
- **6 vCPU team profile** ([TEAM_SETUP.md](TEAM_SETUP.md)) and the adapted GCP runner ([ADAPTED_RUNNER.md](ADAPTED_RUNNER.md)).

### Branch map

Each experiment lives on its own branch: one branch per task × version, and repeats of the same code share a branch.
Each branch has `experiments/<version>.md` describing exactly what changed. Branches with finished runs also have a
`RESULTS.md`.

| Branch | What it is | Status |
|---|---|---|
| `main` | Benchmark code, shared team setup, results ([results/](results/)), run records ([iterations/](iterations/)) | |
| [`exp/t9-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-baseline) | Task 9 baseline on Sherlock | 5 runs, done |
| [`exp/t9-env`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env) | + preinstalled task 9 environment | 5 runs, done |
| [`exp/t9-env-reviewer`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer) | + artifact format reviewer (**best**) | 5 runs, done |
| [`exp/t9-env-subagents`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents) | + orchestrator and sub-agents (v4) | 5 runs, done |
| [`exp/t9-env-subagents-v5`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5) | Sub-agents v5: cost fixes | running |
| [`exp/t9-env-subagents-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-pastdev) | Sub-agents + past.dev shared run memory | running |
| [`exp/t9-env-subagents-v5-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-subagents-v5-pastdev) | Sub-agents v5 + past.dev | running |
| [`exp/t9-env-reviewer-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-pastdev) | Reviewer with memory of the tables it accepted | running |
| [`exp/t9-env-reviewer-dual-pastdev`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t9-env-reviewer-dual-pastdev) | Local reviewer + consistency reviewer with memory | running |
| [`exp/t11-baseline`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t11-baseline) | Task 11 baseline on Sherlock | 4 runs, done |
| [`exp/t11-v4-dag-orchestrator`](https://github.com/timothe-chaumont/BixBench3/tree/exp/t11-v4-dag-orchestrator) | First sub-agent orchestrator (source of t9 v4) | code only |
| [`exp/v2f`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v2f), [`exp/v3a`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3a)–[`v3e`](https://github.com/timothe-chaumont/BixBench3/tree/exp/v3e) | Task 11 batch 1 harness variants on GCP | single runs, see [results/task11](results/task11/) |
| [`sherlock/runner`](https://github.com/timothe-chaumont/BixBench3/tree/sherlock/runner), [`feat/task-envs-sherlock`](https://github.com/timothe-chaumont/BixBench3/tree/feat/task-envs-sherlock) | Sherlock runner; per-task environment images | infrastructure |
| [`setup/adapted-runner`](https://github.com/timothe-chaumont/BixBench3/tree/setup/adapted-runner), [`tools/bixdash`](https://github.com/timothe-chaumont/BixBench3/tree/tools/bixdash) | Earlier snapshots of the runner and dashboard, now merged into `main` | archived |

Original project notes: shared team setup **[6 vCPU + live dashboard](TEAM_SETUP.md)**. Upstream baseline commit
`d0e0bbb41222335b1b8878f533a58466a3a782dc`, included in this branch history.

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

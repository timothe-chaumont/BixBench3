# Adapted task 11 runner

This branch contains the runner used for the baseline, plus its exact upstream ancestor `d0e0bbb41222335b1b8878f533a58466a3a782dc`. The scientific harness, prompts, grading and network gateway were not changed. Inspect records remain under `iterations/baseline-task11/`.

## Adaptations

- CLI overrides for machine type and boot-disk size, including builder VMs.
- `--task11-runtime`: runtime omitting Cell Ranger and ARC, restricted to task 11. Requires a separate machine image; default full-runtime behavior remains available.
- Optional `--cost-limit` support; **not used in the final baseline**.
- Optional `BIXBENCH3_SSH_KEY_FILE` environment variable to control the SSH key used by gcloud.
- Run-plan summaries report effective hardware settings.

## Use

Install Python 3.12, uv and gcloud; authenticate GCP and the gated HF dataset, set provider API keys in environment variables. Install with `uv sync --locked`. No credentials or machine-local wrappers are included in this repository.

Build the task-specific runtime in your own project if it is not already available:

```sh
uv run bixbench3 setup-runtime --project YOUR_PROJECT \
  --machine-type n2-standard-8 --boot-disk-gb 200 --task11-runtime
```

Then launch (choose a private results bucket you control):

```sh
uv run bixbench3 run --task 11 --project YOUR_PROJECT \
  --machine-type n2-standard-8 --boot-disk-gb 200 --task11-runtime \
  --model openai/gpt-5.4-mini --effort max \
  --results-bucket gs://YOUR_RESULTS_BUCKET
```

Runtime image name: `bixbench3-runtime-v1-0-0-r7-task11-no10x`. The baseline's image was private to its GCP project. A new project must build or explicitly obtain access to a compatible image. This repository alone does not grant access to that image or private data.

Original limits remain 24 hours and 5,000 messages. Use `status`, then `complete` to collect a finished run and delete the VM; `cancel` stops it early. Persistent data disks/images/buckets are separate.

## Compare and iterate

```sh
git diff d0e0bbb41222335b1b8878f533a58466a3a782dc -- src tests
git switch -c exp/YOUR_VERSION
```

Keep each experimental run isolated, retain its code commit and record outputs in a new `iterations/<version>/` directory. Do not assume an existing experimental VM runs this exact commit: verify its source before use.

Pre-publication baseline validation: 146 tests passed, 2 skipped (missing companion PhDval checkout), Ruff clean. A focused verification is recorded in the publishing commit's work log. These checks do not establish scientific equivalence of the reduced runtime/hardware.

## Live experiment tracking

Use `--track-live --run-description "What this run tests" --condition YOUR_VERSION`
with a private `--results-bucket`. George's bixdash collector is installed on the
VM before the analyst starts; no runtime image rebuild is needed. Default cadence
is five minutes, with partial grading disabled (`--tracking-grade-every 0`). See
[the bixdash integration guide](tools/bixdash/README.md#integrated-runner-launch).

## Team profile (new experiments)

See [TEAM_SETUP.md](TEAM_SETUP.md) and `configs/team-6vcpu.json` for the shared
6-vCPU / 32-GB launcher and Cloud Run dashboard. Historical task 11 baseline
commands above describe the original 8-vCPU run. New disk-type/image overrides
are explicit; scientific harness/prompt defaults are unchanged.

### One GCP project per team member

Members can launch from their own project and still feed the shared dashboard:
add `--owner <name> --dashboard-uri gs://bixbench3-task11-jex20-results/_dashboard`
(also accepted by `scripts/run_team.py`). The shared project admin first runs
`tools/bixdash/tools/grant_dashboard_access.sh <member-project>` (write access limited
to the `_dashboard/` prefix). See TEAM_SETUP.md.


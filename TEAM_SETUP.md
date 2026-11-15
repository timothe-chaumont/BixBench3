# Shared team setup — 6 vCPU with live tracking

Use this setup for new experiments. The first task 11 baseline remains an **8-vCPU** historical run; its files and scores have not been relabeled.

## Environment and launch

Install Python 3.12, uv and gcloud, run `uv sync --locked`, authenticate GCP and the gated HF dataset, and set `OPENAI_API_KEY` privately. Never commit credentials. Configure `BIXBENCH3_SSH_KEY_FILE` if needed.

The shared profile is `configs/team-6vcpu.json`: **n2-custom-6-32768 = 6 vCPU / 32 GB RAM**, 200 GB boot disk, GPT-5.4 mini xhigh (`max` resolves to xhigh), original 24h/5,000-message limits, live tracking every 5 minutes, no partial grading. The upstream CLI defaults are preserved; use this launcher for the team profile.

```sh
uv run --locked python scripts/run_team.py \
  --task 11 --project YOUR_PROJECT --results-bucket gs://YOUR_PRIVATE_BUCKET \
  --condition baseline-6cpu-task11 \
  --description "Task 11 baseline, 6 vCPU, original scientific harness/prompt"
```

For task 9, use `--task 9` and a different condition/description. Every invocation creates a separate VM and results prefix. This launcher runs the **full selected task**, not an artifact subset.

The profile uses the existing machine image `bixbench3-runtime-v1-0-0-r7-task11-no10x`. Despite its historical name, it contains a generic scientific environment without licensed Cell Ranger tools. `--no10x-runtime` rejects any task whose staged runtime declares licensed tools. A new project must obtain access to a compatible private image or build one; the repo does not grant access to images or gated data. Scientific libraries may still need installation by the agent.

Boot disk defaults to **pd-standard** for parallel runs under the shared SSD quota. The team launcher restores that disk separately using `gcloud beta compute disks create` before attaching it to the analyst VM, because instance creation directly from a machine image can inherit its SSD allocation despite a disk-type override. The beta gcloud component is required (installed by gcloud with `--quiet` if needed). The restored device name is `persistent-disk-0`, verified in our shared image, and the zone is `us-central1-a`. If launch fails before attachment, the printed boot disk may remain and must be cleaned up or reused with `--boot-disk-source`. This trades I/O performance for capacity; report the disk type when comparing runs. To reproduce the first task 11 disk configuration while changing CPU only, add `--boot-disk-type pd-balanced`. The 200 GB size cannot be shrunk below the source image's disk size.

The shared project's CPU quota is 12. Two 6-vCPU analysts consume all of it: stage data with the temporary 4-vCPU loader before both analysts are active. The dashboard now runs on Cloud Run, so it does not consume Compute Engine CPU quota. SSD quota is 250 GB; standard-disk quota is 2,048 GB at last verification. Input disks remain pd-balanced. Check current usage before launch; don't stop a teammate's VM to free quota.

## Dashboard

Cloud Run URL: https://bixdash-385251430960.us-central1.run.app

The team explicitly chose **public access**: open the URL directly, without a token. This publishes dashboard metadata, metrics and activity excerpts; the underlying results bucket remains private. Cloud Run has `BIXDASH_PUBLIC=1` and no shared-token environment secret. The old `bixdash-web` VM is stopped.

**Launching from your own GCP project.** Add `--owner <name> --dashboard-uri gs://bixbench3-task11-jex20-results/_dashboard`
to `scripts/run_team.py`; snapshots then go to the shared bucket read by Cloud Run while your results bucket stays private.
Beforehand, an admin of the shared project runs `tools/bixdash/tools/grant_dashboard_access.sh <your-project-id>`, which grants
your project's default compute service account write access limited to the `_dashboard/` prefix. The installer prints
`OK: snapshots published to …` or an explicit warning if the write is refused. Details:
[multi-project tracking](tools/bixdash/README.md#plusieurs-projets-gcp-un-projet-par-membre-dashboard-central).

The integrated `--track-live` launcher copies George's collector to each analyst VM before the run starts. The observer reads the Inspect SQLite buffer in read-only mode, writes dashboard snapshots to `gs://<results-bucket>/_dashboard/`, and has low CPU/I/O priority. It adds some overhead, so record tracking cadence in comparisons. The web service reads those snapshots using a dedicated read-only service account.

Cloud Run deployment settings: 1 CPU, 512 MiB, min instances 0, max instances 1, request-based CPU allocation, explicit public mode (`BIXDASH_PUBLIC=1`). There is no always-on dashboard VM. Storage, build, registry and secret operations may still incur costs.

### Deploy the dashboard to another project

The dashboard build context is `tools/bixdash/dashboard/` (Dockerfile + pinned requirements). Build and push the image to your Artifact Registry, provision a runtime service account with `storage.objectViewer` on the results bucket, For a protected deployment, grant it access to a Secret Manager secret containing a shared token. For an intentionally public deployment, omit the secret and set `BIXDASH_PUBLIC=1`. Enable Cloud Run, Cloud Build, Artifact Registry and Secret Manager as needed.

```sh
gcloud run deploy bixdash --project YOUR_PROJECT --region us-central1 \
  --image YOUR_IMAGE --service-account YOUR_RUNTIME_SA \
  --command python --args server.py,--source,gs://YOUR_RESULTS_BUCKET/_dashboard \
  --set-secrets BIXDASH_TOKEN=YOUR_SECRET:1 \
  --cpu 1 --memory 512Mi --min-instances 0 --max-instances 1 \
  --concurrency 40 --port 8080 --timeout 60 --allow-unauthenticated
```

The example above is protected by an application token despite its publicly reachable infrastructure endpoint. For public mode, replace `--set-secrets ...` with `--set-env-vars BIXDASH_PUBLIC=1`. On Cloud Run the server fails closed without a token unless this explicit public flag is set. Public mode exposes metrics and activity excerpts, not the bucket itself.

## Versioning and completion

Create `exp/<version>` branches from main, keep one isolated VM per run, record code commit and a diff against upstream `d0e0bbb41222335b1b8878f533a58466a3a782dc`. Use the same model, effort, RAM, disk type and tracking cadence for controlled comparisons. Keep a distinct condition and results bundle under `iterations/<version>/`.

Use `status` to monitor, `complete` to collect a finished run and delete its VM, or `cancel` to terminate it early. The runner does not automatically delete completed VMs. Input disks, images and bucket objects persist separately.

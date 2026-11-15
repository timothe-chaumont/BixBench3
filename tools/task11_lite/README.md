# Task 11 lite: downstream v1

A separate development task, not a validated proxy for the full benchmark.
It retains all 85 libraries, all probes, dose/time groups and the four downstream
artifact contracts. The official reference count matrix is explicitly supplied
as an input, so the counting artifact is removed from both the prompt and score.
This measures DESeq2, ortholog mapping and enrichment conditional on correct
counts. It does not measure FASTQ alignment, package installation or recovery
from errors in upstream counts. Do not compare its four-artifact score directly
with the five-artifact full score.

The upstream Inspect react agent and tools are retained. R 4.0.2, DESeq2 1.28.0,
biomaRt 2.44.0 and PIANO 2.4.0 are installed before the agent starts. Input
references are public method resources, never downstream result tables. Frozen
MSigDB 6.2 GMTs and an Ensembl 100 mapping are allowed when available and their
checksums/provenance are recorded. Full controls and contrasts remain intact.

Agent budget: 600 seconds, 150 messages, 6 vCPU / 32 GiB. This is a runtime cap,
not evidence of successful completion in ten minutes. Initial environment
preparation, grading and the process judge are measured separately. Live
snapshots run once per minute. Runs use the separate dashboard task label
`11-lite-v1` and condition `baseline-lite-downstream-v1`.

Representativeness must be tested by running several harness variants on both
lite and full, repeating runs, and checking rank agreement, direction of gains
and per-artifact failure types. Keep final full evaluations independent of lite
tuning. This version is deliberately downstream-only.

The prepared environment uses available Bioconda patch versions DESeq2 1.28.0
and biomaRt 2.44.0, rather than the full prompt's 1.28.1 / 2.44.1. This is an
explicit environment adaptation and requires a matched full-run check.

## Launch on the existing team GCP setup

This v1 launcher reuses the full task 11 verified read-only data disk for its
metadata; raw FASTQs are not mounted into the lite agent. Prepare that disk once
with the team baseline setup. The reduced input bundle is private and contains
only the supplied counts and public reference resources, not downstream answers.
You need access to that bucket and to the gated HF release.

```sh
uv run python tools/task11_lite/prepare_inputs.py --work-dir operator-cache/task11-lite
uv run python tools/task11_lite/run_lite.py \
  --project YOUR_PROJECT --results-bucket gs://YOUR_RESULTS_BUCKET \
  --repo-root "$PWD" --work-dir operator-cache/task11-lite \
  --boot-disk-source YOUR_COMPATIBLE_RESTORED_BOOT_DISK
```

For repeat iterations on an **inactive** prepared VM, add
`--reuse-prepared-vm arb-run-...`. It refuses an active run, resets its failed
transient unit, archives previous files and observer state on the host, creates
a fresh run ID, and reloads the operator's private API key into memory. It does
not silently resume an interrupted scientific run. Collect or archive outputs
before eventually deleting this prepared VM; its disk remains billable.

The preparation script configures needrestart to defer automatic restarts of
`bixbench3-run.service`, Docker and containerd until the benchmark has finished.
Automatic package updates remain enabled. Ubuntu's automatic service restart
otherwise interrupts the run, whose EXIT cleanup correctly removes ephemeral
credentials; restarting the script without re-streaming those credentials fails.

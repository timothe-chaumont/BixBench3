"""Launch one preregistered job on one exclusively assigned prepared VM."""

import argparse
import dataclasses
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import bixbench3.gcp_runner as gcp
from bixbench3.config import RuntimeSettings, resolve_model

HERE = Path(__file__).resolve().parent
COUNT = "tempo_seq_filtered_counts"


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare_case(work, inputs, original, mode, profile="v2"):
    dataset = work / "dataset"
    if dataset.exists():
        history = work / "staging_attempts" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dataset), str(history))
    gcp.stage_hf_case(original, dataset)
    case = json.loads((dataset / "case.json").read_text())
    text = (inputs / "original-prompt.md").read_text()
    intro, outputs = text.split("## Required Outputs", 1)
    intro = intro.replace("DESeq2 1.28.1", "DESeq2 1.28.0").replace(
        "biomaRt 2.44.1", "biomaRt 2.44.0"
    )
    live = 'Use `biomaRt::useEnsembl(biomart = "genes", dataset = "mmusculus_gene_ensembl", version = 100)` and live BioMart queries through `https://apr2020.archive.ensembl.org/biomart/martservice` for mouse-to-human ortholog mapping.'
    intro = intro.replace(
        live,
        "Use the frozen official Ensembl 100 Compara mapping under data/reference/ensembl100-mouse-human.tsv for mouse-to-human ortholog mapping; this prepared-reference adaptation replaces the retired live BioMart endpoint.",
    )
    common = """# Prepared task 11 evaluation\n\nR 4.0.2, DESeq2 1.28.0, biomaRt 2.44.0 and PIANO 2.4.0 are installed and
verified before this run. Rscript and Python scientific packages are on PATH.
Reference resources under data/reference include Ensembl 100 orthologs and MSigDB
6.2 canonical and Hallmark GMTs, with provenance.json. Use these fixed public
references. These are shared preparation choices for both full and lite runs;
record the package patch versions and frozen-reference adaptation in METHODS.md.
"""
    if profile in ("v3", "v4"):
        common += """\nPrepared metadata: the data tree is mounted at /data (absolute path).\nThe installed R package name is lowercase `piano`: `library(piano)` and\n`packageVersion("piano")` work. The uppercase product name PIANO is not\na second R package to install. Check lowercase before attempting installation.\nThe original DNA-damage workbook is retained unchanged under /data/metadata.\n/data/reference/curated-dna-damage-all-sets.gmt contains the exact same 89\ngene-set names, source URLs and member genes, converted once to a text format.\nIt includes the set that the method guidance asks you to exclude; apply the\noriginal exclusion and background rules yourself. Its conversion provenance is\nin curated-dna-damage-all-sets.provenance.json. No statistical results are supplied.\nSample metadata columns: library_id, geo_accession, treatment_ppm (e.g. 0ppm),\ntimepoint (day7/day28/day90), organism, tissue, strain.\n\n"""
    if mode == "lite":
        case["expected_outputs"] = [
            a for a in case["expected_outputs"] if a["artifact_id"] != COUNT
        ]
        outputs = "\n### ".join(
            p
            for p in outputs.split("\n### ")
            if not p.lstrip().startswith("`tempo_seq_filtered_counts`")
        )
        before, method = intro.split("## Method Guidance", 1)
        de = method.split("Use DESeq2 ", 1)[1]
        intro = (
            before
            + "## Method Guidance\n\nStart from the provided raw integer counts at data/provided/counts.csv. Retain every probe separately using gene_probe_id and every library. Use DESeq2 "
            + de
        )
        # Remove a now-inapplicable description of local FASTQs from the objective.
        intro = intro.replace(
            "Analyze the primary sequencing reads to produce probe-level expression counts, identify treatment effects",
            "Starting from the provided counts, identify treatment effects",
        )
        common += "\nThis is the downstream-only lite task: all 85 samples, probes and contrasts are retained. Counts are explicitly supplied as input. Do not align FASTQs or produce tempo_seq_filtered_counts.csv. Only the four downstream outputs and METHODS.md are required. The counting artifact is excluded from this score.\n\n"
    else:
        common += "\nThis is the complete task: all 85 original FASTQs and all five output contracts are present. Produce counts from raw reads and all downstream artifacts.\n\n"
    (dataset / case["prompt"]["prompt_path"]).write_text(
        common + intro + "\n## Required Outputs" + outputs
    )
    (dataset / "case.json").write_text(json.dumps(case, indent=2) + "\n")
    return gcp.StagedCase(
        dataset,
        dataset / "case.json",
        {str(p.relative_to(dataset)): digest(p) for p in dataset.rglob("*") if p.is_file()},
    )


class PreparedExecutor(gcp.SubprocessExecutor):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

    def run(self, argv, **kwargs):
        a = list(argv)
        if ("instances" in a and "create" in a and self.vm in a) or (
            "attach-disk" in a and self.vm in a
        ):
            return subprocess.CompletedProcess(a, 0, "", "")
        return super().run(a, **kwargs)


class StudyRunner(gcp.GCPRunner):
    def build_run_plan(self, **kwargs):
        p = super().build_run_plan(**kwargs)
        old = p.layout.vm_name
        commands = {k: tuple(a.replace(old, self.vm) for a in v) for k, v in p.commands.items()}
        argv = tuple(
            "/opt/bixbench3/tools/proxy_study/inspect_task.py@proxy_study"
            if a.endswith("/inspect_harness/tasks.py@bixbench3_cases")
            else a
            for a in p.inspect_argv
        )
        argv += (
            "-T",
            f"budget_seconds={self.budget}",
            "-T",
            f"study_profile={self.profile}",
            "--model-cost-config",
            "/opt/bixbench3/tools/proxy_study/model-costs.json",
        )
        p = dataclasses.replace(
            p,
            layout=dataclasses.replace(p.layout, vm_name=self.vm),
            commands=commands,
            inspect_argv=argv,
        )
        self.plan = p
        return p

    def _initial_manifest(self, *args, **kwargs):
        m = super()._initial_manifest(*args, **kwargs)
        m["study_profile"] = {
            "version": "task11-prospective-" + self.profile,
            "job_id": self.job_id,
            "mode": self.mode,
            "variant": self.variant,
            "replicate": self.replicate,
            "harness_commit": self.commit,
            "harness_archive_sha256": digest(self.work / "harness.tar.gz"),
            "actor_budget_s": self.budget,
            "common_downstream_artifacts": 4,
            "scored_artifacts": 4 if self.mode == "lite" else 5,
            "count_matrix_supplied": self.mode == "lite",
            "process_judge": "not_run_primary_artifact_study",
            "reference_provenance": json.loads(
                (self.inputs / "reference-data/provenance.json").read_text()
            ),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=HERE, text=True
            ).strip(),
        }
        return m

    def _install_live_tracking(self, p):
        base = ("gcloud", "--project", self.project)
        self.executor.run(
            gcp.ssh_argv(
                base,
                self.vm,
                p.zone,
                ("bash", "-c", "rm -rf ~/proxy-study-code ~/proxy-study-inputs"),
            )
        )
        for src, dst in [
            (HERE, "proxy-study-code"),
            (self.work / "harness.tar.gz", "harness.tar.gz"),
            (
                self.inputs
                / ("upload-" + self.profile if self.profile in ("v3", "v4") else "upload"),
                "proxy-study-inputs",
            ),
            (HERE.parent / "task11_lite/grade_lite.py", "grade_lite.py"),
        ]:
            recursive = ("--recurse",) if src.is_dir() else ()
            self.executor.run(
                (
                    *base,
                    "compute",
                    "scp",
                    *recursive,
                    str(src),
                    f"{self.vm}:~/{dst}",
                    f"--zone={p.zone}",
                )
            )
        data = f"/var/lib/bixbench3/study_inputs/{p.layout.run_id}"
        script = f"""set -euo pipefail
sudo mkdir -p /opt/bixbench3/tools /opt/bixbench3/harness_history
sudo cp -a ~/proxy-study-code/. /opt/bixbench3/tools/proxy_study/
sudo cp ~/grade_lite.py /opt/bixbench3/tools/proxy_study/grade_lite.py
sudo mv /opt/bixbench3/src/bixbench3/inspect_harness /opt/bixbench3/harness_history/{p.layout.run_id}
sudo tar -xzf ~/harness.tar.gz -C /opt/bixbench3
sudo bash /opt/bixbench3/tools/proxy_study/prepare_vm.sh > /var/lib/bixbench3/runtime-inventory.txt 2>&1
sudo cp ~/harness.tar.gz /var/lib/bixbench3/harness.tar.gz
sudo bash -s <<'DATA'
set -euo pipefail
data={data}
mkdir -p "$data"
cp -a /mnt/bixbench3-data/data/metadata "$data/metadata"
DATA
"""
        # Input copy runs as the SSH user to avoid guessing its home under sudo.
        script += f"""sudo cp -a ~/proxy-study-inputs/reference-data {data}/reference
"""
        if self.mode == "lite":
            script += f"""sudo mkdir -p {data}/provided
sudo cp ~/proxy-study-inputs/provided_counts.csv {data}/provided/counts.csv
"""
        else:
            script += f"""sudo mkdir -p {data}/raw
sudo mount --bind /mnt/bixbench3-data/data/raw {data}/raw
sudo mount -o remount,bind,ro {data}/raw
"""
        script += f"""sudo chmod -R a+rX {data}/metadata {data}/reference
"""
        if self.mode == "lite":
            script += f"""sudo chmod -R a+rX {data}/provided
"""
        self.executor.run(gcp.ssh_argv(base, self.vm, p.zone, ("bash", "-s")), input_text=script)
        # Supply explicit scope before the first observer snapshot.
        meta = {
            "task_id": p.task.task_id,
            "time_limit_s": self.budget,
            "owner": "timothe",
            "evaluation_scope": f"proxy-study-{self.mode}-{self.profile}",
            "study_job_id": self.job_id,
        }
        script = "sudo mkdir -p /var/lib/bixdash; sudo chmod 700 /var/lib/bixdash; sudo sh -c 'cat > /var/lib/bixdash/run_meta.json'"
        self.executor.run(
            gcp.ssh_argv(base, self.vm, p.zone, ("bash", "-c", script)), input_text=json.dumps(meta)
        )
        super()._install_live_tracking(p)


def archive_previous(executor, project, vm):
    script = """set -euo pipefail
if sudo systemctl is-active --quiet bixbench3-run.service; then echo 'ACTIVE RUN: refusing reuse'; exit 1; fi
sudo systemctl stop bixdash-collect.timer bixdash-collect.service || true
sudo systemctl reset-failed bixbench3-run.service || true
sudo docker ps -a --format '{{.ID}} {{.Names}}' | awk '$2 ~ /^inspect-/ {print $1}' | xargs -r sudo docker rm -f
sudo python3 - <<'ARCHIVE'
from pathlib import Path
from datetime import datetime,UTC
import shutil
root=Path('/var/lib/bixbench3');archive=root/'previous-runs'/datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ');archive.mkdir(parents=True,mode=0o700)
for name in ['inspect_logs','artifact_grades','outputs','agent_artifacts','grade.json','judge.json','status.json','run_manifest.json','run.sh','workspace','broker','broker_logs','broker_cache','dataset','study_metrics.json','final_usage.json','runtime-inventory.txt','harness.tar.gz']:
 p=root/name
 if p.exists():shutil.move(str(p),str(archive/name))
p=Path('/var/lib/bixdash')
if p.exists():shutil.move(str(p),str(archive/'observer'))
ARCHIVE
"""
    executor.run(
        gcp.ssh_argv(("gcloud", "--project", project), vm, "us-central1-a", ("bash", "-s")),
        input_text=script,
    )


def main():
    ap = argparse.ArgumentParser()
    for name in [
        "project",
        "vm",
        "mode",
        "variant",
        "commit",
        "job-id",
        "work-dir",
        "inputs-dir",
        "repo-root",
        "source-repo",
    ]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--budget", type=int, required=True)
    ap.add_argument("--replicate", type=int, default=1)
    ap.add_argument("--profile", choices=["v2", "v3", "v4"], default="v2")
    a = ap.parse_args()
    work = Path(a.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    inputs = Path(a.inputs_dir).resolve()
    if (work / "launch.json").exists():
        raise RuntimeError(
            "This job already has a launch manifest; collect or resume it instead of relaunching"
        )
    original = gcp.load_public_task("11")
    case = prepare_case(work, inputs, original, a.mode, a.profile)
    subprocess.run(
        [
            "git",
            "archive",
            "--format=tar.gz",
            "-o",
            str(work / "harness.tar.gz"),
            a.commit,
            "src/bixbench3/inspect_harness",
        ],
        cwd=a.source_repo,
        check=True,
    )
    executor = PreparedExecutor(a.vm)
    value = executor.run(
        (
            "gcloud",
            "--project",
            a.project,
            "compute",
            "instances",
            "describe",
            a.vm,
            "--zone=us-central1-a",
            "--format=json",
        ),
        capture_output=True,
    )
    vm = json.loads(value.stdout)
    if not vm["machineType"].endswith("/n2-custom-6-32768"):
        raise ValueError("Wrong VM shape")
    if not any(
        d.get("deviceName") == "bixbench3-data"
        and original.input_manifest_sha256[:12] in d.get("source", "")
        and d.get("mode") == "READ_ONLY"
        for d in vm["disks"]
    ):
        raise ValueError("Wrong data disk or writable data")
    archive_previous(executor, a.project, a.vm)
    task = dataclasses.replace(original, task_id="11-study-" + a.mode + "-" + a.profile)
    settings = RuntimeSettings(
        machine_type="n2-custom-6-32768",
        boot_disk_gb=200,
        boot_disk_type="pd-standard",
        boot_disk_source=next(d["source"].rsplit("/", 1)[-1] for d in vm["disks"] if d.get("boot")),
        include_10x=False,
        runtime_image_name="bixbench3-runtime-v1-0-0-r7-task11-no10x",
        time_limit_seconds=a.budget,
        message_limit=5000,
        analyst_cost_limit=6 if a.mode == "full" else 2,
        track_live=True,
        run_description=f"Proxy study {a.profile} | {a.mode} | {a.variant} | {a.budget // 60}min | repeat {a.replicate}",
        run_condition="baseline-proxy-study-" + a.profile
        if a.variant == "baseline"
        else a.variant + "-proxy-study-" + a.profile,
        tracking_grade_every=0,
    )
    runner = StudyRunner(
        project=a.project,
        executor=executor,
        settings=settings,
        repo_root=Path(a.repo_root),
        runs_root=Path(a.repo_root) / "runs",
    )
    for key, val in {
        "profile": a.profile,
        "vm": a.vm,
        "mode": a.mode,
        "variant": a.variant,
        "commit": a.commit,
        "replicate": a.replicate,
        "budget": a.budget,
        "job_id": a.job_id,
        "work": work,
        "inputs": inputs,
    }.items():
        setattr(runner, key, val)
    original_script = gcp.remote_run_script

    def script(plan, settings):
        text = original_script(plan, settings)
        text = text.replace(
            "export BIXBENCH3_DATA_DIR=/mnt/bixbench3-data/data",
            f"export BIXBENCH3_DATA_DIR=/var/lib/bixbench3/study_inputs/{plan.layout.run_id}",
        )
        text = text.replace(
            "export BIXBENCH3_SANDBOX_IMAGE=bixbench3-sandbox:1.0.0",
            "export BIXBENCH3_SANDBOX_IMAGE=bixbench3-sandbox:proxy-study-v2",
        )
        if a.mode == "lite":
            text = text.replace(
                "from bixbench3.gcp_runner import TaskSpec, grade_existing_artifacts",
                'from bixbench3.gcp_runner import TaskSpec\nsys.path.insert(0,"/opt/bixbench3/tools/proxy_study")\nfrom grade_lite import grade_existing_artifacts',
            )
        begin = text.index('write_status judging judging "$run_status"')
        end = text.index(f"python3 - {settings.remote_root} /dev/shm/bixbench3.env", begin)
        text = (
            text[:begin]
            + """judge_status=0
printf '{"judge_status":"not_run","reason":"prospective artifact-score study; secondary judge disabled equally"}\\n' > /var/lib/bixbench3/judge.json
"""
            + text[end:]
        )
        # Compute final metrics after sanitization but before upload.
        begin = text.index('write_status uploading running "$run_status"')
        metrics = """uv run python /opt/bixbench3/tools/proxy_study/record_metrics.py /var/lib/bixbench3 || true
"""
        text = text[:begin] + metrics + text[begin:]
        text = text.replace(
            "broker_logs run_manifest.json; do",
            "broker_logs run_manifest.json study_metrics.json final_usage.json runtime-inventory.txt harness.tar.gz; do",
        )
        assert "run_process_judge(" not in text
        assert "proxy-study-v2" in text
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)
        (work / "remote_run.sh").write_text(text)
        return text

    gcp.remote_run_script = script
    model = resolve_model("openai/gpt-5.4-mini", "max")
    result = runner._run_staged_task(
        task=task,
        model=model,
        environment=gcp.selected_environment(gcp.required_environment_keys(model)),
        staged_case=case,
        results_bucket="gs://bixbench3-task11-jex20-results",
    )
    (work / "launch.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

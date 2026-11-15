from __future__ import annotations

import argparse
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from bixbench3.cli import (
    _print_grade_summary,
    _print_judge_summary,
    _print_run_follow_up,
    build_parser,
)
from bixbench3.config import RuntimeSettings, resolve_model
from bixbench3.gcp_runner import (
    GCPRunner,
    TaskSpec,
    build_runtime_plan,
    create_runtime_source_archive,
    environment_file,
    file_sha256,
    hf_download,
    loader_copy_script,
    remote_builder_prepare_script,
    remote_prepare_script,
    remote_run_script,
    remote_runtime_build_script,
    remote_runtime_smoke_script,
    required_environment_keys,
    stage_hf_case,
    validate_safe_argv,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        input_text: str | None = None,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del input_text, check, capture_output
        command = tuple(argv)
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


@pytest.mark.parametrize("machine_type", ["n2-standard-8", "n2-standard-32"])
def test_machine_type_controls_analyst_builder_and_summary(
    task: TaskSpec, tmp_path: Path, machine_type: str,
) -> None:
    settings = RuntimeSettings(machine_type=machine_type)
    runner = GCPRunner(
        project="example-project", executor=RecordingExecutor(), settings=settings,
        runs_root=tmp_path, repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task, model=resolve_model("openai/gpt-5.5", "max"), results_bucket=None,
    )
    assert f"--machine-type={machine_type}" in plan.commands["create_run_vm"]
    assert plan.public_summary()["machine_type"] == machine_type
    build = build_runtime_plan(
        project="example-project", settings=settings,
        source_archive=tmp_path / "source.tar.gz", source_archive_sha256="a" * 64,
        cellranger_tarball=tmp_path / "cellranger.tar.gz",
        cellranger_arc_tarball=tmp_path / "cellranger-arc.tar.gz",
        cellranger_sha256="b" * 64, cellranger_arc_sha256="c" * 64,
    )
    assert f"--machine-type={machine_type}" in build.commands["create_builder"]
    arguments = build_parser().parse_args([
        "run", "--task", "11", "--model", "openai/gpt-5.5", "--effort", "max",
        "--project", "example-project", "--machine-type", machine_type,
    ])
    assert arguments.machine_type == machine_type
    setup_arguments = build_parser().parse_args([
        "setup-runtime", "--project", "example-project", "--machine-type", machine_type,
        "--cellranger-tarball", "cellranger.tar.gz",
        "--cellranger-arc-tarball", "cellranger-arc.tar.gz",
    ])
    assert setup_arguments.machine_type == machine_type


def test_task11_runtime_build_requires_no_vendor_archives(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        machine_type="n2-standard-8", include_10x=False,
        boot_disk_gb=200,
        runtime_image_name="bixbench3-runtime-v1-0-0-r7-task11-no10x",
    )
    runner = GCPRunner(
        project="example-project", executor=RecordingExecutor(), settings=settings,
        repo_root=Path(__file__).resolve().parents[2], runs_root=tmp_path,
    )
    result = runner.setup_runtime(dry_run=True)
    assert result["include_10x"] is False
    assert result["image_name"].endswith("task11-no10x")
    assert "copy_cellranger" not in result["commands"]
    assert "copy_cellranger_arc" not in result["commands"]
    assert "--boot-disk-size=200GB" in result["commands"]["create_builder"]
    script = remote_runtime_build_script(
        source_archive_sha256="a" * 64,
        cellranger_sha256="not-installed", cellranger_arc_sha256="not-installed",
        image_tag="test-sandbox:task11", include_10x=False,
    )
    assert "install -m 0600" not in script
    assert "--build-arg CELLRANGER_TARBALL=" not in script
    assert '"runtime_profile": "task11-no10x"' in script
    smoke = remote_runtime_smoke_script(
        sandbox_image_tag="test-sandbox:task11", network_gateway_image_tag="test-gateway:task11",
        include_10x=False,
    )
    assert "cellranger --version" not in smoke
    assert "cellranger-arc --version" not in smoke
    assert "Rscript --version" in smoke
    assert "docker compose" in smoke
    for payload in (script, smoke):
        subprocess.run(["bash", "-n"], input=payload, text=True, check=True)


def test_analyst_cost_limit_is_forwarded_to_inspect(task: TaskSpec, tmp_path: Path) -> None:
    runner = GCPRunner(
        project="example-project", executor=RecordingExecutor(),
        settings=RuntimeSettings(analyst_cost_limit=60.0),
        repo_root=tmp_path, runs_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task, model=resolve_model("openai/gpt-5.4-mini", "max"), results_bucket=None,
    )
    index = plan.inspect_argv.index("--cost-limit")
    assert plan.inspect_argv[index + 1] == "60.0"


@pytest.fixture
def task() -> TaskSpec:
    return TaskSpec(
        task_id="1",
        paper_id="10.1234_example",
        input_manifest_uri=(
            "gs://bixbench3-inputs/releases/v1.0.0/manifests/10.1234_example.json"
        ),
        input_manifest_sha256="a" * 64,
        input_size_bytes=100 * 1024**3,
        grader_manifest_url=(
            "https://storage.googleapis.com/bixbench3-ground-truth/"
            "releases/v1.0.0/manifests/10.1234_example.json"
        ),
        grader_manifest_sha256="b" * 64,
    )


def test_score_only_plan_has_fixed_vm_and_no_service_account(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "max"),
        results_bucket=None,
    )

    create = plan.commands["create_run_vm"]
    attach = plan.commands["attach_data_disk"]
    assert isinstance(create, tuple)
    assert "--machine-type=n2-standard-32" in create
    assert any("size=500,type=pd-balanced" in arg for arg in create)
    assert (
        "--source-machine-image=projects/example-project/global/machineImages/"
        "bixbench3-runtime-v1-0-0-r7"
    ) in create
    assert "--no-service-account" in create
    assert "--no-scopes" in create
    assert "--mode=ro" in attach
    assert "--device-name=bixbench3-data" in attach
    assert plan.results_uri is None
    inspect = plan.inspect_argv
    assert any(value.endswith("tasks.py@bixbench3_cases") for value in inspect)
    assert "dataset_path=/var/lib/bixbench3/dataset/case.json" in inspect
    assert "effort=xhigh" in inspect
    assert not any("task_id=" in value for value in inspect)
    assert not any("hf_revision=" in value for value in inspect)
    assert not any("message_limit=" in value for value in inspect)
    assert not any("time_limit=" in value for value in inspect)


def test_full_bundle_uses_default_compute_service_account(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("anthropic/claude-opus-4-8", "max"),
        results_bucket="gs://my-existing-results/benchmark",
        default_service_account="123456-compute@developer.gserviceaccount.com",
    )

    create = plan.commands["create_run_vm"]
    assert "--service-account=123456-compute@developer.gserviceaccount.com" in create
    assert "--scopes=https://www.googleapis.com/auth/cloud-platform" in create
    assert "--no-service-account" not in create
    assert plan.results_uri is not None
    assert plan.results_uri.startswith("gs://my-existing-results/benchmark/")
    summary = plan.public_summary()
    assert summary["required_environment_keys"] == [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ]
    assert summary["process_judge"] == {
        "model": "openai/gpt-5.5",
        "reasoning_effort": {"requested": "max", "resolved": "xhigh"},
        "temperature": 0,
        "max_tool_output_chars": 4000,
        "max_trace_chars": 120000,
        "prompt_sha256": "0972e209a26712cc3bf9272a30df6402c40be784a22233bae91eefd94e647dda",
        "required_environment_keys": ["OPENAI_API_KEY"],
    }


def test_first_run_disk_is_balanced_and_loader_is_temporary(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("google/gemini-3.5-flash", "high"),
        results_bucket=None,
    )

    create_disk = plan.commands["create_data_disk"]
    create_loader = plan.commands["create_loader_vm"]
    delete_loader = plan.commands["delete_loader_vm"]
    assert "--type=pd-balanced" in create_disk
    assert any(value.startswith("--size=") for value in create_disk)
    assert any("device-name=bixbench3-data,mode=rw,boot=no" in value for value in create_loader)
    assert "delete" in delete_loader
    assert plan.layout.data_disk_name not in delete_loader


def test_commands_never_contain_api_key_values(
    task: TaskSpec,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-proj-super-secret-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "high"),
        results_bucket=None,
    )

    flattened = "\n".join(argument for command in plan.commands.values() for argument in command)
    assert secret not in flattened
    assert "/dev/shm/bixbench3.env" in flattened
    assert secret in environment_file({"OPENAI_API_KEY": secret})


def test_every_run_requires_openai_key_for_process_judge() -> None:
    model = resolve_model("anthropic/claude-opus-4-8", "max")

    assert required_environment_keys(model) == (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ("gcloud", "storage", "mv", "gs://source/a", "gs://destination/a"),
        ("gcloud", "storage", "rm", "gs://source/a"),
        ("gcloud", "storage", "rsync", "--delete", "gs://source", "gs://destination"),
        ("gcloud", "compute", "disks", "delete", "source-disk"),
    ],
)
def test_destructive_source_commands_are_rejected(argv: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        validate_safe_argv(argv)


def test_only_ephemeral_bixbench3_vms_can_be_deleted() -> None:
    with pytest.raises(ValueError):
        validate_safe_argv(("gcloud", "compute", "instances", "delete", "unrelated-vm"))
    validate_safe_argv(("gcloud", "compute", "instances", "delete", "arb-run-example"))


def test_cli_exposes_lifecycle_commands_and_requires_effort() -> None:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    assert set(subparsers.choices) == {
        "setup-runtime",
        "run",
        "status",
        "complete",
        "cancel",
        "grade",
    }

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "run",
                "--task",
                "1",
                "--model",
                "openai/gpt-5.5",
                "--project",
                "example-project",
            ]
        )


def test_run_output_ends_with_lifecycle_instructions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_run_follow_up(
        {
            "follow_up_commands": {
                "status": "bixbench3 status --run example",
                "complete": "bixbench3 complete --run example",
                "cancel": "bixbench3 cancel --run example",
            }
        }
    )

    output = capsys.readouterr().out
    assert "Monitor the detached run" in output
    assert "collect grades and delete the VM" in output
    assert output.rstrip().endswith("The VM remains billable until you run complete or cancel.")


def test_grade_summary_prints_overall_and_artifact_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_grade_summary(
        {
            "score": 0.75,
            "artifacts": [
                {"artifact_id": "one", "score": 0.5},
                {"artifact_id": "two", "score": 1.0},
            ],
        },
        tmp_path,
    )

    output = capsys.readouterr().out
    assert "Overall paper grade: 0.750000" in output
    assert f"Overall grade file: {tmp_path / 'grade.json'}" in output
    assert f"one: 0.500000 ({tmp_path / 'artifact_grades' / 'one.json'})" in output
    assert f"Artifact grade directory: {tmp_path / 'artifact_grades'}" in output


def test_judge_summary_prints_score_status_and_failure_modes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_judge_summary(
        {
            "judge_score": 0.625,
            "judge_status": "ok",
            "failure_modes": [
                {"tag": "incomplete_data", "evidence": "one sample was omitted"}
            ],
        },
        tmp_path,
    )

    output = capsys.readouterr().out
    assert "Process judge score: 0.625000" in output
    assert "Process judge status: ok" in output
    assert "Failure modes: incomplete_data" in output
    assert f"Process judge file: {tmp_path / 'judge.json'}" in output


def test_success_cleanup_deletes_and_failure_cleanup_stops(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor()
    runner = GCPRunner(
        project="example-project",
        executor=executor,
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "high"),
        results_bucket=None,
    )

    success = runner._cleanup_run_vm(plan, succeeded=True)
    failure = runner._cleanup_run_vm(plan, succeeded=False)

    assert success["action"] == "deleted"
    assert failure["action"] == "stopped"
    assert failure["ongoing_disk_cost_warning"] is True
    assert "delete" in executor.calls[-2]
    assert "stop" in executor.calls[-1]


def test_streamed_remote_scripts_have_valid_shell_syntax(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    settings = RuntimeSettings()
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        settings=settings,
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "high"),
        results_bucket="gs://my-existing-results/benchmark",
        default_service_account="123456-compute@developer.gserviceaccount.com",
    )
    scripts = (
        loader_copy_script(task),
        remote_builder_prepare_script(),
        remote_runtime_build_script(
            source_archive_sha256="c" * 64,
            cellranger_sha256="a" * 64,
            cellranger_arc_sha256="b" * 64,
            image_tag="bixbench3-sandbox:1.0.0",
        ),
        remote_runtime_smoke_script(
            sandbox_image_tag="bixbench3-sandbox:1.0.0",
            network_gateway_image_tag=("bixbench3-network-gateway:1.0.0"),
        ),
        remote_run_script(plan, settings),
    )

    for script in scripts:
        result = subprocess.run(
            ("bash", "-n"),
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_authenticated_hf_download_uses_only_local_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloaded = tmp_path / "runtime.json"
    downloaded.write_text("{}", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_download(**kwargs: object) -> str:
        observed.update(kwargs)
        return str(downloaded)

    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        fake_download,
    )

    assert hf_download("cases/example/runtime/runtime.json") == downloaded
    assert observed["repo_type"] == "dataset"
    assert observed["revision"] == "v1.0.0"
    assert observed["token"] is None


def test_stages_checksum_verified_one_case_dataset(
    task: TaskSpec,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub_root = tmp_path / "hub"
    package_files = {
        f"cases/{task.paper_id}/agent/prompt.md": "# task\n",
        f"cases/{task.paper_id}/agent/task_body.json": "{}\n",
        f"cases/{task.paper_id}/agent/inputs_metadata.json": "{}\n",
        f"cases/{task.paper_id}/runtime/runtime.json": json.dumps(
            {
                "paper_id": task.paper_id,
                "expected_outputs": [],
                "network_policy": {
                    "mode": "allowlist_with_tool",
                    "fetch_instead_of_allow_domains": ["github.com"],
                },
            }
        ),
    }
    hashes: dict[str, str] = {}
    for relative, content in package_files.items():
        path = hub_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        hashes[relative] = file_sha256(path)
    release = hub_root / "release.json"
    release.write_text(
        json.dumps({"files_sha256": hashes}),
        encoding="utf-8",
    )

    def fake_hf_download(filename: str) -> Path:
        return hub_root / filename

    monkeypatch.setattr(
        "bixbench3.gcp_runner.hf_download",
        fake_hf_download,
    )
    staged = stage_hf_case(task, tmp_path / "staged" / "dataset")

    case = json.loads(staged.dataset_path.read_text(encoding="utf-8"))
    assert case["task_id"] == task.paper_id
    assert case["prompt"] == {"prompt_path": f"cases/{task.paper_id}/agent/prompt.md"}
    assert "fetch_instead_of_allow_domains" not in case["network_policy"]
    assert set(staged.file_sha256) == {*package_files, "case.json"}
    assert not any("ground-truth" in path.as_posix() for path in staged.dataset_dir.rglob("*"))


def test_scp_staged_case_and_grade_only_after_inspect(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "high"),
        results_bucket=None,
        case_dataset_dir=dataset_dir,
    )

    copy_command = plan.commands["copy_case_dataset"]
    assert str(dataset_dir.resolve()) in copy_command
    assert "--recurse" in copy_command
    script = remote_run_script(plan, RuntimeSettings())
    inspect_at = script.index("inspect_harness/tasks.py@bixbench3_cases")
    outputs_at = script.index("/outputs/.")
    ground_truth_at = script.index("/host_ground_truth")
    grade_at = script.index("grade_existing_artifacts(")
    judge_at = script.index("run_process_judge(")
    redaction_at = script.index("secret_values:")
    assert inspect_at < outputs_at < ground_truth_at < grade_at < judge_at < redaction_at
    assert "judge.json" in script
    assert "write_status judging judging" in script
    assert "huggingface.co" not in script
    assert "bixbench3 grade --task" not in script


def test_runtime_source_archive_is_clean_and_deterministic(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    for filename in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
        path = repo / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename, encoding="utf-8")
    for relative in (
        "src/bixbench3/module.py",
        "sandbox/Dockerfile",
        "src/.venv/secret",
        "src/__pycache__/module.pyc",
        "sandbox/runs/stale.txt",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")

    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    create_runtime_source_archive(repo, first)
    create_runtime_source_archive(repo, second)

    assert file_sha256(first) == file_sha256(second)
    with tarfile.open(first, "r:gz") as archive:
        members = {member.name for member in archive}
    assert "src/bixbench3/module.py" in members
    assert "sandbox/Dockerfile" in members
    assert not any(".venv" in member for member in members)
    assert not any(".git" in member for member in members)
    assert not any("runs" in Path(member).parts for member in members)
    assert not any("__pycache__" in member for member in members)


def test_runtime_script_sets_exact_compose_environment(
    task: TaskSpec,
    tmp_path: Path,
) -> None:
    runner = GCPRunner(
        project="example-project",
        executor=RecordingExecutor(),
        runs_root=tmp_path,
        repo_root=tmp_path,
    )
    plan = runner.build_run_plan(
        task=task,
        model=resolve_model("openai/gpt-5.5", "high"),
        results_bucket=None,
    )
    script = remote_run_script(plan, RuntimeSettings())

    for name in (
        "BIXBENCH3_NETWORK_GATEWAY_IMAGE",
        "BIXBENCH3_BROKER_POLICY",
        "BIXBENCH3_BROKER_LOG_DIR",
        "BIXBENCH3_BROKER_CACHE_DIR",
        "BIXBENCH3_WORKSPACE_DIR",
        "BIXBENCH3_BROKER_TOKEN",
        "BIXBENCH3_SANDBOX_IMAGE",
        "BIXBENCH3_DATA_DIR",
        "BIXBENCH3_OUTPUTS_DIR",
    ):
        assert f"export {name}=" in script


def test_run_vm_preparation_grants_docker_socket_access() -> None:
    script = remote_prepare_script(RuntimeSettings())

    assert "chmod 0666 /var/run/docker.sock" in script


def test_runtime_build_creates_both_private_compose_images() -> None:
    script = remote_runtime_build_script(
        source_archive_sha256="c" * 64,
        cellranger_sha256="a" * 64,
        cellranger_arc_sha256="b" * 64,
        image_tag="bixbench3-sandbox:1.0.0",
    )
    smoke = remote_runtime_smoke_script(
        sandbox_image_tag="bixbench3-sandbox:1.0.0",
        network_gateway_image_tag="bixbench3-network-gateway:1.0.0",
    )

    assert "--tag bixbench3-sandbox:1.0.0" in script
    assert "--tag bixbench3-network-gateway:1.0.0" in script
    assert "sandbox/Dockerfile" in script
    assert "network_gateway/Dockerfile" in script
    assert "docker image inspect bixbench3-network-gateway:1.0.0" in smoke
    assert "docker compose -f sandbox/compose.yaml config" in smoke


def test_live_tracking_installs_separate_collector_without_partial_grading(
    task: TaskSpec, tmp_path: Path,
) -> None:
    from dataclasses import replace

    executor = RecordingExecutor()
    source = tmp_path / "tools" / "bixdash" / "vm"
    source.mkdir(parents=True)
    for name in ("collect.py", "install_collector.sh"):
        (source / name).write_text("# collector fixture\n")
    runner = GCPRunner(
        project="example-project", executor=executor, repo_root=tmp_path,
        settings=RuntimeSettings(track_live=True, run_description="Task 9 baseline", run_condition="baseline-task9"),
    )
    model = resolve_model("openai/gpt-5.4-mini", "max")
    plan = runner.build_run_plan(task=task, model=model, results_bucket="gs://example-results")
    runner._install_live_tracking(plan)
    assert len(executor.calls) == 2
    assert "scp" in executor.calls[0]
    command = executor.calls[1][-1]
    assert "--grade-every 0" in command
    assert "--interval 5min" in command
    assert "'Task 9 baseline'" in command
    script = remote_run_script(plan, runner.settings)
    assert "# RUN_DESCRIPTION: Task 9 baseline" in script
    assert "systemctl start bixdash-collect.service || true" in script
    assert "bixdash-collect.service" not in remote_run_script(plan, replace(runner.settings, track_live=False))


def test_live_tracking_forwards_central_dashboard_and_owner(task: TaskSpec, tmp_path: Path) -> None:
    executor = RecordingExecutor()
    source = tmp_path / "tools" / "bixdash" / "vm"
    source.mkdir(parents=True)
    for name in ("collect.py", "install_collector.sh"):
        (source / name).write_text("# collector fixture\n")
    runner = GCPRunner(
        project="member-project", executor=executor, repo_root=tmp_path,
        settings=RuntimeSettings(
            track_live=True, run_description="v2a: validation gates", run_condition="v2a",
            dashboard_uri="gs://team-dashboard/_dashboard", run_owner="georges",
        ),
    )
    model = resolve_model("openai/gpt-5.4-mini", "max")
    plan = runner.build_run_plan(task=task, model=model, results_bucket="gs://member-results")
    runner._install_live_tracking(plan)
    command = executor.calls[1][-1]
    assert "--dashboard-uri gs://team-dashboard/_dashboard" in command
    assert "--owner georges" in command


def test_tracking_rejects_non_gcs_dashboard_uri() -> None:
    from bixbench3.cli import _runner

    with pytest.raises(ValueError, match="gs://"):
        _runner("project", dashboard_uri="https://example.org/x")


def test_tracking_requires_description_and_nonnegative_interval() -> None:
    from bixbench3.cli import _runner

    with pytest.raises(ValueError, match="description"):
        _runner("project", track_live=True)
    with pytest.raises(ValueError, match="nonnegative"):
        _runner("project", tracking_grade_every=-1)
    with pytest.raises(ValueError, match="single-line"):
        _runner("project", run_description="first\nsecond")


def test_shared_six_cpu_profile_and_disk_override(task: TaskSpec, tmp_path: Path) -> None:
    from bixbench3.cli import _runner

    runner = _runner('example-project', machine_type='n2-custom-6-32768', boot_disk_gb=200,
                     boot_disk_type='pd-standard', runtime_image='shared-no10x', no10x_runtime=True)
    plan = runner.build_run_plan(task=task, model=resolve_model('openai/gpt-5.4-mini', 'max'),
                                 results_bucket='gs://example-results')
    assert '--machine-type=n2-custom-6-32768' in plan.commands['create_run_vm']
    assert any('device-name=persistent-disk-0,size=200,type=pd-standard' in arg for arg in plan.commands['create_run_vm'])
    assert plan.public_summary()['boot_disk_type'] == 'pd-standard'
    assert runner.settings.include_10x is False
    assert runner.settings.runtime_image_name == 'shared-no10x'
    with pytest.raises(ValueError, match='requires --runtime-image'):
        _runner('example-project', no10x_runtime=True)


def test_no10x_runtime_rejects_licensed_task_before_cloud(tmp_path: Path, task: TaskSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    import bixbench3.gcp_runner as module

    path = tmp_path / 'case.json'
    path.write_text(json.dumps({'licensed_runtime_tools': ['cellranger']}))
    staged = module.StagedCase(tmp_path, path, {})
    monkeypatch.setattr(module, 'stage_hf_case', lambda *args: staged)
    monkeypatch.setattr(module, 'selected_environment', lambda *args: {})
    executor = RecordingExecutor()
    runner = GCPRunner(project='example-project', executor=executor,
                       settings=RuntimeSettings(include_10x=False))
    with pytest.raises(ValueError, match='requires licensed'):
        runner.run_task(task=task, model=resolve_model('openai/gpt-5.4-mini', 'max'))
    assert executor.calls == []


def test_restored_standard_boot_avoids_inheriting_machine_image_disks(task: TaskSpec) -> None:
    from bixbench3.cli import _runner

    runner = _runner('example-project', boot_disk_source='restored-standard-boot',
                     boot_disk_type='pd-standard')
    plan = runner.build_run_plan(task=task, model=resolve_model('openai/gpt-5.4-mini', 'max'), results_bucket=None)
    command = plan.commands['create_run_vm']
    assert not any(a.startswith(('--source-machine-image=', '--create-disk=')) for a in command)
    assert '--disk=name=restored-standard-boot,boot=yes,auto-delete=yes,device-name=persistent-disk-0' in command


def test_team_launcher_forwards_owner_and_central_dashboard(tmp_path: Path) -> None:
    import importlib.util
    import json as _json
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "run_team", Path(__file__).resolve().parents[2] / "scripts" / "run_team.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    config = tmp_path / "team.json"
    config.write_text(_json.dumps({
        "machine_type": "n2-custom-6-32768", "boot_disk_gb": 200, "boot_disk_type": "pd-standard",
        "model": "openai/gpt-5.4-mini", "effort": "max", "runtime_image": "img",
        "no10x_runtime": True, "track_live": True, "tracking_grade_every": 0,
    }))
    args = SimpleNamespace(config=config, task="11", project="member", results_bucket="gs://member-results",
                           condition="v2a", description="v2a test", boot_disk_type=None, boot_disk_source=None, dry_run=True,
                           owner="georges", dashboard_uri="gs://team/_dashboard")
    command = module.build_command(args)
    assert command[command.index("--owner") + 1] == "georges"
    assert command[command.index("--dashboard-uri") + 1] == "gs://team/_dashboard"
    args.owner, args.dashboard_uri = None, None
    assert "--owner" not in module.build_command(args)


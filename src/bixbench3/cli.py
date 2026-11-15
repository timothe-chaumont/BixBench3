"""Command-line entry point for the public benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import RUN_MACHINE_TYPE, JsonValue, RuntimeSettings, resolve_model
from .gcp_runner import (
    GCPRunner,
    SubprocessExecutor,
    grade_existing_artifacts,
    load_public_task,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bixbench3",
        description="Run and grade one BixBench3 benchmark task.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser(
        "setup-runtime",
        help="build the private licensed runtime image once",
    )
    setup.add_argument("--project", required=True, help="GCP project ID")
    setup.add_argument("--machine-type", default=RUN_MACHINE_TYPE, help="GCP builder VM type")
    setup.add_argument("--boot-disk-gb", type=int, default=500, help="builder boot disk size in GB")
    setup.add_argument("--boot-disk-type", choices=["pd-balanced", "pd-standard", "pd-ssd"], default="pd-balanced")
    setup.add_argument("--task11-runtime", action="store_true", help="build the task-11-only runtime without unused licensed 10x tools")
    setup.add_argument(
        "--cellranger-tarball",
        required=False,
        type=Path,
        help="licensed Cell Ranger 6.0.2 tarball",
    )
    setup.add_argument(
        "--cellranger-arc-tarball",
        required=False,
        type=Path,
        help="licensed Cell Ranger ARC 2.0.2 tarball",
    )
    setup.add_argument(
        "--dry-run",
        action="store_true",
        help="validate local files and print cloud actions without running gcloud",
    )

    run = commands.add_parser("run", help="run and grade one task on GCP")
    run.add_argument("--task", required=True, help="task number or stable paper ID")
    run.add_argument(
        "--model",
        required=True,
        help="any Inspect provider/model identifier",
    )
    run.add_argument(
        "--effort",
        required=True,
        help="explicit reasoning effort; no default is applied",
    )
    run.add_argument("--project", required=True, help="GCP project ID")
    run.add_argument("--machine-type", default=RUN_MACHINE_TYPE, help="GCP analyst VM type")
    run.add_argument("--boot-disk-gb", type=int, default=500, help="analyst boot disk size in GB")
    run.add_argument("--boot-disk-type", choices=["pd-balanced", "pd-standard", "pd-ssd"], default="pd-balanced")
    run.add_argument("--boot-disk-source", help="existing boot disk restored from the compatible machine image; attached with auto-delete")
    run.add_argument("--runtime-boot-device", default="persistent-disk-0", help="boot disk device name in the source machine image")
    run.add_argument("--runtime-image", help="existing compatible machine image in the selected project")
    run.add_argument("--no10x-runtime", action="store_true", help="runtime without licensed 10x tools; rejected for tasks requiring them")
    run.add_argument("--cost-limit", type=float, help="Inspect analyst cost limit in USD (excludes judges and cloud infrastructure)")
    run.add_argument("--track-live", action="store_true", help="install George's bixdash collector on the run VM")
    run.add_argument("--run-description", default="", help="one-line experiment description for live tracking")
    run.add_argument("--condition", default="baseline", help="dashboard experiment condition")
    run.add_argument("--tracking-grade-every", type=int, default=0, help="partial grading interval in seconds; 0 disables it")
    run.add_argument("--dashboard-uri", default="", help="central bixdash bucket prefix (gs://BUCKET/_dashboard); default: <results bucket>/_dashboard")
    run.add_argument("--owner", default="", help="team member running the experiment (shown on the dashboard)")
    run.add_argument("--task11-runtime", action="store_true", help="use the task-11-only runtime without licensed 10x tools")
    run.add_argument(
        "--model-arg",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="additional Inspect model argument; repeat as needed",
    )
    run.add_argument(
        "--results-bucket",
        help="existing gs:// bucket/prefix for the full run bundle",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="print effort resolution, resources, and commands without running gcloud",
    )

    for name, help_text in (
        ("status", "inspect a detached benchmark run"),
        ("complete", "collect a finished run and delete its VM"),
        ("cancel", "cancel a detached run and delete its VM"),
    ):
        lifecycle = commands.add_parser(name, help=help_text)
        lifecycle.add_argument("--run", required=True, help="run ID printed by the run command")
        lifecycle.add_argument("--project", required=True, help="GCP project ID")

    grade = commands.add_parser(
        "grade",
        help="grade an existing local artifact directory",
    )
    grade.add_argument("--task", required=True, help="task number or stable paper ID")
    grade.add_argument(
        "--artifacts-dir",
        required=True,
        type=Path,
        help="directory containing the task's requested artifact files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "setup-runtime":
            return _setup_runtime(arguments)
        if arguments.command == "run":
            return _run(arguments)
        if arguments.command == "status":
            return _status(arguments)
        if arguments.command == "complete":
            return _complete(arguments)
        if arguments.command == "cancel":
            return _cancel(arguments)
        if arguments.command == "grade":
            return _grade(arguments)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, f"bixbench3: error: {error}\n")
    raise AssertionError(f"unhandled command {arguments.command!r}")


def _setup_runtime(arguments: argparse.Namespace) -> int:
    runner = _runner(arguments.project, machine_type=arguments.machine_type, task11_runtime=arguments.task11_runtime, boot_disk_gb=arguments.boot_disk_gb, boot_disk_type=arguments.boot_disk_type)
    result = runner.setup_runtime(
        cellranger_tarball=arguments.cellranger_tarball,
        cellranger_arc_tarball=arguments.cellranger_arc_tarball,
        dry_run=arguments.dry_run,
    )
    _print_json(result)
    return 0


def _run(arguments: argparse.Namespace) -> int:
    task = load_public_task(arguments.task)
    if arguments.task11_runtime and task.paper_id != "10.1016_j.crtox.2021.01.003_v1":
        raise ValueError("--task11-runtime is restricted to task 11")
    model_args = parse_model_args(arguments.model_arg)
    model = resolve_model(
        arguments.model,
        arguments.effort,
        user_model_args=model_args,
    )
    runner = _runner(arguments.project, machine_type=arguments.machine_type, task11_runtime=arguments.task11_runtime, boot_disk_gb=arguments.boot_disk_gb, cost_limit=arguments.cost_limit, track_live=arguments.track_live, run_description=arguments.run_description, run_condition=arguments.condition, tracking_grade_every=arguments.tracking_grade_every, boot_disk_type=arguments.boot_disk_type, runtime_image=arguments.runtime_image, no10x_runtime=arguments.no10x_runtime, runtime_boot_device=arguments.runtime_boot_device, boot_disk_source=arguments.boot_disk_source, dashboard_uri=arguments.dashboard_uri, owner=arguments.owner)
    if arguments.track_live and not arguments.results_bucket:
        raise ValueError("--track-live requires --results-bucket")
    result = runner.run_task(
        task=task,
        model=model,
        results_bucket=arguments.results_bucket,
        dry_run=arguments.dry_run,
    )
    _print_json(result)
    if not arguments.dry_run:
        _print_run_follow_up(result)
    return 0


def _print_run_follow_up(result: dict[str, Any]) -> None:
    commands = result.get("follow_up_commands")
    if not isinstance(commands, dict):
        return
    status = commands.get("status")
    complete = commands.get("complete")
    cancel = commands.get("cancel")
    if not all(isinstance(command, str) for command in (status, complete, cancel)):
        return
    print("\nNext steps:")
    print("1. Monitor the detached run:")
    print(f"   {status}")
    print("2. When status reports succeeded or failed, collect grades and delete the VM:")
    print(f"   {complete}")
    print("3. To stop early and delete the VM:")
    print(f"   {cancel}")
    print("The VM remains billable until you run complete or cancel.")


def _status(arguments: argparse.Namespace) -> int:
    result = _runner(arguments.project).status_run(arguments.run)
    print(
        f"run {result['run_id']}: {result['status']} "
        f"(phase={result['phase']}, vm={result['vm_state']})",
        file=sys.stderr,
    )
    print(f"next: {result['next_command']}", file=sys.stderr)
    _print_json(result)
    return 0


def _complete(arguments: argparse.Namespace) -> int:
    result = _runner(arguments.project).complete_run(arguments.run)
    _print_json(result)
    local_dir = result.get("local_dir")
    if isinstance(local_dir, str):
        grade_path = Path(local_dir) / "grade.json"
        if grade_path.is_file():
            grade_result = json.loads(grade_path.read_text(encoding="utf-8"))
            if isinstance(grade_result, dict):
                _print_grade_summary(grade_result, Path(local_dir))
        judge_path = Path(local_dir) / "judge.json"
        if judge_path.is_file():
            judge_result = json.loads(judge_path.read_text(encoding="utf-8"))
            if isinstance(judge_result, dict):
                _print_judge_summary(judge_result, Path(local_dir))
    return 0 if result["status"] == "succeeded" else 1


def _cancel(arguments: argparse.Namespace) -> int:
    result = _runner(arguments.project).cancel_run(arguments.run)
    _print_json(result)
    return 0


def _grade(arguments: argparse.Namespace) -> int:
    task = load_public_task(arguments.task)
    artifacts_dir = arguments.artifacts_dir.resolve()
    result = grade_existing_artifacts(
        task=task,
        artifacts_dir=artifacts_dir,
    )
    _print_json(result)
    _print_grade_summary(result, artifacts_dir.parent)
    return 0


def _print_grade_summary(result: dict[str, Any], output_root: Path) -> None:
    artifact_grades_dir = output_root / "artifact_grades"
    print(f"\nOverall paper grade: {float(result['score']):.6f}")
    print(f"Overall grade file: {output_root / 'grade.json'}")
    print("Artifact grades:")
    artifacts = result.get("artifacts", [])
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("artifact_id")
            score = artifact.get("score")
            if isinstance(artifact_id, str) and isinstance(score, int | float):
                print(
                    f"- {artifact_id}: {float(score):.6f} "
                    f"({artifact_grades_dir / f'{artifact_id}.json'})"
                )
    print(f"Artifact grade directory: {artifact_grades_dir}")


def _print_judge_summary(result: dict[str, Any], output_root: Path) -> None:
    status = str(result.get("judge_status", "unknown"))
    raw_score = result.get("judge_score")
    score = f"{float(raw_score):.6f}" if isinstance(raw_score, int | float) else "unavailable"
    print(f"\nProcess judge score: {score}")
    print(f"Process judge status: {status}")
    failure_modes = result.get("failure_modes", [])
    tags = [
        str(entry["tag"])
        for entry in failure_modes
        if isinstance(entry, dict) and isinstance(entry.get("tag"), str)
    ]
    print(f"Failure modes: {', '.join(tags) if tags else 'none'}")
    print(f"Process judge file: {output_root / 'judge.json'}")


def _runner(project: str, *, machine_type: str = RUN_MACHINE_TYPE, task11_runtime: bool = False, boot_disk_gb: int = 500, cost_limit: float | None = None, track_live: bool = False, run_description: str = "", run_condition: str = "baseline", tracking_grade_every: int = 0, boot_disk_type: str = "pd-balanced", runtime_image: str | None = None, no10x_runtime: bool = False, runtime_boot_device: str = "persistent-disk-0", boot_disk_source: str | None = None, dashboard_uri: str = "", owner: str = "") -> GCPRunner:
    if boot_disk_type not in {"pd-balanced", "pd-standard", "pd-ssd"}:
        raise ValueError("unsupported boot disk type")
    if no10x_runtime and not runtime_image:
        raise ValueError("--no10x-runtime requires --runtime-image")
    if boot_disk_gb < 20:
        raise ValueError("boot disk must be at least 20 GB")
    if cost_limit is not None and cost_limit <= 0:
        raise ValueError("cost limit must be positive")
    if track_live and not run_description.strip():
        raise ValueError("--track-live requires --run-description")
    if any(c in run_description + run_condition for c in "\r\n"):
        raise ValueError("experiment description and condition must be single-line")
    if tracking_grade_every < 0:
        raise ValueError("tracking grading interval must be nonnegative")
    if dashboard_uri and not dashboard_uri.startswith("gs://"):
        raise ValueError("--dashboard-uri must be a gs:// prefix")
    if any(c in dashboard_uri + owner for c in "\r\n "):
        raise ValueError("dashboard URI and owner must be single tokens")
    repo_root = Path(__file__).resolve().parents[2]
    settings = RuntimeSettings(
        machine_type=machine_type, include_10x=not (task11_runtime or no10x_runtime), boot_disk_gb=boot_disk_gb,
        boot_disk_type=boot_disk_type, runtime_boot_device=runtime_boot_device, boot_disk_source=boot_disk_source,
        analyst_cost_limit=cost_limit, track_live=track_live,
        run_description=run_description, run_condition=run_condition,
        tracking_grade_every=tracking_grade_every,
        dashboard_uri=dashboard_uri.rstrip("/"), run_owner=owner,
    )
    if task11_runtime:
        settings = replace(settings, runtime_image_name="bixbench3-runtime-v1-0-0-r7-task11-no10x")
    if runtime_image:
        settings = replace(settings, runtime_image_name=runtime_image)
    return GCPRunner(
        project=project,
        executor=SubprocessExecutor(),
        settings=settings,
        runs_root=repo_root / "runs",
        repo_root=repo_root,
    )


def parse_model_args(values: Sequence[str]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for value in values:
        key, separator, raw = value.partition("=")
        if not separator or not key or not raw:
            raise ValueError(f"model argument must use KEY=JSON syntax: {value!r}")
        if key in result:
            raise ValueError(f"duplicate model argument {key!r}")
        try:
            decoded: Any = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"model argument {key!r} has invalid JSON value: {error.msg}"
            ) from error
        result[key] = _json_value(decoded, key)
    return result


def _json_value(value: Any, source: str) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item, source) for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"model argument {source!r} contains a non-string key")
            result[key] = _json_value(item, source)
        return result
    raise ValueError(f"model argument {source!r} contains unsupported {type(value).__name__}")


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

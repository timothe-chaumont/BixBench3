"""Shared 6-vCPU experiment launcher. Provider credentials stay in the environment."""
import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path


def build_command(args):
    config = json.loads(args.config.read_text())
    command = ['uv', 'run', '--locked', 'bixbench3', 'run', '--task', args.task,
               '--project', args.project, '--results-bucket', args.results_bucket,
               '--condition', args.condition, '--run-description', args.description]
    for key in ['machine_type', 'boot_disk_gb', 'boot_disk_type', 'model', 'effort', 'runtime_image', 'tracking_grade_every']:
        value = args.boot_disk_type if key == 'boot_disk_type' and args.boot_disk_type else config[key]
        command.extend(['--' + key.replace('_', '-'), str(value)])
    for key in ['no10x_runtime', 'track_live']:
        if config.get(key):
            command.append('--' + key.replace('_', '-'))
    if args.boot_disk_source:
        command.extend(["--boot-disk-source", args.boot_disk_source])
    if args.owner:
        command.extend(['--owner', args.owner])
    dashboard_uri = args.dashboard_uri or config.get('dashboard_uri')
    if dashboard_uri:
        command.extend(['--dashboard-uri', dashboard_uri])
    if args.dry_run:
        command.append('--dry-run')
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/team-6vcpu.json')
    for name in ['task', 'project', 'results-bucket', 'condition', 'description']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--boot-disk-type', choices=['pd-standard', 'pd-balanced', 'pd-ssd'])
    parser.add_argument("--boot-disk-source", help="reuse an already restored compatible boot disk")
    parser.add_argument('--owner', help='team member running the experiment (dashboard filter)')
    parser.add_argument('--dashboard-uri', help='central dashboard prefix, e.g. gs://bixbench3-task11-jex20-results/_dashboard '
                        '(needed when launching from your own GCP project)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    disk_type = args.boot_disk_type or config['boot_disk_type']
    if disk_type != 'pd-balanced' and not args.boot_disk_source and not args.dry_run:
        # Restoring the disk separately avoids inherited SSD allocation from the machine image.
        disk_name = 'bixboot-' + uuid.uuid4().hex[:20]
        image = f"projects/{args.project}/global/machineImages/{config['runtime_image']}"
        subprocess.run(['gcloud', '--quiet', 'beta', 'compute', 'disks', 'create', disk_name,
                        '--project', args.project, '--zone', 'us-central1-a',
                        '--type', disk_type, '--size', str(config['boot_disk_gb']) + 'GB',
                        '--source-machine-image', image,
                        '--source-machine-image-disk-device-name', 'persistent-disk-0'], check=True)
        args.boot_disk_source = disk_name
        print(f'Restored boot disk: {disk_name} (auto-deleted with its VM once attached)', flush=True)
    command = build_command(args)
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()

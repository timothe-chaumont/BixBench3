"""Launch the explicitly separate, four-artifact downstream development task."""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, UTC

import bixbench3.gcp_runner as gcp
from bixbench3.config import RuntimeSettings, resolve_model

HERE = Path(__file__).resolve().parent
COUNT_ID = 'tempo_seq_filtered_counts'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_dataset(work: Path, original: gcp.TaskSpec):
    dataset = work/'dataset'
    if not dataset.exists():
        gcp.stage_hf_case(original, dataset)
    case = json.loads((dataset/'case.json').read_text())
    case['expected_outputs'] = [a for a in case['expected_outputs'] if a['artifact_id'] != COUNT_ID]
    original_prompt = work/'original-prompt.md'
    text = original_prompt.read_text()
    # Preserve original method guidance and all four downstream output contracts.
    intro, outputs = text.split('## Required Outputs', 1)
    pieces = outputs.split('\n### ')
    pieces = [piece for piece in pieces if not piece.lstrip().startswith('`tempo_seq_filtered_counts`')]
    outputs = '\n### '.join(pieces)
    scope = '''# Task 11 lite — downstream v1\n\nThis is a separate downstream development task. All 85 libraries, probes, doses,
replicates and timepoints are retained. Start from the supplied unnormalized
integer probe counts at `data/provided/counts.csv`. The raw-read counting step is
already performed; do not align FASTQs or reproduce the counting artifact.
Use the staged metadata and probe manifest to interpret the matrix.
Only the four downstream artifacts below and METHODS.md are required.
The score is conditional on supplied correct counts and is not the full-task score.
The environment is prepared before your clock starts: R 4.0.2, DESeq2 1.28.0,
biomaRt 2.44.0, PIANO 2.4.0, data.table, readxl and openxlsx.
Use Rscript on PATH; do not reinstall these packages. The files under
`data/reference` are frozen public reference resources, with provenance.json.
Use the staged Ensembl 100 homology mapping instead of a live BioMart query,
and the staged MSigDB 6.2 GMT collections. State this resource-caching adaptation
in METHODS.md. Do not download alternative result tables or use expected answers.
Use all original downstream statistics, contrasts and output filters below.
You have {time_limit} seconds. Write artifacts incrementally and use at most
6 threads; batch calculations rather than polling. Failed or substituted methods
must be disclosed.\n\n'''
    # Original counting instructions are superseded explicitly; downstream paragraphs unchanged.
    intro = intro.replace('DESeq2 1.28.1', 'DESeq2 1.28.0').replace('biomaRt 2.44.1', 'biomaRt 2.44.0')
    intro = intro.replace('Start from the 85 staged single-end TempO-Seq FASTQs', 'The original full task starts from the 85 staged single-end TempO-Seq FASTQs')
    intro = intro.replace('Use `biomaRt::useEnsembl(biomart = \"genes\", dataset = \"mmusculus_gene_ensembl\", version = 100)` and live BioMart queries through `https://apr2020.archive.ensembl.org/biomart/martservice` for mouse-to-human ortholog mapping.', 'For this lite variant use the frozen Ensembl 100 Compara ortholog table at `data/reference/ensembl100-mouse-human.tsv`; record this public-reference caching adaptation.')
    prompt = scope + intro + '\n## Required Outputs' + outputs
    target = dataset/case['prompt']['prompt_path']
    target.write_text(prompt)
    (dataset/'case.json').write_text(json.dumps(case,indent=2)+'\n')
    files={str(p.relative_to(dataset)):sha(p) for p in dataset.rglob('*') if p.is_file()}
    return gcp.StagedCase(dataset,dataset/'case.json',files)


class LiteRunner(gcp.GCPRunner):
    def build_run_plan(self, **kwargs):
        plan=super().build_run_plan(**kwargs)
        argv=tuple('/opt/bixbench3/tools/task11_lite/inspect_task.py@task11_lite' if x.endswith('/inspect_harness/tasks.py@bixbench3_cases') else x for x in plan.inspect_argv)
        if getattr(self, 'reuse_vm', None):
            old_vm=plan.layout.vm_name
            commands={name:tuple(arg.replace(old_vm,self.reuse_vm) for arg in command) for name,command in plan.commands.items()}
            plan=dataclasses.replace(plan,layout=dataclasses.replace(plan.layout,vm_name=self.reuse_vm),commands=commands)
        return dataclasses.replace(plan,inspect_argv=argv)

    def _initial_manifest(self,*args,**kwargs):
        value=super()._initial_manifest(*args,**kwargs)
        value['lite_profile']={'version':'task11-lite-downstream-v1','parent_task':'11',
            'provided_artifact':COUNT_ID,'scored_artifacts':4,'raw_read_alignment':False,
            'input_manifest':json.loads((self.work/'upload/input-provenance.json').read_text()),
            'reference_provenance':{'preparation_pending':True},
            'source_files_sha256':{p.name:sha(p) for p in HERE.glob('*') if p.is_file() and p.suffix in ('.py','.sh')},
            'representativeness_validated':False,'setup_started_at':datetime.now(UTC).isoformat()}
        return value

    def _install_live_tracking(self,plan):
        base=('gcloud','--project',self.project)
        for local,remote in [(HERE,'task11-lite-code'),(self.work/'upload','task11-lite-staging')]:
            self.executor.run((*base,'compute','scp','--recurse',str(local),f'{plan.layout.vm_name}:~/{remote}',f'--zone={plan.zone}'))
        script='''set -euo pipefail
if sudo find /var/lib/bixbench3/inspect_logs -name '*.eval' -print -quit | grep -q .; then echo 'Refusing to repeat an existing agent run'; exit 1; fi
sudo mkdir -p /opt/bixbench3/tools
sudo cp -a ~/task11-lite-code /opt/bixbench3/tools/task11_lite
sudo cp -a ~/task11-lite-staging /var/lib/bixbench3/lite-staging
cd /opt/bixbench3/tools/task11_lite
if ! sudo docker image inspect bixbench3-sandbox:task11-lite-v1 >/dev/null 2>&1; then sudo docker build -t bixbench3-sandbox:task11-lite-v1 .; fi
'''
        self.executor.run(gcp.ssh_argv(base,plan.layout.vm_name,plan.zone,('bash','-s')),input_text=script)
        import time
        for _ in range(180):
            if (self.work/'reference-data/provenance.json').exists(): break
            time.sleep(5)
        else: raise RuntimeError('Reference preparation did not finish; agent was not started')
        shutil.copytree(self.work/'reference-data',self.work/'upload/reference-data',dirs_exist_ok=True)
        self.executor.run((*base,'compute','scp','--recurse',str(self.work/'upload/reference-data'),f'{plan.layout.vm_name}:~/task11-lite-staging/',f'--zone={plan.zone}'))
        script='sudo cp -a ~/task11-lite-staging/reference-data/. /var/lib/bixbench3/lite-staging/reference-data/; sudo bash /opt/bixbench3/tools/task11_lite/prepare_vm.sh'
        self.executor.run(gcp.ssh_argv(base,plan.layout.vm_name,plan.zone,('bash','-c',script)))
        manifest=json.loads(plan.layout.manifest_path.read_text())
        manifest['lite_profile']['reference_provenance']=json.loads((self.work/'reference-data/provenance.json').read_text())
        manifest['lite_profile']['environment_ready_at']=datetime.now(UTC).isoformat()
        gcp.write_json(plan.layout.manifest_path,manifest)
        self.executor.run(plan.commands['copy_run_manifest'])
        super()._install_live_tracking(plan)
        # The official collector is unchanged; only its cadence is shortened for lite.
        script='''sudo python3 - <<'META'
from pathlib import Path
import json
p=Path('/var/lib/bixdash/run_meta.json'); m=json.loads(p.read_text()); m.update(task_id='11-lite-v1',time_limit_s=600,evaluation_scope='downstream-only-4-artifacts',owner='timothe'); p.write_text(json.dumps(m,indent=2)+'\\n')
p=Path('/opt/bixdash/collect.py'); p.write_text(p.read_text().replace('TIME_LIMIT_S = 86_400','TIME_LIMIT_S = 600'))
META
sudo mkdir -p /etc/systemd/system/bixdash-collect.timer.d
printf '[Timer]\\nOnUnitActiveSec=\\nOnUnitActiveSec=60s\\n' | sudo tee /etc/systemd/system/bixdash-collect.timer.d/lite.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl restart bixdash-collect.timer
'''
        self.executor.run(gcp.ssh_argv(base,plan.layout.vm_name,plan.zone,('bash','-s')),input_text=script)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project',required=True);ap.add_argument('--results-bucket',required=True)
    ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--boot-disk-source',required=True)
    ap.add_argument('--reuse-prepared-vm', help='reuse an inactive prepared 6-vCPU VM; archives all previous run state')
    ap.add_argument('--resume-preparation', help='resume only a failed setup, before any Inspect sample exists')
    args=ap.parse_args();work=args.work_dir.resolve()
    original=gcp.load_public_task('11');staged=make_dataset(work,original)
    task=dataclasses.replace(original,task_id='11-lite-v1')
    settings=RuntimeSettings(machine_type='n2-custom-6-32768',boot_disk_gb=200,
        boot_disk_type='pd-standard',boot_disk_source=args.boot_disk_source,
        include_10x=False,runtime_image_name='bixbench3-runtime-v1-0-0-r7-task11-no10x',
        time_limit_seconds=600,message_limit=150,track_live=True,
        run_description='Task 11 lite downstream v1 — 6 vCPU; supplied counts; 4 artifacts; 10-min cap',
        run_condition='baseline-lite-downstream-v1',tracking_grade_every=0)
    executor=gcp.SubprocessExecutor()
    if args.resume_preparation:
        import subprocess
        old_path=gcp.resolve_run_manifest(args.repo_root.resolve()/'runs',args.resume_preparation)
        old=json.loads(old_path.read_text())
        if old.get('phase') != 'submission_failed' or old.get('task_id') != '11-lite-v1':
            raise ValueError('Only a failed pre-agent lite preparation may be resumed')
        fixed_now=datetime.strptime(old_path.parent.name,'%Y%m%dT%H%M%S%fZ').replace(tzinfo=UTC)
        original_layout=gcp.build_run_layout
        gcp.build_run_layout=lambda **kwargs: original_layout(**kwargs,now=fixed_now)
        vm=old['gcp']['vm_name']
        class ResumeExecutor(gcp.SubprocessExecutor):
            def run(self,argv,**kwargs):
                command=list(argv)
                if 'instances' in command and 'create' in command and vm in command:
                    return super().run(('gcloud','--project',args.project,'compute','instances','start',vm,'--zone=us-central1-a','--quiet'),**kwargs)
                if 'attach-disk' in command and vm in command:
                    value=super().run(('gcloud','--project',args.project,'compute','instances','describe',vm,'--zone=us-central1-a','--format=json'),capture_output=True)
                    disks=json.loads(value.stdout).get('disks',[])
                    if any(d.get('deviceName')=='bixbench3-data' for d in disks):
                        return subprocess.CompletedProcess(command,0,'','')
                return super().run(command,**kwargs)
        executor=ResumeExecutor()
        (work/'previous-preparation-manifest.json').write_text(json.dumps(old,indent=2)+'\n')
    if args.reuse_prepared_vm:
        import subprocess
        vm=args.reuse_prepared_vm
        if not vm.startswith('arb-run-'):raise ValueError('Only a benchmark VM may be reused')
        executor.run(gcp.ssh_argv(('gcloud','--project',args.project),vm,settings.zone,('bash','-s')), input_text="""set -euo pipefail
if sudo systemctl is-active --quiet bixbench3-run.service; then echo 'Refusing to overwrite an active run'; exit 1; fi
sudo systemctl stop bixdash-collect.timer bixdash-collect.service || true
sudo systemctl reset-failed bixbench3-run.service || true
sudo python3 - <<'ARCHIVE'
from pathlib import Path
from datetime import datetime,UTC
import shutil
root=Path('/var/lib/bixbench3')
archive=root/'setup-attempts'/datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
archive.mkdir(parents=True,mode=0o700)
for name in ['inspect_logs','artifact_grades','outputs','agent_artifacts','grade.json','judge.json','status.json','run_manifest.json','run.sh','workspace','broker','broker_logs','broker_cache','dataset']:
 p=root/name
 if p.exists(): shutil.move(str(p),str(archive/name))
p=Path('/var/lib/bixdash')
if p.exists():shutil.move(str(p),str(archive/'dashboard-state'))
ARCHIVE
""")
        class WarmExecutor(gcp.SubprocessExecutor):
            def run(self,argv,**kwargs):
                command=list(argv)
                if ('instances' in command and 'create' in command and vm in command) or ('attach-disk' in command and vm in command):
                    return subprocess.CompletedProcess(command,0,'','')
                return super().run(command,**kwargs)
        executor=WarmExecutor()
    runner=LiteRunner(project=args.project,executor=executor,settings=settings,
        repo_root=args.repo_root.resolve(),runs_root=args.repo_root.resolve()/'runs')
    runner.work=work
    runner.reuse_vm=args.reuse_prepared_vm
    original_script=gcp.remote_run_script
    def lite_script(plan,settings):
        script=original_script(plan,settings)
        script=script.replace('export BIXBENCH3_DATA_DIR=/mnt/bixbench3-data/data','export BIXBENCH3_DATA_DIR=/var/lib/bixbench3/lite_data')
        script=script.replace('export BIXBENCH3_SANDBOX_IMAGE=bixbench3-sandbox:1.0.0','export BIXBENCH3_SANDBOX_IMAGE=bixbench3-sandbox:task11-lite-v1')
        script=script.replace('from bixbench3.gcp_runner import TaskSpec, grade_existing_artifacts',
            'from bixbench3.gcp_runner import TaskSpec\nsys.path.insert(0, "/opt/bixbench3/tools/task11_lite")\nfrom grade_lite import grade_existing_artifacts')
        assert 'BIXBENCH3_DATA_DIR=/var/lib/bixbench3/lite_data' in script
        assert 'from grade_lite import' in script
        return script
    gcp.remote_run_script=lite_script
    model=resolve_model('openai/gpt-5.4-mini','max')
    result=runner._run_staged_task(task=task,model=model,environment=gcp.selected_environment(gcp.required_environment_keys(model)),staged_case=staged,results_bucket=args.results_bucket)
    (work/'launched.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()

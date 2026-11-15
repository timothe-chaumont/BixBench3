"""Stage the private, explicitly reduced task inputs; no downstream answers."""
import argparse
from pathlib import Path
import subprocess
from bixbench3.gcp_runner import hf_download, load_public_task


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--input-prefix',default='gs://bixbench3-task11-jex20-results/lite-inputs/task11-downstream-v1')
    args=ap.parse_args()
    work=args.work_dir.resolve();upload=work/'upload';upload.mkdir(parents=True,exist_ok=True)
    subprocess.run(['gcloud','storage','cp','--recursive',args.input_prefix.rstrip('/')+'/*',str(upload)],check=True)
    task=load_public_task('11')
    prompt=hf_download(f'cases/{task.paper_id}/agent/prompt.md')
    (work/'original-prompt.md').write_bytes(prompt.read_bytes())
    # run_lite stages the authenticated case. Reference files are copied separately
    # so the operator can inspect hashes before the scientific run starts.
    import shutil
    shutil.copytree(upload/'reference-data',work/'reference-data',dirs_exist_ok=True)
    if not (work/'reference-data/provenance.json').exists():
        raise RuntimeError('Reference provenance is missing')
    print('Lite input package ready. Keep the full task 11 verified data disk for metadata.')

if __name__=='__main__':main()

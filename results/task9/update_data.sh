#!/bin/bash
# Pull the latest completed task 9 runs from Sherlock into data/runs.jsonl (needs an open `ssh sherlock`).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
scp -q "$HERE/collect_on_sherlock.py" sherlock:bixbench3-sherlock/logs/collect_t9.py
ssh sherlock 'cd ~/bixbench3-sherlock/logs && srun -p normal -c 2 --mem=8G -t 0:30:00 -J bb3-collect-t9 \
  apptainer exec --cleanenv --bind /scratch /scratch/users/sbennani/bixbench3/images/bixbench3-runner-py312.sif \
  $HOME/bixbench3-sherlock/venv/bin/python collect_t9.py /scratch/users/sbennani/bixbench3/runs $HOME/bixbench3-sherlock/logs/t9_runs.jsonl' 2>&1 | grep -v -E '^Automated|^srun: job|queued|allocated'
scp -q sherlock:bixbench3-sherlock/logs/t9_runs.jsonl "$HERE/data/runs.jsonl"
echo "data/runs.jsonl: $(wc -l < "$HERE/data/runs.jsonl") runs"

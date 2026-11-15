#!/bin/bash
# Night batch 2026-11-15, task 9: 3 conditions x 5 repeats on Sherlock (6 CPU / 32 GB, AMD EPYC 7502).
#   t9-baseline       : official task 9 prompt, stock sandbox                  (branch exp/t9-baseline)
#   t9-env            : + preinstalled task 9 environment (sandbox SIF)       (branch exp/t9-env)
#   t9-env-subagents  : + run_subagent tool and orchestration note (overlay)  (branch exp/t9-env-subagents)
# Run from the main checkout:  bash sherlock/night_t9.sh
set -euo pipefail
cd "$(dirname "$0")/.."
WT=$(cd .. && pwd)/wt
SIF=/scratch/users/sbennani/bixbench3/images/bixbench3-sandbox_1.0.0-task9env.sif
ssh -o BatchMode=yes sherlock "test -s $SIF && test -f /scratch/users/sbennani/bixbench3/data/10_1186_s12915_024_01879_0_v1/.bixbench3-ready.json" \
  || { echo "task 9 data or task 9 env SIF missing on Sherlock"; exit 1; }
export BB3_CPUS=6 BB3_MEM_GB=32 BB3_REPEATS=${BB3_REPEATS:-5} BB3_OWNER=sofia
sherlock/submit.sh t9-baseline "$WT/t9-baseline" 9 t9-baseline "Task 9 baseline (stock sandbox)" normal
BB3_SANDBOX_SIF=$SIF sherlock/submit.sh t9-env "$WT/t9-env" 9 t9-env "Task 9 + preinstalled env" normal
BB3_SANDBOX_SIF=$SIF sherlock/submit.sh t9-env-subagents "$WT/t9-env-subagents" 9 t9-env-subagents \
  "Task 9 + preinstalled env + sub-agents" normal --harness-overlay

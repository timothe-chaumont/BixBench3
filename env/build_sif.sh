#!/bin/bash
# Build the task environment SIF on Sherlock (compute node with network; Apptainer --fakeroot).
#   bash env/build_sif.sh task9  [BASE_SIF] [OUT_SIF]
# Defaults: BASE_SIF=$SCRATCH/bixbench3/images/bixbench3-sandbox_1.0.0.sif
#           OUT_SIF=$SCRATCH/bixbench3/images/bixbench3-sandbox_1.0.0-<task>env.sif
# Then run a task with it:  BB3_SANDBOX_SIF=<OUT_SIF> sherlock/submit.sh ...
set -euo pipefail
TASK=${1:?usage: build_sif.sh <task9|task11> [BASE_SIF] [OUT_SIF]}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGES=${SCRATCH:-/tmp}/bixbench3/images
BASE_SIF=${2:-$IMAGES/bixbench3-sandbox_1.0.0.sif}
OUT_SIF=${3:-$IMAGES/bixbench3-sandbox_1.0.0-${TASK}env.sif}
test -d "$ROOT/env/$TASK" || { echo "no env/$TASK"; exit 2; }
test -f "$BASE_SIF" || { echo "base SIF not found: $BASE_SIF"; exit 2; }
test -f "$ROOT/env/$TASK/path.env" || { echo "missing env/$TASK/path.env"; exit 2; }
DEF=$(mktemp --suffix=.def)
sed -e "s#@BASE_SIF@#$BASE_SIF#" -e "s#@TASK@#$TASK#g" -e "s#@EXACT_PINS@#${EXACT_PINS:-1}#" \
    "$ROOT/env/sif.def.template" > "$DEF"
if [ "${PRINT_DEF:-0}" = 1 ]; then cat "$DEF"; rm -f "$DEF"; exit 0; fi
export APPTAINER_TMPDIR=${L_SCRATCH_JOB:-${TMPDIR:-/tmp}}
(cd "$ROOT" && apptainer build --fakeroot "$OUT_SIF.tmp" "$DEF")
rm -f "$DEF"
# offline check BEFORE publishing: proxies point at a closed port so any network access fails
VERIFY="bash /opt/task-env/verify_env.sh"
[ "$TASK" = task11 ] && VERIFY="micromamba run -n task11 Rscript /opt/task-env/verify_env.R"
# --workdir: node-local /tmp like the run sandbox (the default --containall session tmpfs is too small for R/SQLite)
mkdir -p "$APPTAINER_TMPDIR/verify-work"
if ! apptainer exec --containall --workdir "$APPTAINER_TMPDIR/verify-work" --env "HTTP_PROXY=http://127.0.0.1:9,HTTPS_PROXY=http://127.0.0.1:9,http_proxy=http://127.0.0.1:9,https_proxy=http://127.0.0.1:9" \
     "$OUT_SIF.tmp" bash -c "$VERIFY"; then
  mv "$OUT_SIF.tmp" "$OUT_SIF.failed"
  echo "verification failed; image kept for debugging as $OUT_SIF.failed" >&2
  exit 1
fi
mv "$OUT_SIF.tmp" "$OUT_SIF"
apptainer exec "$OUT_SIF" cat /opt/task-env/MANIFEST.json
sha256sum "$OUT_SIF" | tee "$OUT_SIF.sha256"

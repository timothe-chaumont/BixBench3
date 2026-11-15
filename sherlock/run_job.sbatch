#!/bin/bash
# Run one prepared BixBench3 bundle (sherlock/prepare_run.py) on a Sherlock compute node.
#
#   sbatch -p <partition> -o <bundle>/slurm-%j.out sherlock/run_job.sbatch <bundle-dir>
#
# Smoke test: BB3_SMOKE_MESSAGES=30 caps the agent at 30 messages (whole pipeline in minutes).
# Same resources as the team's GCP profile (6 vCPU / 32 GB, n2-custom-6-32768).
# The run executes the official run.sh produced by gcp_runner.remote_run_script with host
# paths rewritten, Inspect's Docker sandbox replaced by the "apptainer" provider
# (same images, same mounts, gateway-only network enforced by bb3jail), and the
# bixdash collector publishing to the team dashboard every 5 minutes.
#SBATCH --job-name=bb3-run
#SBATCH --cpus-per-task=6
#SBATCH --mem=32G
#SBATCH --time=1-02:00:00
set -uo pipefail

BUNDLE=$(cd "$1" && pwd)
ml purge
ml python/3.12.1 uv/0.10.8
ml system google-cloud-sdk/448.0.0

BB3=$HOME/bixbench3-sherlock
REPO=$BB3/BixBench3
VENV=$BB3/venv
IMAGES=$SCRATCH/bixbench3/images
RUNNER=$IMAGES/bixbench3-runner-py312.sif
JOB=$L_SCRATCH_JOB/bb3
RUN_ROOT=$JOB/run
SRC=$JOB/src
SECRETS=/dev/shm/bb3-$SLURM_JOB_ID
mkdir -p "$JOB" "$SRC" "$JOB/jaildir" "$JOB/jaillog" "$JOB/squidlog" "$JOB/xdg" "$JOB/bixdash" "$JOB/tmp"
(umask 077 && mkdir -p "$SECRETS")
COLLECTOR=""
HOSTEXEC=""
RELAY=""
cleanup() {
  [ -n "$COLLECTOR" ] && kill "$COLLECTOR" 2>/dev/null
  [ -n "$HOSTEXEC" ] && kill "$HOSTEXEC" 2>/dev/null
  [ -n "$RELAY" ] && kill "$RELAY" 2>/dev/null
  rm -rf "$SECRETS"
}
trap cleanup EXIT

field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$BUNDLE/job.json" "$1"; }
PAPER=$(field paper_id)
RUN_ID=$(field run_id)
OVERLAY=$(field harness_overlay)
DATA_DIR=$SCRATCH/bixbench3/data/$PAPER/data
echo "[sherlock] job $SLURM_JOB_ID on $(hostname) partition ${SLURM_JOB_PARTITION:-?} cpus ${SLURM_CPUS_PER_TASK:-?} run $RUN_ID"
test -f "$DATA_DIR/../.bixbench3-ready.json" || { echo "task data not staged: $DATA_DIR (run setup.sbatch)"; exit 2; }

# --- secrets: OpenAI access goes through a per-job key relay (sherlock/key_relay.py) that switches from
# OPENAI_API_KEY to OPENAI_API_KEY_2, _3 ... in ~/.bixbench3_secrets when a key runs out, without
# interrupting the run. The run only sees a random per-job token and OPENAI_BASE_URL; real keys stay
# in the relay. Same file format as the GCP /dev/shm/bixbench3.env.
grep -Eq '^(export )?OPENAI_API_KEY=.' "$HOME/.bixbench3_secrets" || { echo "OPENAI_API_KEY missing from ~/.bixbench3_secrets"; exit 2; }
RELAY_PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
RELAY_TOKEN=$(python3 -c 'import secrets;print("bb3relay-" + secrets.token_hex(24))')
BB3_RELAY_TOKEN=$RELAY_TOKEN BB3_ROTATION_LOG=$BB3/logs/key_rotation.log \
  python3 "$REPO/sherlock/key_relay.py" "$RELAY_PORT" > "$JOB/key_relay.log" 2>&1 &
RELAY=$!
for _ in $(seq 20); do python3 -c 'import socket,sys;socket.create_connection(("127.0.0.1",int(sys.argv[1])),1)' "$RELAY_PORT" 2>/dev/null && break; sleep 0.5; done
kill -0 "$RELAY" 2>/dev/null || { echo "key relay did not start"; cat "$JOB/key_relay.log"; exit 2; }
(umask 077 && printf 'OPENAI_API_KEY=%s\nOPENAI_BASE_URL=http://127.0.0.1:%s/v1\n' "$RELAY_TOKEN" "$RELAY_PORT" > "$SECRETS/bixbench3.env")
# past.dev run-memory conditions: the host-side harness reads PAST_API_KEY (never passed to the sandbox,
# whose commands run under env -i / --cleanenv); redacted from uploaded results by gcp_runner.
(umask 077 && sed -n 's/^export //; /^PAST_API_KEY=./p' "$HOME/.bixbench3_secrets" >> "$SECRETS/bixbench3.env")
echo "[sherlock] $(tail -1 "$JOB/key_relay.log" | cut -d' ' -f4-)"

# --- source tree = runtime checkout (HEAD) + optional committed harness overlay (as on GCP)
(cd "$REPO" && git archive --format=tar HEAD) | tar -x -C "$SRC" || { echo "source tree export failed"; exit 2; }
test -d "$SRC/src/bixbench3/inspect_harness" || { echo "source tree incomplete"; exit 2; }
if [ "$OVERLAY" = "True" ]; then
  archive=$BUNDLE/bixbench3-harness-overlay.tar.gz
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['harness_overlay']['archive_sha256'])" "$BUNDLE/run_manifest.json")
  printf '%s  %s\n' "$want" "$archive" | sha256sum --check - || exit 2
  staging=$(mktemp -d "$JOB/overlay.XXXX")
  tar -xzf "$archive" -C "$staging"
  test -d "$staging/src/bixbench3/inspect_harness" || exit 2
  mkdir -p "$JOB/harness-baseline/src/bixbench3"
  mv "$SRC/src/bixbench3/inspect_harness" "$JOB/harness-baseline/src/bixbench3/inspect_harness"
  cp -a "$staging/src/bixbench3/inspect_harness" "$SRC/src/bixbench3/inspect_harness"
  (cd "$SRC" && diff -rq -x __pycache__ "$JOB/harness-baseline/src/bixbench3/inspect_harness" src/bixbench3/inspect_harness || true) > "$JOB/harness_overlay_changes.txt"
fi

# --- images and jail on node-local disk
# Sandbox image. Default: the stock sandbox SIF (unchanged behaviour).
#   BB3_TASK_ENV=task9|task11 : use the preinstalled task environment (env/<task>). The image is named
#     after the committed env files (git tree hash), so it is reused as long as env/ does not change;
#     if it does not exist yet it is built here first (env/build_sif.sh, offline verification included),
#     under a lock so concurrent repeats build it only once. The agent's clock starts after this.
#   BB3_SANDBOX_SIF=<path> : use this SIF as is (overrides BB3_TASK_ENV).
SANDBOX_SIF=$IMAGES/bixbench3-sandbox_1.0.0.sif
ENV_HASH=""
if [ -n "${BB3_SANDBOX_SIF:-}" ]; then
  SANDBOX_SIF=$BB3_SANDBOX_SIF
elif [ -n "${BB3_TASK_ENV:-}" ]; then
  (cd "$REPO" && git cat-file -e "HEAD:env/$BB3_TASK_ENV") 2>/dev/null || { echo "BB3_TASK_ENV=$BB3_TASK_ENV: no committed env/$BB3_TASK_ENV in $REPO"; exit 2; }
  ENV_HASH=$(for p in "env/$BB3_TASK_ENV" env/build_sif.sh env/sif.def.template env/link_path.sh; do (cd "$REPO" && git rev-parse "HEAD:$p"); done | sha256sum | cut -c1-12)
  SANDBOX_SIF=$IMAGES/bixbench3-sandbox_1.0.0-${BB3_TASK_ENV}env-$ENV_HASH.sif
  if [ ! -f "$SANDBOX_SIF" ]; then
    echo "[sherlock] $(basename "$SANDBOX_SIF") not found: building it (first use of this env version)"
    (
      flock 9
      if [ ! -f "$SANDBOX_SIF" ]; then
        envsrc=$(mktemp -d "$JOB/envsrc.XXXX")
        (cd "$REPO" && git archive HEAD env) | tar -x -C "$envsrc"   # build from committed files only
        bash "$envsrc/env/build_sif.sh" "$BB3_TASK_ENV" "$IMAGES/bixbench3-sandbox_1.0.0.sif" "$SANDBOX_SIF"
      fi
    ) 9>"$SANDBOX_SIF.lock" > "$JOB/task_env_build.log" 2>&1 \
      || { echo "[sherlock] task env build failed:"; tail -40 "$JOB/task_env_build.log"; exit 2; }
    echo "[sherlock] task env image ready: $SANDBOX_SIF"
  else
    echo "[sherlock] reusing task env image $SANDBOX_SIF"
  fi
fi
test -f "$SANDBOX_SIF" || { echo "sandbox SIF not found: $SANDBOX_SIF"; exit 2; }
# copied under the stock job-local name so the rest of the job is unchanged; identity recorded
cp "$SANDBOX_SIF" "$JOB/bixbench3-sandbox_1.0.0.sif"
cp "$IMAGES/bixbench3-network-gateway_1.0.0.sif" "$JOB/"
printf '{"sandbox_sif": "%s", "env_hash": "%s", "sha256": "%s", "task_env": "%s"}\n' "$SANDBOX_SIF" "$ENV_HASH" \
  "$(sha256sum "$SANDBOX_SIF" | cut -d' ' -f1)" \
  "$(apptainer inspect --labels "$SANDBOX_SIF" 2>/dev/null | sed -n 's/.*bixbench3.task_env: *//p' | head -1)" > "$JOB/sandbox_image.json"
echo "[sherlock] sandbox image: $(cat "$JOB/sandbox_image.json")"
cp "$BB3/jail/bb3jail" "$JOB/jaildir/bb3jail"

# --- run root, laid out like /var/lib/bixbench3 on the VM
mkdir -p "$RUN_ROOT"/{outputs,workspace,agent_artifacts,broker,broker_logs,broker_cache,inspect_logs}
cp -a "$BUNDLE/dataset" "$RUN_ROOT/dataset"
cp "$BUNDLE/run_manifest.json" "$RUN_ROOT/run_manifest.json"
[ -f "$JOB/harness_overlay_changes.txt" ] && cp "$JOB/harness_overlay_changes.txt" "$RUN_ROOT/"

free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }
SQUID_PORT=$(free_port)
BROKER_PORT=$(free_port)
while [ "$BROKER_PORT" = "$SQUID_PORT" ]; do BROKER_PORT=$(free_port); done

# --- gateway: the image's own supervisor with configurable loopback ports (3128/8080 cannot be shared on a node)
apptainer exec --containall "$JOB/bixbench3-network-gateway_1.0.0.sif" cat /app/bixbench3/network_gateway/supervisor.py > "$JOB/supervisor.orig.py"
python3 - "$JOB/supervisor.orig.py" "$JOB/supervisor.py" <<'PY'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
patched = source.replace(
    '"http_port 3128\\n"',
    '"http_port 127.0.0.1:" + os.environ.get("BB3_SQUID_PORT", "3128") + "\\n"',
).replace(
    "threading.Thread(target=run_server, daemon=True)",
    'threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": int(os.environ.get("BB3_BROKER_PORT", "8080"))}, daemon=True)',
)
assert patched.count("BB3_SQUID_PORT") == 1 and patched.count("BB3_BROKER_PORT") == 1, "supervisor patch did not apply"
open(sys.argv[2], "w", encoding="utf-8").write(patched)
PY
[ $? -eq 0 ] || exit 2
printf '127.0.0.1 localhost\n127.0.0.1 network-gateway\n::1 localhost\n' > "$JOB/hosts"
# apt under `apptainer --fakeroot` (root-mapped user namespace, no /etc/subuid): apt cannot drop to
# its _apt user (setgroups fails) and the image's archives/partial dir belongs to _apt (unmapped, so
# root cannot write it). In the GCP Docker sandbox apt works as root; these two settings restore that.
printf 'APT::Sandbox::User "root";\nDir::Cache::Archives "/var/cache/apt/sherlock-archives/";\n' > "$JOB/apt-sherlock.conf"
NCPU=$(python3 "$REPO/sherlock/cpu_view.py" "$JOB/cpuinfo" "$JOB/cpu_online")
echo "[sherlock] sandbox CPU view: $NCPU CPUs"
NMEM=$(python3 "$REPO/sherlock/mem_view.py" "$JOB/meminfo") || exit 2
echo "[sherlock] sandbox memory view: $NMEM GB; CPU: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"

# --- sandbox provider config (mirrors the compose `default` service)
python3 - "$JOB/sandbox.json" <<PY
import json, sys
proxy = "http://network-gateway:$SQUID_PORT"
cfg = {
    "sif": "$JOB/bixbench3-sandbox_1.0.0.sif",
    "overlay_dir": "$JOB/overlay",
    "binds": [["$DATA_DIR", "/data", "ro"], ["$RUN_ROOT/workspace", "/workspace", "rw"], ["$RUN_ROOT/outputs", "/outputs", "rw"],
              ["$JOB/cpuinfo", "/proc/cpuinfo", "ro"], ["$JOB/cpu_online", "/sys/devices/system/cpu/online", "ro"], ["$JOB/meminfo", "/proc/meminfo", "ro"],
              ["$JOB/apt-sherlock.conf", "/etc/apt/apt.conf.d/99-sherlock-fakeroot", "ro"]],
    "jail_dir": "$JOB/jaildir",
    "jail_log_dir": "$JOB/jaillog",
    "proxy_port": $SQUID_PORT,
    "hosts_file": "$JOB/hosts",
    "workdir": "/workspace",
    "host_path": "$JOB/bridge/bin:/usr/local/bin:/usr/bin:/bin",
    "env": {"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "http_proxy": proxy, "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1",
            "PS1": "\\\\u@\\\\h:\\\\w# "},
    "gateway": {"sif": "$JOB/bixbench3-network-gateway_1.0.0.sif", "squid_port": $SQUID_PORT,
                "broker_port": $BROKER_PORT, "supervisor_file": "$JOB/supervisor.py",
                "squid_log_dir": "$JOB/squidlog", "log_file": "$JOB/gateway.log"},
}
json.dump(cfg, open(sys.argv[1], "w"), indent=2)
PY

# --- run.sh: the official script with host paths rewritten
python3 - "$BUNDLE/run.sh.template" "$RUN_ROOT/run.sh" <<PY
import sys
text = open(sys.argv[1], encoding="utf-8").read()
inspect_old = "uv run --project /opt/bixbench3 inspect eval "
assert text.count(inspect_old) == 1
smoke = "${BB3_SMOKE_MESSAGES:-}"
extra = f"--message-limit {int(smoke)} " if smoke else ""
text = text.replace(inspect_old, "$VENV/bin/inspect eval --sandbox apptainer:$JOB/sandbox.json " + extra)
for old, new in [
    ("uv run python - ", "$VENV/bin/python - "),
    ("/var/lib/bixbench3", "$RUN_ROOT"),
    ("/mnt/bixbench3-data/data", "$DATA_DIR"),
    ("/opt/bixbench3", "$SRC"),
    ("/dev/shm/bixbench3.env", "$SECRETS/bixbench3.env"),
    ("BIXBENCH3_BROKER_HOST_PORT=18080", "BIXBENCH3_BROKER_HOST_PORT=$BROKER_PORT"),
    ("BIXBENCH3_BROKER_ENDPOINT=http://127.0.0.1:18080", "BIXBENCH3_BROKER_ENDPOINT=http://127.0.0.1:$BROKER_PORT"),
    ("systemctl start bixdash-collect.service || true", "true  # sherlock: final dashboard snapshot is taken by run_job.sbatch"),
]:
    assert old in text, old
    text = text.replace(old, new)
for leftover in ("/var/lib/bixbench3", "/opt/bixbench3", "/mnt/bixbench3-data", "18080", "systemctl"):
    assert leftover not in text, leftover
open(sys.argv[2], "w", encoding="utf-8").write(text)
PY
[ $? -eq 0 ] || exit 2
python3 - "$RUN_ROOT/run_manifest.json" <<PY
import json, os, sys
p = sys.argv[1]
m = json.load(open(p))
m["platform"].update({"slurm_job_id": os.environ.get("SLURM_JOB_ID"), "node": os.uname().nodename,
                      "partition": os.environ.get("SLURM_JOB_PARTITION"), "cpus": int(os.environ.get("SLURM_CPUS_PER_TASK", "6")),
                      "memory_mb": int(os.environ.get("SLURM_MEM_PER_NODE", "0") or 0),
                      "cpu_model": next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), None),
                      "slurm_constraint": os.environ.get("SLURM_JOB_CONSTRAINTS") or None})
json.dump(m, open(p, "w"), indent=2, sort_keys=True)
PY

# --- host helper: lets the runner container use the host's apptainer/gcloud (see sherlock/bridge)
mkdir -p "$JOB/bridge/bin" && chmod 700 "$JOB/bridge"
cp "$REPO/sherlock/bridge/bin/apptainer" "$REPO/sherlock/bridge/bin/gcloud" "$JOB/bridge/bin/"
export APPTAINER_TMPDIR=$JOB/tmp TMPDIR=$JOB/tmp
python3 "$REPO/sherlock/bridge/hostexec.py" "$JOB/bridge/hostexec.sock" > "$JOB/hostexec.log" 2>&1 &
HOSTEXEC=$!
for _ in $(seq 30); do [ -S "$JOB/bridge/hostexec.sock" ] && break; sleep 1; done
[ -S "$JOB/bridge/hostexec.sock" ] || { echo "host helper did not start"; exit 2; }

# --- environment of the runner container (job-local sample buffer, branch code first on sys.path)
XDG_DATA_HOME=$JOB/xdg
cat > "$JOB/runner.env" <<ENV
PATH=$JOB/bridge/bin:$VENV/bin:/opt/uvbin:/usr/local/bin:/usr/bin:/bin
UV_PROJECT_ENVIRONMENT=$VENV
UV_NO_SYNC=1
UV_PYTHON_DOWNLOADS=never
UV_CACHE_DIR=$SCRATCH/bixbench3/cache/uv
HOME=$HOME
XDG_DATA_HOME=$XDG_DATA_HOME
TMPDIR=$JOB/tmp
PYTHONPATH=$SRC/src
OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
BB3_HOSTEXEC_SOCK=$JOB/bridge/hostexec.sock
LANG=C.UTF-8
ENV

# --- live dashboard collector (inside this job; stops with it)
python3 - "$BUNDLE/run_meta.json" "$JOB/bixdash/run_meta.json" <<PY
import json, os, sys
meta = json.load(open(sys.argv[1]))
meta["vm"] = f"sherlock:{os.uname().nodename}:job{os.environ.get('SLURM_JOB_ID')}"
json.dump(meta, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
PY
export BIXDASH_RUN_ROOT=$RUN_ROOT BIXDASH_HARNESS=$SRC BIXDASH_STATE=$JOB/bixdash
export BIXDASH_BUFFER_GLOB="$XDG_DATA_HOME/inspect_ai/samplebuffer/*/*.db"
COLLECT="python3 $REPO/tools/bixdash/vm/collect.py --grade-every 0"
( while true; do sleep 60; $COLLECT >> "$JOB/collector.log" 2>&1; sleep 240; done ) &
COLLECTOR=$!

# --- keep a copy on scratch ($L_SCRATCH_JOB is purged at job end; the GCS upload in run.sh is the durable record)
DEST=$SCRATCH/bixbench3/runs/$RUN_ID
keep_copy() {  # keep_copy [quick]: quick = local copy only (must fit in Slurm's 30 s KillWait)
  mkdir -p "$DEST/sherlock"
  rsync -a --exclude workspace "$RUN_ROOT/" "$DEST/"
  cp -a "$JOB/gateway.log" "$JOB/collector.log" "$JOB/hostexec.log" "$JOB/key_relay.log" "$JOB/sandbox.json" "$JOB/supervisor.py" "$JOB/sandbox_image.json" "$JOB/task_env_build.log" "$DEST/sherlock/" 2>/dev/null
  cp -a "$JOB/jaillog" "$JOB/squidlog" "$JOB/bixdash" "$DEST/sherlock/" 2>/dev/null
  cp -a "$XDG_DATA_HOME/inspect_ai/samplebuffer" "$DEST/sherlock/" 2>/dev/null
  echo "[sherlock] results kept in $DEST"
  [ "${1:-}" = quick ] && return 0
  local results_uri f
  results_uri=$(field results_uri)
  for f in "$JOB/jaillog/jail.log" "$JOB/squidlog/access.log"; do
    [ -s "$f" ] && timeout 60 gcloud storage cp --no-clobber "$f" "$results_uri/sherlock/$(basename "$(dirname "$f")")-$(basename "$f")" >/dev/null 2>&1
  done
}

# --- scancel / time limit: publish a final "cancelled" dashboard snapshot before exiting.
# Slurm sends SIGTERM and SIGKILLs 30 s later (KillWait); bash runs a trap only between
# foreground commands, so the run is started in the background and awaited with `wait`.
RUNPID=""
on_term() {
  trap - TERM INT
  echo "[sherlock] job cancelled or timed out"
  kill "$COLLECTOR" 2>/dev/null; COLLECTOR=""
  # run.sh's own EXIT trap also writes status.json (as "completed" when interrupted): let it finish first
  if [ -n "$RUNPID" ]; then
    kill -TERM "$RUNPID" 2>/dev/null
    for _ in $(seq 16); do kill -0 "$RUNPID" 2>/dev/null || break; sleep 0.5; done
  fi
  python3 - "$RUN_ROOT/status.json" <<'PY'
import json, sys
from datetime import UTC, datetime
json.dump({"phase": "cancelled", "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
           "remote_exit_status": 143, "systemd_unit": "slurm"}, open(sys.argv[1], "w"), indent=2)
PY
  keep_copy quick
  timeout 12 $COLLECT >> "$JOB/collector.log" 2>&1
  exit 143
}
trap on_term TERM INT

# --- the run: official run.sh inside the python:3.12 runner (exact uv.lock environment)
apptainer exec --cleanenv --env-file "$JOB/runner.env" --pwd "$SRC" \
  --bind "$JOB" --bind "$SECRETS" --bind "$BB3" --bind "$DATA_DIR:$DATA_DIR:ro" \
  --bind "$(dirname "$(readlink -f "$(command -v uv)")"):/opt/uvbin:ro" --bind "$SCRATCH/bixbench3/cache/uv" \
  "$RUNNER" bash "$RUN_ROOT/run.sh" &
RUNPID=$!
wait "$RUNPID"
rc=$?
echo "[sherlock] run.sh exited with $rc"
kill "$COLLECTOR" 2>/dev/null; COLLECTOR=""
$COLLECT >> "$JOB/collector.log" 2>&1

keep_copy
exit $rc

#!/bin/bash
set -euo pipefail
root=/var/lib/bixbench3
mkdir -p /etc/needrestart/conf.d
cat >/etc/needrestart/conf.d/bixbench3.conf <<'PERL'
$nrconf{override_rc}->{qr(^bixbench3-run\.service$)} = 0;
$nrconf{override_rc}->{qr(^docker\.service$)} = 0;
$nrconf{override_rc}->{qr(^containerd\.service$)} = 0;
PERL
# All installation is outside the scientific run's measured clock.
if ! docker image inspect bixbench3-sandbox:task11-lite-v1 >/dev/null 2>&1; then
  /snap/bin/gcloud storage cp gs://bixbench3-task11-jex20-results/runtime-cache/task11-lite-v1.tar.gz /var/cache/task11-lite-v1.tar.gz
  test "$(stat -c%s /var/cache/task11-lite-v1.tar.gz)" -gt 100000000
  gzip -t /var/cache/task11-lite-v1.tar.gz
  gzip -dc /var/cache/task11-lite-v1.tar.gz | docker load
fi
cd /opt/bixbench3/tools/proxy_study
if ! docker image inspect bixbench3-sandbox:proxy-study-v2 >/dev/null 2>&1; then
  docker build -t bixbench3-sandbox:proxy-study-v2 .
fi
docker run --rm --network none bixbench3-sandbox:proxy-study-v2 python3 -c 'import sys,pandas,numpy;print(sys.executable,pandas.__version__,numpy.__version__)'
docker run --rm --network none bixbench3-sandbox:proxy-study-v2 Rscript -e 'library(DESeq2);library(piano);library(biomaRt);sessionInfo()'
docker run --rm --network none -v /opt/bixbench3/tools/proxy_study/runtime_smoke.R:/runtime_smoke.R:ro bixbench3-sandbox:proxy-study-v2 Rscript /runtime_smoke.R

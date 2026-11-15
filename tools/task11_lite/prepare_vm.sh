#!/bin/bash
set -euo pipefail
# Packages may still update; defer automatic restarts of the live benchmark and Docker.
mkdir -p /etc/needrestart/conf.d
cat > /etc/needrestart/conf.d/bixbench3.conf <<'PERL'
$nrconf{override_rc}->{qr(^bixbench3-run\.service$)} = 0;
$nrconf{override_rc}->{qr(^docker\.service$)} = 0;
$nrconf{override_rc}->{qr(^containerd\.service$)} = 0;
PERL
cd /opt/bixbench3/tools/task11_lite
mkdir -p /var/lib/bixbench3/lite_data/provided /var/lib/bixbench3/lite_data/reference
cp -a /mnt/bixbench3-data/data/metadata /var/lib/bixbench3/lite_data/
cp /var/lib/bixbench3/lite-staging/provided_counts.csv /var/lib/bixbench3/lite_data/provided/counts.csv
cp -a /var/lib/bixbench3/lite-staging/reference-data/. /var/lib/bixbench3/lite_data/reference/
chmod -R a+rX /var/lib/bixbench3/lite_data
if ! docker image inspect bixbench3-sandbox:task11-lite-v1 >/dev/null 2>&1; then
  docker build -t bixbench3-sandbox:task11-lite-v1 .
fi
docker run --rm --network none bixbench3-sandbox:task11-lite-v1 Rscript -e 'library(DESeq2);library(piano);library(biomaRt);library(readxl);sessionInfo()' > /var/lib/bixbench3/lite-runtime-inventory.txt

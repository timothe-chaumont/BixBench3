#!/usr/bin/env bash
# Let run VMs (and optionally people) from OTHER GCP projects publish to the
# team's central dashboard bucket — and nothing else.
#
# Run by an admin of the dashboard bucket's project, once per member project:
#   bash tools/grant_dashboard_access.sh <MEMBER_PROJECT_ID> [member@email ...]
#
# What it grants, on gs://$DASH_BUCKET only, restricted by an IAM condition to
# objects under _dashboard/ :
#   - roles/storage.objectUser to <project-number>-compute@developer.gserviceaccount.com
#     (the default compute service account the BixBench3 runner attaches to run VMs)
#   - the same role to each email given (to run import_finished_run.py from a laptop)
# Results buckets, ground truth and everything else stay private to each project.
set -euo pipefail

DASH_BUCKET="${DASH_BUCKET:-bixbench3-task11-jex20-results}"
PREFIX="_dashboard/"

if [ $# -lt 1 ]; then
  echo "usage: $0 <member-project-id> [member-email ...]" >&2
  exit 2
fi
MEMBER_PROJECT="$1"; shift

# IAM conditions require uniform bucket-level access.
UBLA=$(gcloud storage buckets describe "gs://$DASH_BUCKET" --format='value(uniform_bucket_level_access)')
if [ "$UBLA" != "True" ]; then
  echo "gs://$DASH_BUCKET does not use uniform bucket-level access; prefix-restricted grants are impossible." >&2
  echo "Enable it (gcloud storage buckets update gs://$DASH_BUCKET --uniform-bucket-level-access) or use a dedicated dashboard bucket." >&2
  exit 1
fi

NUMBER=$(gcloud projects describe "$MEMBER_PROJECT" --format='value(projectNumber)' 2>/dev/null || true)
if [ -z "$NUMBER" ]; then
  echo "Cannot read project $MEMBER_PROJECT. Ask its owner for the project NUMBER and run:" >&2
  echo "  MEMBER_NUMBER=<number> $0 $MEMBER_PROJECT ..." >&2
  NUMBER="${MEMBER_NUMBER:-}"
  [ -n "$NUMBER" ] || exit 1
fi

CONDITION="expression=resource.name.startsWith(\"projects/_/buckets/${DASH_BUCKET}/objects/${PREFIX}\"),title=bixdash-${MEMBER_PROJECT},description=bixdash snapshots only"
MEMBERS=("serviceAccount:${NUMBER}-compute@developer.gserviceaccount.com")
for email in "$@"; do MEMBERS+=("user:${email}"); done

for member in "${MEMBERS[@]}"; do
  echo "granting objectUser on gs://${DASH_BUCKET}/${PREFIX}* to ${member}"
  gcloud storage buckets add-iam-policy-binding "gs://${DASH_BUCKET}" \
    --member="$member" --role=roles/storage.objectUser --condition="$CONDITION" >/dev/null
done
echo "Done. Member runs: add --dashboard-uri gs://${DASH_BUCKET}/_dashboard to the launch command."

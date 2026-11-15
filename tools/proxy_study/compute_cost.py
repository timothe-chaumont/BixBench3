"""Retail resource estimate from Compute Engine start/stop operation timestamps."""

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

CPU_H = 0.03319155
MEMORY_GIB_H = 0.00444885
IPV4_H = 0.005
STANDARD_GIB_H = 0.04 / 730
BALANCED_GIB_H = 0.1 / 730


def estimate(operations, start, end):
    groups = defaultdict(list)
    for row in operations:
        if row.get("error") or row.get("operationType") not in ("start", "stop"):
            continue
        groups[row["targetLink"].rsplit("/", 1)[-1]].append(row)
    intervals = []
    for vm, rows in groups.items():
        active = None
        for row in sorted(rows, key=lambda r: r["startTime"]):
            when = datetime.fromisoformat(row["startTime"]).astimezone(UTC)
            if row["operationType"] == "start":
                active = when
            elif active is not None:
                a, b = max(start, active), min(end, when)
                if b > a:
                    intervals.append(
                        {
                            "vm": vm,
                            "start": a.isoformat(),
                            "end": b.isoformat(),
                            "hours": (b - a).total_seconds() / 3600,
                        }
                    )
                active = None
        if active is not None and end > max(start, active):
            a = max(start, active)
            intervals.append(
                {
                    "vm": vm,
                    "start": a.isoformat(),
                    "end": end.isoformat(),
                    "hours": (end - a).total_seconds() / 3600,
                }
            )
    hours = sum(i["hours"] for i in intervals)
    window_h = (end - start).total_seconds() / 3600
    rates = {
        "vcpu_hour": CPU_H,
        "memory_gib_hour": MEMORY_GIB_H,
        "external_ipv4_hour": IPV4_H,
        "standard_disk_gib_hour_730h_month": STANDARD_GIB_H,
        "balanced_disk_gib_hour_730h_month": BALANCED_GIB_H,
    }
    parts = {
        "vcpu_and_ram_usd": hours * (6 * CPU_H + 32 * MEMORY_GIB_H),
        "ipv4_usd": hours * IPV4_H,
        "two_retained_200gib_boot_disks_usd": window_h * 400 * STANDARD_GIB_H,
        "retained_18gib_shared_input_disk_usd": window_h * 18 * BALANCED_GIB_H,
    }
    return {
        "source": "GCE start/stop operations and public Iowa retail rates",
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "vm_hours": hours,
        "intervals": intervals,
        "rates_usd": rates,
        "components_usd": parts,
        "estimated_total_usd": sum(parts.values()),
        "limitations": "Operation start timestamps approximate RUNNING/STOPPING billing boundaries. Retained disks charged through entire window. Excludes GCS, Artifact Registry, machine-image storage, network transfer, existing dashboard, unrelated disks, discounts, taxes and provider billing reconciliation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operations", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--start", default="2026-11-15T08:55:08+00:00")
    parser.add_argument("--end")
    a = parser.parse_args()
    value = estimate(
        json.loads(a.operations.read_text()),
        datetime.fromisoformat(a.start),
        datetime.fromisoformat(a.end) if a.end else datetime.now(UTC),
    )
    a.out.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({k: v for k, v in value.items() if k != "intervals"}, indent=2))

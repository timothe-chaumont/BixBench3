"""Losslessly materialize the input workbook's gene-set rows as GMT (not answers)."""

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def convert(source, dest):
    wb = load_workbook(source, read_only=True, data_only=True)
    assert len(wb.worksheets) == 1
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    sets = []
    for row in rows[2:]:
        if row[0] is None:
            continue
        values = [str(v) for v in row if v is not None]
        assert len(values) >= 3 and not any("\t" in v or "\n" in v for v in values)
        sets.append(values)
    assert len(sets) == 89
    dest.write_text("".join("\t".join(row) + "\n" for row in sets))
    # Check exact names, URLs, gene order, membership, and multiplicity after round trip.
    assert [line.split("\t") for line in dest.read_text().splitlines()] == sets
    provenance = {
        "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "derived_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "worksheet": wb.worksheets[0].title,
        "source_rows_1_based": "3:91",
        "sets": len(sets),
        "operation": "one-pass conversion of non-empty input cells to GMT; original excluded set is retained; no statistical analysis, filtering, or downstream target used",
    }
    dest.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("source", type=Path)
    a.add_argument("dest", type=Path)
    v = a.parse_args()
    print(json.dumps(convert(v.source, v.dest), indent=2))

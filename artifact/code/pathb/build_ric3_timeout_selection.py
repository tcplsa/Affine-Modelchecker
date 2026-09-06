#!/usr/bin/env python3
"""Select stock-rIC3 four-replica timeouts for an independent rerun."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.selection.read_text(encoding="utf-8"))
    by_id = {model["id"]: model for model in source["models"]}
    with args.result.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    timed_out = {
        row["model_id"]
        for row in rows
        if row.get("stock_native_legacy4_status") == "TIMEOUT"
    }
    models = [by_id[model_id] for model_id in sorted(timed_out)]
    args.output.write_text(json.dumps({
        "selection_rule": "stock rIC3 native legacy, four replicas, 1800 seconds: TIMEOUT",
        "models": models,
    }, indent=2) + "\n", encoding="utf-8")
    print("selected=%s" % len(models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

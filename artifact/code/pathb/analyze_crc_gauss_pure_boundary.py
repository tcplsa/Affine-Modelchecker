#!/usr/bin/env python3
"""Report pure CRC Gaussian phase boundaries and four-lane confirmations."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--confirm", type=Path, action="append", default=[])
    parser.add_argument("--screen-timeout", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    params = {model["stem"]: model["params"] for model in models}
    screen = {row["name"]: row for row in load_tsv(args.screen)}
    confirmations: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in args.confirm:
        for row in load_tsv(path):
            confirmations[row["name"]].append(row)

    lines = [
        "# Pure Gaussian CRC Boundary",
        "",
        "All single-lane rows use the same MC-XAG PDR policy. Only the pure SAT "
        "backend differs. Four-lane rows, when present, use four replicas of the "
        "same backend rather than a mixed portfolio.",
        "",
        "## Single-lane boundary",
        "",
        "| CRC | Bits/transition | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |",
        "| --- | ---: | --- | --- | --- |",
    ]
    strict = []
    for name, row in sorted(
        screen.items(), key=lambda item: (params[item[0]]["width"], params[item[0]]["symbol_bits"])
    ):
        p = params[name]
        values = []
        for config in ("xag_cadical", "xag_cmsat_no_gauss", "xag_cmsat_gauss"):
            status = row[f"{config}_status"]
            wall = float(row[f"{config}_wall_seconds"])
            values.append(f"SAFE ({wall:.3f}s)" if status == "SAFE" else "TIMEOUT")
        lines.append(f"| CRC-{p['width']} | {p['symbol_bits']} | {values[0]} | {values[1]} | {values[2]} |")
        if values[0] == "TIMEOUT" and values[1] == "TIMEOUT" and row["xag_cmsat_gauss_status"] == "SAFE":
            strict.append(name)

    lines.extend([
        "",
        f"At the {args.screen_timeout}-second screen limit, strict Gaussian-only points: **{len(strict)}**.",
        "",
    ])
    if confirmations:
        lines.extend([
            "## Pure four-lane confirmation",
            "",
            "| CRC | Bits/transition | 4x CaDiCaL | 4x CMSat no-Gauss | 4x CMSat Gaussian | Repetitions |",
            "| --- | ---: | --- | --- | --- | ---: |",
        ])
        for name in sorted(confirmations, key=lambda n: (params[n]["width"], params[n]["symbol_bits"])):
            p = params[name]
            rows = confirmations[name]
            def consensus(config: str) -> str:
                states = {row[f"{config}_status"] for row in rows}
                return next(iter(states)) if len(states) == 1 else "/".join(sorted(states))
            lines.append(
                f"| CRC-{p['width']} | {p['symbol_bits']} | {consensus('cadical_4x')} | "
                f"{consensus('cmsat_no_gauss_4x')} | {consensus('cmsat_gauss_4x')} | {len(rows)} |"
            )
        lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"screen_models": len(screen), "strict": len(strict), "confirmed": len(confirmations)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

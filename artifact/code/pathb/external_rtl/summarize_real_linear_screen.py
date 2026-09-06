#!/usr/bin/env python3
"""Summarize pure-backend screens without treating timeouts as solved results."""

from __future__ import annotations

import re
import sys
from pathlib import Path


RESULT = re.compile(r"(?:result:\s*|PDR_STATS.*?\bresult=)(safe|unsafe|unknown)")
TIME = re.compile(r"time = ([0-9.]+)s")
DEPTH = re.compile(r"c PDR_STATS .* depth=(-?[0-9]+)")
QUERIES = re.compile(r"c PDR_COUNTERS.*?\bqueries=([0-9]+)")
STATUS = re.compile(r"SCREEN_STATUS ([^\n]+)")


def value(pattern: re.Pattern[str], text: str) -> str:
    matches = pattern.findall(text)
    return matches[-1] if matches else "-"


def main() -> None:
    directory = Path(sys.argv[1])
    print("# Real Linear Datapath Screen")
    print()
    print("All rows are single-lane, `--forward-xag 1`, with preprocessing disabled")
    print("for CMSat. `unknown` is not evidence for either backend.")
    print()
    print("| Model | Backend | Status | Result | Time (s) | Last depth | Last queries |")
    print("| --- | --- | --- | --- | ---: | ---: | ---: |")
    for log in sorted(directory.glob("*.log")):
        text = log.read_text(encoding="utf-8", errors="replace")
        stem = log.stem
        if "__" not in stem:
            continue
        model, backend = stem.split("__", 1)
        result = value(RESULT, text)
        status = value(STATUS, text)
        # Older screen logs predate explicit status markers.  They were emitted
        # by a wall-clock wrapper and have periodic unknown statistics but no
        # final solver result, which is a timeout rather than missing evidence.
        if status == "-" and result == "unknown" and value(TIME, text) == "-":
            status = "timeout-legacy"
        print(
            f"| {model} | {backend} | {status} | {result} | "
            f"{value(TIME, text)} | {value(DEPTH, text)} | {value(QUERIES, text)} |"
        )


if __name__ == "__main__":
    main()

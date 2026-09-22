#!/usr/bin/env python3
"""Persistent experiment worker used by the MC Compare Web UI."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from compare_runner import ExperimentRunner


RUNNER: Optional[ExperimentRunner] = None
CANCEL_REQUESTED = threading.Event()
HEARTBEAT_STOP = threading.Event()
STATE_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_json(path: Path, data: Dict[str, Any]) -> None:
    temporary = path.with_name(
        "%s.tmp.%s.%d" % (path.name, socket.gethostname(), os.getpid())
    )
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
    temporary.replace(path)


def update_state(path: Path, values: Dict[str, Any]) -> None:
    with STATE_LOCK:
        try:
            with path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError):
            state = {}
        state.update(values)
        state["updated_at"] = now_iso()
        state["worker_heartbeat"] = now_iso()
        atomic_json(path, state)


def heartbeat(path: Path) -> None:
    while not HEARTBEAT_STOP.wait(5.0):
        update_state(path, {"worker_pid": os.getpid()})


def on_signal(_signum: int, _frame: object) -> None:
    CANCEL_REQUESTED.set()
    if RUNNER is not None:
        RUNNER.cancel()


def wait_for_spec(path: Path, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("worker specification was not published")
        time.sleep(0.05)


def main() -> None:
    global RUNNER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    final_status = "error"
    error_text = ""
    try:
        wait_for_spec(args.spec)
        with args.spec.open("r", encoding="utf-8") as handle:
            settings = json.load(handle)
        heartbeat_thread = threading.Thread(
            target=heartbeat, args=(args.state,), name="compare-heartbeat", daemon=True
        )
        heartbeat_thread.start()

        def progress(event: Dict[str, Any]) -> None:
            event_type = event["type"]
            if event_type == "started":
                update_state(args.state, {
                    "status": "running", "total": event["total"],
                    "worker_pid": os.getpid(),
                })
            elif event_type == "row":
                update_state(args.state, {
                    "status": "running", "completed": event["completed"],
                    "total": event["total"], "worker_pid": os.getpid(),
                })
            elif event_type == "finished":
                update_state(args.state, {
                    "completed": event["completed"], "total": event["total"],
                    "worker_pid": os.getpid(),
                })

        RUNNER = ExperimentRunner(settings, progress)
        if CANCEL_REQUESTED.is_set():
            RUNNER.cancel()
        result = RUNNER.run()
        final_status = "cancelled" if result["cancelled"] else "completed"
    except Exception as error:
        error_text = "%s: %s" % (type(error).__name__, error)
        final_status = "cancelled" if CANCEL_REQUESTED.is_set() else "error"
    finally:
        HEARTBEAT_STOP.set()
        if RUNNER is not None and CANCEL_REQUESTED.is_set():
            RUNNER.cancel()
        update_state(args.state, {
            "status": final_status,
            "worker_pid": os.getpid(),
            "error": error_text,
            "finished_at": now_iso(),
        })
        if final_status in {"completed", "cancelled"}:
            try:
                args.spec.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()

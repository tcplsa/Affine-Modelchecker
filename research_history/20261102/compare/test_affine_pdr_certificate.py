#!/usr/bin/env python3
"""Small soundness regressions for check_affine_pdr_certificate.py."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


PASS_MODEL = """aag 1 0 1 0 0 1
2 0 0
2
"""

INIT_FAIL_MODEL = """aag 1 0 1 0 0 1
2 0 1
2
"""

CONSECUTION_FAIL_MODEL = """aag 1 0 1 0 0 1
2 1 0
2
"""

LEMMA_MODEL = """aag 2 0 2 0 0 1
2 4 0
4 4 0
2
"""

LEMMA = """mc-pdr-invariant-v1 2
c block r = true
2 0
"""

XOR_PASS_MODEL = """aag 5 0 2 0 3 1
2 2 0
4 4 0
10
6 3 5
8 2 4
10 7 9
"""


def invoke(
    checker: Path, wrapper: Path, model: Path, invariant: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        "python3",
        str(checker),
        str(model),
        "--cmsat-wrapper",
        str(wrapper),
    ]
    if invariant is not None:
        command.extend(("--invariant", str(invariant)))
    return subprocess.run(command, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--cmsat-wrapper", type=Path, required=True)
    args = parser.parse_args()
    checker = args.checker.resolve()
    wrapper = args.cmsat_wrapper.resolve()
    with tempfile.TemporaryDirectory(prefix="affine-cert-test-") as temporary:
        root = Path(temporary)
        cases = {}
        for name, content in (
            ("pass", PASS_MODEL),
            ("init_fail", INIT_FAIL_MODEL),
            ("consecution_fail", CONSECUTION_FAIL_MODEL),
            ("lemma", LEMMA_MODEL),
            ("xor_pass", XOR_PASS_MODEL),
        ):
            path = root / f"{name}.aag"
            path.write_text(content, encoding="ascii")
            cases[name] = path
        invariant = root / "lemma.inv"
        invariant.write_text(LEMMA, encoding="ascii")

        expected = (
            ("inductive property", invoke(checker, wrapper, cases["pass"]), True),
            ("bad initial state", invoke(checker, wrapper, cases["init_fail"]), False),
            (
                "non-inductive property",
                invoke(checker, wrapper, cases["consecution_fail"]),
                False,
            ),
            ("missing strengthening lemma", invoke(checker, wrapper, cases["lemma"]), False),
            (
                "valid strengthening lemma",
                invoke(checker, wrapper, cases["lemma"], invariant),
                True,
            ),
            ("inductive XOR property", invoke(checker, wrapper, cases["xor_pass"]), True),
        )
        for label, result, should_pass in expected:
            passed = result.returncode == 0
            if passed != should_pass:
                raise RuntimeError(
                    f"{label}: expected pass={should_pass}, got {result.returncode}\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
            if label == "inductive XOR property" and "xors=1" not in result.stdout:
                raise RuntimeError(f"XOR regression was not recognized:\n{result.stdout}")
            print(f"PASS\t{label}\texpected_accept={int(should_pass)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

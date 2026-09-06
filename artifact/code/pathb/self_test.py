#!/usr/bin/env python3
"""Path B generator self-test.

Verifies that the generated AAG files are well-formed and that, for a small
set of instances, the rIC3 solver verdict agrees with the generator's
reference-expected outcome.  This is the sanity gate before any B1 sweep.

Run:
  python3 pathb/self_test.py --ric3 /home/wudl/rIC3/target/release/ric3 \
      --tmp /tmp/pathb_selftest
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathb.families.lfsr import generate_lfsr, reference_check_lfsr  # noqa: E402
from pathb.families.adders import generate_adder, reference_check_adder  # noqa: E402
from pathb.aag_writer import to_aag_text  # noqa: E402
from pathb.blif_writer import to_blif_text  # noqa: E402
from pathb.families.affine_equiv import generate_affine_equiv  # noqa: E402
from pathb.families.affine_warmup import generate_affine_warmup  # noqa: E402
from pathb.families.affine_phase_sync import (  # noqa: E402
    generate_affine_phase_sync,
    full_rank_matrix,
    gf2_rank,
)


def _ric3_verdict(ric3_bin, aag_path, timeout=60):
    proc = subprocess.run(
        [ric3_bin, "check", aag_path, "ic3"],
        capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout + proc.stderr).strip()
    if "UNSAT" in out:
        return "SAFE"
    if "SAT" in out:
        return "UNSAFE"
    return "UNKNOWN"


def _parse_aag_header(text):
    header = text.strip().splitlines()[0].split()
    assert header[0] == "aag"
    M, I, L, O, A = map(int, header[1:6])
    B = C = 0
    if len(header) > 6:
        B = int(header[6])
    if len(header) > 7:
        C = int(header[7])
    return M, I, L, O, A, B, C


def _check_aag_wellformed(text):
    """Basic AAG structural checks."""
    lines = text.strip().splitlines()
    M, I, L, O, A, B, C = _parse_aag_header(text)
    body = lines[1:]
    # count tokens: inputs I, latches L (3 cols), outputs O, bad B, con C,
    # ands A (3 cols)
    idx = 0
    for _ in range(I):
        idx += 1
    for _ in range(L):
        parts = body[idx].split()
        assert len(parts) >= 2, f"latch row malformed: {body[idx]}"
        idx += 1
    for _ in range(O):
        idx += 1
    for _ in range(B):
        idx += 1
    for _ in range(C):
        idx += 1
    for _ in range(A):
        parts = body[idx].split()
        assert len(parts) == 3, f"AND row malformed: {body[idx]}"
        idx += 1
    assert idx == len(body), f"trailing tokens: {idx} vs {len(body)}"
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ric3", default="/home/wudl/rIC3/target/release/ric3")
    p.add_argument("--tmp", default=tempfile.mkdtemp(prefix="pathb_selftest_"))
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()

    os.makedirs(args.tmp, exist_ok=True)

    cases = []
    # (name, net, expected, ref)
    for width in (4, 8, 16):
        net = generate_lfsr(width=width, taps=[0], init=1, seed=1)
        ref = reference_check_lfsr(net, width, taps=[0], init=1,
                                   use_bias=False, seed=1)
        exp = "SAFE" if not ref["reached_zero"] else "UNSAFE"
        cases.append((f"lfsr_w{width}", net, exp, ref))

    for struct in ("ripple", "prefix", "carrysave"):
        net = generate_adder(width=8, struct=struct, mode="invariant", seed=1)
        ref = reference_check_adder(8, struct, "invariant", seed=1)
        cases.append((f"adder_{struct}_w8_inv", net, ref["expected"], ref))

    for target in (3, 15):
        net = generate_adder(width=4, struct="ripple", mode="counter",
                             target=target, seed=1)
        ref = reference_check_adder(4, "ripple", "counter", target=target)
        cases.append((f"adder_ripple_w4_cnt{target}", net,
                      ref["expected"], ref))

    for topology in ("serial", "balanced"):
        net = generate_affine_equiv(
            width=8, weight=5, rounds=2, inputs=3,
            topology=topology, seed=1)
        cases.append((f"affine_equiv_w8_{topology}", net, "SAFE",
                      {"expected": "SAFE", "topology": topology}))
    for delay in (3, 5):
        net = generate_affine_warmup(
            width=8, weight=4, rounds=2, delay=delay, inputs=3,
            topology="balanced", seed=1)
        cases.append((f"affine_warmup_w8_d{delay}", net, "SAFE",
                      {"expected": "SAFE", "delay": delay}))
    for delay in (2, 4):
        rows = full_rank_matrix(8, 5, 17 + delay)
        assert gf2_rank(rows, 8) == 8
        net = generate_affine_phase_sync(
            width=8, weight=5, rounds=2, delay=delay, inputs=3,
            topology="balanced", seed=17 + delay)
        cases.append((f"affine_phase_sync_w8_d{delay}", net, "SAFE",
                      {"expected": "SAFE", "delay": delay, "rank": 8}))

    failures = 0
    for name, net, expected, ref in cases:
        aag = to_aag_text(net)
        blif = to_blif_text(net)
        try:
            _check_aag_wellformed(aag)
            wellformed = True
        except AssertionError as e:
            wellformed = False
            print(f"[FAIL] {name}: AAG malformed: {e}")
            failures += 1
            continue

        aag_path = os.path.join(args.tmp, name + ".aag")
        with open(aag_path, "w") as f:
            f.write(aag)
        # verify with rIC3
        verdict = _ric3_verdict(args.ric3, aag_path, args.timeout)
        ok = (verdict == expected)
        status = "PASS" if (ok and wellformed) else "FAIL"
        if not (ok and wellformed):
            failures += 1
        print(f"[{status}] {name}: expected={expected} rIC3={verdict} "
              f"ref={ref} aag_ok={wellformed}")

    # also write BLIF files so downstream parsing can be eyeballed
    for name, net, expected, ref in cases:
        with open(os.path.join(args.tmp, name + ".blif"), "w") as f:
            f.write(to_blif_text(net))

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    print(f"artifacts in {args.tmp}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

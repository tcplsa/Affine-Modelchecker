#!/usr/bin/env python3
"""Build reproducible AIGER safety models from public affine RTL sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
COMPARE = ROOT / "test_tools" / "compare"
SOURCES = COMPARE / "external_linear_rtl"
SCRIPT_DIR = Path(__file__).resolve().parent
YOSYS = ROOT / "tools" / "yosys-0.40" / "yosys"
DEFAULT_OUT = COMPARE / "results" / "pathb_public_affine_rtl_v1"
OPENTITAN_SHA256 = "c61632878728613ba0403f2d068c03a5103165663b58d8dd50892ef032dec916"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def run_yosys(commands: list[str], log: Path) -> None:
    proc = subprocess.run(
        [str(YOSYS), "-Q", "-p", "; ".join(commands)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"Yosys failed; see {log}")


def adapt_opentitan(source: Path, output: Path) -> list[int]:
    if sha256(source) != OPENTITAN_SHA256:
        raise RuntimeError("OpenTitan prim_lfsr.sv changed; review the adapter first")
    text = source.read_text(encoding="utf-8")
    table_match = re.search(
        r"localparam logic \[167:0\] LFSR_COEFFS \[166\] =\s*'\{(.*?)\};",
        text,
        flags=re.DOTALL,
    )
    if not table_match:
        raise RuntimeError("cannot locate the OpenTitan coefficient table")
    coefficients = [int(value, 16) for value in re.findall(r"168'h([0-9A-Fa-f]+)", table_match.group(1))]
    if len(coefficients) != 166:
        raise RuntimeError(f"expected 166 OpenTitan coefficients, found {len(coefficients)}")

    text, count = re.subn(
        r"localparam logic \[167:0\] LFSR_COEFFS \[166\] =\s*'\{.*?\};",
        "wire [167:0] LFSR_COEFFS [0:165];",
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("coefficient-table adaptation failed")
    old = "parameter logic [LfsrDw-1:0][LfsrIdxDw-1:0] StatePerm = '0,"
    new = "parameter logic [LfsrDw*LfsrIdxDw-1:0] StatePerm = '0,"
    if text.count(old) != 1:
        raise RuntimeError("StatePerm declaration adaptation failed")
    text = text.replace(old, new)
    inactive_start = text.index("  logic [LfsrDw-1:0] sbox_out;")
    inactive_end = text.index(
        "  always_ff @(posedge clk_i or negedge rst_ni)", inactive_start
    )
    text = (
        text[:inactive_start]
        + "  // Specialization of the upstream NonLinearOut=0 and StatePermEn=0 branches.\n"
        + "  logic [LfsrDw-1:0] sbox_out;\n"
        + "  assign sbox_out = lfsr_q;\n"
        + "  assign state_o = StateOutDw'(sbox_out);\n\n"
        + text[inactive_end:]
    )
    output.write_text(text, encoding="utf-8")
    return coefficients


def common_finish(top: str, output: Path) -> list[str]:
    return [
        f"hierarchy -top {top}",
        f"prep -top {top}",
        "async2sync",
        "dffunmap",
        "flatten",
        "opt -noff",
        "techmap -map +/dff2ff.v",
        "simplemap",
        "opt -noff",
        "pmuxtree",
        "aigmap",
        "opt_clean",
        "setundef -zero",
        f"write_aiger -ascii -miter -symbols {output}",
    ]


def aiger_counts(path: Path) -> dict[str, int]:
    fields = path.open(encoding="ascii").readline().split()
    if fields[0] != "aag":
        raise RuntimeError(f"unexpected AIGER header in {path}")
    names = ("maxvar", "inputs", "latches", "outputs", "ands", "bad", "constraints")
    values = [int(value) for value in fields[1:]]
    return {name: values[index] if index < len(values) else 0 for index, name in enumerate(names)}


def specialize_verilog_lfsr_wrapper(config: str, output: Path) -> None:
    """Fix the string parameter in source because Yosys 0.40 chparam cannot."""
    template = (SCRIPT_DIR / "verilog_lfsr_style_formal_wrapper.v").read_text(
        encoding="utf-8"
    )
    old = 'parameter LFSR_CONFIG = "GALOIS",'
    new = f'parameter LFSR_CONFIG = "{config}",'
    if template.count(old) != 1:
        raise RuntimeError("cannot specialize the verilog-lfsr wrapper")
    output.write_text(template.replace(old, new), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    derived = out / "derived_rtl"
    aiger = out / "aiger"
    logs = out / "logs"
    for directory in (derived, aiger, logs):
        directory.mkdir(parents=True, exist_ok=True)

    opentitan_repo = SOURCES / "opentitan"
    opentitan_source = opentitan_repo / "hw/ip/prim/rtl/prim_lfsr.sv"
    adapted = derived / "opentitan_prim_lfsr_yosys040.sv"
    coefficients = adapt_opentitan(opentitan_source, adapted)
    models: list[dict[str, object]] = []

    for width in (8, 16, 24, 32, 64, 128):
        entropy_width = min(8, width)
        coeff = coefficients[width - 3]
        name = f"opentitan_prim_lfsr_transition_w{width}_e{entropy_width}"
        output = aiger / f"{name}.aag"
        commands = [
            "read_verilog -formal -sv -DSYNTHESIS "
            f"-I {opentitan_repo / 'hw/ip/prim/rtl'} {adapted} "
            f"{SCRIPT_DIR / 'opentitan_lfsr_formal_wrapper.sv'}",
            f"chparam -set WIDTH {width} -set ENTROPY_WIDTH {entropy_width} "
            f"-set COEFFS {coeff} opentitan_lfsr_transition_formal",
            *common_finish("opentitan_lfsr_transition_formal", output),
        ]
        run_yosys(commands, logs / f"{name}.log")
        models.append({
            "name": name,
            "family": "opentitan_prim_lfsr",
            "category": "public-rtl-controlled-affine",
            "expected": "SAFE",
            "path": str(output),
            "params": {"width": width, "entropy_width": entropy_width, "coefficients": hex(coeff)},
            "source": "https://github.com/lowRISC/opentitan",
            "source_commit": git_commit(opentitan_repo),
            "source_file": "hw/ip/prim/rtl/prim_lfsr.sv",
            "source_sha256": sha256(opentitan_source),
            "derived_rtl_sha256": sha256(adapted),
            "aag_sha256": sha256(output),
            "aiger": aiger_counts(output),
        })

    verilog_repo = SOURCES / "verilog-lfsr"
    verilog_source = verilog_repo / "rtl/lfsr.v"
    configurations = (
        ("crc16_ccitt", 16, 0x1021, "GALOIS", 0, 8),
        ("crc16_ibm", 16, 0x8005, "GALOIS", 1, 16),
        ("crc32_ethernet", 32, 0x04C11DB7, "GALOIS", 1, 8),
        ("crc32c", 32, 0x1EDC6F41, "GALOIS", 1, 16),
        ("prbs31", 31, 0x10000001, "FIBONACCI", 0, 8),
        ("scrambler_64b66b", 58, 0x8000000001, "FIBONACCI", 1, 16),
    )
    for label, width, poly, config, reverse, data_width in configurations:
        name = f"verilog_lfsr_style_{label}_w{width}_d{data_width}"
        output = aiger / f"{name}.aag"
        specialized_wrapper = derived / f"{name}_wrapper.v"
        specialize_verilog_lfsr_wrapper(config, specialized_wrapper)
        commands = [
            f"read_verilog -formal {verilog_source} "
            f"{specialized_wrapper}",
            f"chparam -set LFSR_WIDTH {width} -set LFSR_POLY {poly} "
            f"-set REVERSE {reverse} "
            f"-set DATA_WIDTH {data_width} verilog_lfsr_style_formal",
            *common_finish("verilog_lfsr_style_formal", output),
        ]
        run_yosys(commands, logs / f"{name}.log")
        models.append({
            "name": name,
            "family": "verilog_lfsr_style_equivalence",
            "category": "public-rtl-linear-datapath",
            "expected": "SAFE",
            "path": str(output),
            "params": {
                "application": label, "width": width, "data_width": data_width,
                "polynomial": hex(poly), "configuration": config, "reverse": reverse,
            },
            "source": "https://github.com/alexforencich/verilog-lfsr",
            "source_commit": git_commit(verilog_repo),
            "source_file": "rtl/lfsr.v",
            "source_sha256": sha256(verilog_source),
            "derived_wrapper_sha256": sha256(specialized_wrapper),
            "aag_sha256": sha256(output),
            "aiger": aiger_counts(output),
        })

    manifest = {
        "schema": 1,
        "description": "Public-source affine RTL converted to sequential AIGER safety models",
        "yosys": subprocess.check_output([str(YOSYS), "-V"], text=True).strip(),
        "models": models,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "output": str(out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

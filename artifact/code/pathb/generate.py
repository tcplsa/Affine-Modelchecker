#!/usr/bin/env python3
"""Path B benchmark generator CLI.

Generates deterministic, structure-controlled sequential circuits in three
formats (AAG for rIC3/MC, BLIF for the CryptoMiniSat flow, BTOR2 optional)
plus a frozen manifest with hashes and expected outcome.

Usage:
  python3 pathb/generate.py --family lfsr --width 8 --out dir/ [--seed N] ...
  python3 pathb/generate.py --family adder --width 16 --struct ripple \
        --mode accumulate --out dir/
  python3 pathb/generate.py --manifest examples.json --out dir/

The generator is a pure function of (family, params): it must NOT read any
candidate result files (preregistration discipline).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathb.netlist import Netlist  # noqa: E402
from pathb.aag_writer import to_aag_text  # noqa: E402
from pathb.blif_writer import to_blif_text  # noqa: E402
from pathb.families.lfsr import generate_lfsr, reference_check_lfsr  # noqa: E402
from pathb.families.adders import (generate_adder,  # noqa: E402
                                   reference_check_adder)
from pathb.families.shiftmix import (generate_shiftmix,  # noqa: E402
                                     reference_check_shiftmix)
from pathb.families.affine_equiv import (  # noqa: E402
    generate_affine_equiv,
    reference_check_affine_equiv,
)
from pathb.families.affine_warmup import (  # noqa: E402
    generate_affine_warmup,
    reference_check_affine_warmup,
)
from pathb.families.affine_phase_sync import (  # noqa: E402
    generate_affine_phase_sync,
    reference_check_affine_phase_sync,
)
from pathb.families.crc_equiv import (  # noqa: E402
    generate_crc_equiv,
    reference_check_crc_equiv,
)
from pathb.families.aes_linear_equiv import (  # noqa: E402
    generate_aes_linear_equiv,
    reference_check_aes_linear_equiv,
)
from pathb.families.keccak_linear_equiv import (  # noqa: E402
    generate_keccak_linear_equiv,
    reference_check_keccak_linear_equiv,
)
from pathb.families.adder_equiv import (  # noqa: E402
    generate_adder_equiv,
    reference_check_adder_equiv,
)
from pathb.families.arx_equiv import (  # noqa: E402
    generate_arx_equiv,
    reference_check_arx_equiv,
)
from pathb.families.mac_equiv import (  # noqa: E402
    generate_mac_equiv,
    reference_check_mac_equiv,
)
from pathb.families.scrambler_recovery import (  # noqa: E402
    generate_scrambler_recovery,
    reference_check_scrambler_recovery,
)
from pathb.families.crc_frame_align import (  # noqa: E402
    generate_crc_frame_align,
    reference_check_crc_frame_align,
)
from pathb.families.crc_frame_lock import (  # noqa: E402
    generate_crc_frame_lock,
    reference_check_crc_frame_lock,
)
from pathb.families.crc_frame_residue import (  # noqa: E402
    generate_crc_frame_residue,
    reference_check_crc_frame_residue,
)
from pathb.families.lfsr_jump_equiv import (  # noqa: E402
    generate_lfsr_jump_equiv,
    reference_check_lfsr_jump_equiv,
)
from pathb.families.scrambler_equiv import (  # noqa: E402
    generate_scrambler_equiv,
    reference_check_scrambler_equiv,
)
from pathb.families.syndrome_equiv import (  # noqa: E402
    generate_syndrome_equiv,
    reference_check_syndrome_equiv,
)
from pathb.families.unsafe_faults import (  # noqa: E402
    generate_crc_frame_align_unsafe,
    generate_scrambler_equiv_unsafe,
    generate_syndrome_equiv_unsafe,
    reference_check_unsafe_fault,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _xor_density(net: Netlist) -> float:
    n_xor = sum(1 for g in net.gates if g[0] == 'xor')
    n_and = sum(1 for g in net.gates if g[0] == 'and')
    denom = n_xor + n_and
    return n_xor / denom if denom else 0.0


def _bad_cone_xor_density(net: Netlist, depth=4) -> float:
    """Approximate XOR density in the bad cone (bounded backward expansion)."""
    from collections import deque
    # signals reachable backward from bad literals through gate fanins
    def _fn(sig, rev_edges, seen):
        if sig == 0 or sig in seen:
            return
        seen.add(sig)
        for f in rev_edges.get(sig, []):
            _fn(f, rev_edges, seen)

    # forward gate -> fanins
    fanins = {}
    for g in net.gates:
        kind = g[0]
        out = g[1]
        fanins[out] = (kind, g[2], g[3] if len(g) > 3 else None)
    # reverse edges
    rev = {}
    for g in net.gates:
        out = g[1]
        for f in (g[2], g[3] if len(g) > 3 else None):
            if f is not None and abs(f) > 0:
                rev.setdefault(abs(f), []).append(out)
    # seed from bad cone signals
    cone = set()
    for blit in net.bad:
        _fn(abs(blit), rev, cone)
    # also follow latch next signals backwards through gates
    for _nm, _cur, _iv, nxt in net.latches:
        _fn(abs(nxt), rev, cone)
    if not cone:
        return 0.0
    x = sum(1 for s in cone if s in fanins and fanins[s][0] == 'xor')
    a = sum(1 for s in cone if s in fanins and fanins[s][0] == 'and')
    return x / (x + a) if (x + a) else 0.0


def build_benchmark(family, params) -> dict:
    """Returns {'net': Netlist, 'expected', 'family', 'params', 'ref'}."""
    family = family.lower()
    if family == 'lfsr':
        taps = params.get('taps')
        if taps is None:
            taps = [0]
        net = generate_lfsr(
            width=params['width'],
            taps=taps,
            init=params.get('init'),
            use_bias=params.get('use_bias', False),
            seed=params.get('seed', 0),
        )
        ref = reference_check_lfsr(
            net, params['width'],
            taps=taps,
            init=params.get('init', 1),
            use_bias=params.get('use_bias', False),
            steps=params.get('ref_steps', 256),
            seed=params.get('seed', 0),
        )
        # All-zero state unreachable from nonzero init in a proper LFSR.
        expected = 'SAFE' if not ref['reached_zero'] else 'UNSAFE'
        return {'net': net, 'expected': expected, 'ref': ref}
    elif family == 'adder':
        mode = params.get('mode', 'invariant')
        struct = params.get('struct', 'ripple')
        target = params.get('target')
        net = generate_adder(
            width=params['width'],
            struct=struct,
            mode=mode,
            target=target,
            seed=params.get('seed', 0),
        )
        ref = reference_check_adder(
            params['width'], struct, mode,
            target=target,
            seed=params.get('seed', 0),
        )
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'shiftmix':
        mode = params.get('mode', 'chain')
        badbits = params.get('badbits')
        net = generate_shiftmix(
            width=params['width'],
            seed=params.get('seed', 0),
            mode=mode,
            badbits=badbits,
        )
        ref = reference_check_shiftmix(
            params['width'], mode=mode, seed=params.get('seed', 0),
            badbits=badbits)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'affine_equiv':
        net = generate_affine_equiv(
            width=params['width'],
            weight=params.get('weight', 8),
            rounds=params.get('rounds', 1),
            inputs=params.get('inputs', 4),
            topology=params.get('topology', 'balanced'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_affine_equiv()
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'affine_warmup':
        net = generate_affine_warmup(
            width=params['width'],
            weight=params.get('weight', 8),
            rounds=params.get('rounds', 2),
            delay=params.get('delay', 4),
            inputs=params.get('inputs', 4),
            topology=params.get('topology', 'balanced'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_affine_warmup(delay=params.get('delay', 4))
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'affine_phase_sync':
        net = generate_affine_phase_sync(
            width=params['width'],
            weight=params.get('weight', 9),
            rounds=params.get('rounds', 2),
            delay=params.get('delay', 3),
            inputs=params.get('inputs', 4),
            topology=params.get('topology', 'balanced'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_affine_phase_sync(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'crc_equiv':
        net = generate_crc_equiv(
            width=params['width'],
            polynomial=params['polynomial'],
            symbol_bits=params.get('symbol_bits', 8),
            updates=params.get('updates', 1),
            seed=params.get('seed', 0),
        )
        ref = reference_check_crc_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'aes_linear_equiv':
        net = generate_aes_linear_equiv(
            columns=params.get('columns', 1),
            rounds=params.get('rounds', 1),
            left_topology=params.get('left_topology', 'serial'),
            right_topology=params.get('right_topology', 'balanced'),
            input_bits=params.get('input_bits', 8),
            seed=params.get('seed', 0),
        )
        ref = reference_check_aes_linear_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'keccak_linear_equiv':
        net = generate_keccak_linear_equiv(
            lane_width=params.get('lane_width', 4),
            rounds=params.get('rounds', 1),
            left_topology=params.get('left_topology', 'serial'),
            right_topology=params.get('right_topology', 'balanced'),
            input_bits=params.get('input_bits', 8),
            seed=params.get('seed', 0),
        )
        ref = reference_check_keccak_linear_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'adder_equiv':
        net = generate_adder_equiv(
            width=params['width'],
            left_struct=params.get('left_struct', 'ripple'),
            right_struct=params.get('right_struct', 'prefix'),
            rounds=params.get('rounds', 1),
            seed=params.get('seed', 0),
        )
        ref = reference_check_adder_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'arx_equiv':
        net = generate_arx_equiv(
            primitive=params.get('primitive', 'chacha'),
            width=params['width'],
            rounds=params.get('rounds', 1),
            left_struct=params.get('left_struct', 'ripple'),
            right_struct=params.get('right_struct', 'prefix'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_arx_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'mac_equiv':
        net = generate_mac_equiv(
            width=params['width'],
            left_multiplier=params.get('left_multiplier', 'schoolbook'),
            right_multiplier=params.get('right_multiplier', 'wallace'),
            left_adder=params.get('left_adder', 'ripple'),
            right_adder=params.get('right_adder', 'prefix'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_mac_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'scrambler_recovery':
        net = generate_scrambler_recovery(
            symbol_bits=params.get('symbol_bits', 64),
            topology=params.get('topology', 'balanced'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_scrambler_recovery(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'crc_frame_align':
        net = generate_crc_frame_align(
            width=params.get('width', 32),
            polynomial=params.get('polynomial', 0x04C11DB7),
            symbol_bits=params.get('symbol_bits', 64),
            seed=params.get('seed', 0),
        )
        ref = reference_check_crc_frame_align(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'crc_frame_lock':
        net = generate_crc_frame_lock(
            width=params.get('width', 32),
            polynomial=params.get('polynomial', 0x04C11DB7),
            symbol_bits=params.get('symbol_bits', 64),
            confirm_headers=params.get('confirm_headers', 4),
            seed=params.get('seed', 0),
        )
        ref = reference_check_crc_frame_lock(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'crc_frame_residue':
        net = generate_crc_frame_residue(
            width=params.get('width', 32),
            polynomial=params.get('polynomial', 0x04C11DB7),
            symbol_bits=params.get('symbol_bits', 32),
            payload_cycles=params.get('payload_cycles', 4),
            fcs_topology=params.get('fcs_topology', 'balanced'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_crc_frame_residue(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'lfsr_jump_equiv':
        net = generate_lfsr_jump_equiv(
            width=params.get('width', 32),
            steps=params.get('steps', 64),
            taps=params.get('taps'),
            seed=params.get('seed', 0),
        )
        ref = reference_check_lfsr_jump_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'scrambler_equiv':
        net = generate_scrambler_equiv(
            symbol_bits=params.get('symbol_bits', 64),
            seed=params.get('seed', 0),
        )
        ref = reference_check_scrambler_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'syndrome_equiv':
        net = generate_syndrome_equiv(
            check_bits=params.get('check_bits', 32),
            data_bits=params.get('data_bits', 256),
            row_weight=params.get('row_weight', 17),
            seed=params.get('seed', 0),
        )
        ref = reference_check_syndrome_equiv(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'crc_frame_align_unsafe':
        net = generate_crc_frame_align_unsafe(
            width=params.get('width', 32),
            polynomial=params.get('polynomial', 0x04C11DB7),
            symbol_bits=params.get('symbol_bits', 64),
            witness_depth=params.get('witness_depth', 8),
            fault_bit=params.get('fault_bit', 0),
            seed=params.get('seed', 0),
        )
        ref = reference_check_unsafe_fault(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'scrambler_equiv_unsafe':
        net = generate_scrambler_equiv_unsafe(
            symbol_bits=params.get('symbol_bits', 64),
            witness_depth=params.get('witness_depth', 8),
            fault_bit=params.get('fault_bit', 0),
            seed=params.get('seed', 0),
        )
        ref = reference_check_unsafe_fault(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    elif family == 'syndrome_equiv_unsafe':
        net = generate_syndrome_equiv_unsafe(
            check_bits=params.get('check_bits', 32),
            data_bits=params.get('data_bits', 256),
            row_weight=params.get('row_weight', 17),
            witness_depth=params.get('witness_depth', 8),
            fault_bit=params.get('fault_bit', 0),
            seed=params.get('seed', 0),
        )
        ref = reference_check_unsafe_fault(**params)
        return {'net': net, 'expected': ref['expected'], 'ref': ref}
    raise ValueError(f"unknown family {family}")


def make_manifest(entry: dict) -> dict:
    net = entry['net']
    text_aag = to_aag_text(net)
    text_blif = to_blif_text(net)
    stats = net.stats()
    params = entry['params']
    return {
        "family": params['family'],
        "params": {k: v for k, v in params.items() if k != 'family'},
        "classification": {
            key: params[key]
            for key in ("category", "semantic", "source", "standard")
            if key in params
        },
        "expected": entry['expected'],
        "reference": entry.get('ref', {}),
        "aag_sha256": sha256_text(text_aag),
        "blif_sha256": sha256_text(text_blif),
        "aag_lines": text_aag.count("\n"),
        "blif_lines": text_blif.count("\n"),
        "stats": stats,
        "xor_density": _xor_density(net),
        "bad_cone_xor_density": _bad_cone_xor_density(net),
    }


def write_outputs(entry: dict, out_dir: str, stem: str) -> dict:
    net = entry['net']
    os.makedirs(out_dir, exist_ok=True)
    aag_path = os.path.join(out_dir, f"{stem}.aag")
    blif_path = os.path.join(out_dir, f"{stem}.blif")
    with open(aag_path, "w") as f:
        f.write(to_aag_text(net))
    with open(blif_path, "w") as f:
        f.write(to_blif_text(net))
    return {"aag": aag_path, "blif": blif_path}


def run_manifest(manifest_path, out_dir):
    with open(manifest_path) as f:
        specs = json.load(f)
    if isinstance(specs, dict):
        specs = specs.get("benchmarks", specs)
    results = []
    for spec in specs:
        fam = spec['family']
        params = dict(spec)
        params.pop('family', None)
        entry = build_benchmark(fam, {'family': fam, **params})
        entry['params'] = {'family': fam, **params}
        m = make_manifest(entry)
        metadata_keys = {"category", "semantic", "source", "standard", "notes"}
        stem_parts = (
            f'{key}{value}'
            for key, value in sorted(spec.items())
            if key != 'family' and key not in metadata_keys
        )
        stem = f"{fam}_{'_'.join(stem_parts)}"
        paths = write_outputs(entry, out_dir, stem)
        results.append({**m, "paths": paths, "stem": stem})
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


def run_single(args):
    params = {
        'family': args.family,
        'width': args.width,
        'seed': args.seed,
    }
    if args.family == 'lfsr':
        if args.taps:
            params['taps'] = [int(t) for t in args.taps.split(',')]
        if args.use_bias:
            params['use_bias'] = True
        if args.init is not None:
            params['init'] = args.init
    elif args.family == 'adder':
        params['struct'] = args.struct
        params['mode'] = args.mode
        if args.target is not None:
            params['target'] = args.target
    elif args.family == 'shiftmix':
        params['mode'] = args.smode
        if args.badbits:
            params['badbits'] = [int(b) for b in args.badbits.split(',')]
    elif args.family in ('affine_equiv', 'affine_warmup', 'affine_phase_sync'):
        params['weight'] = args.weight if args.weight is not None else (
            9 if args.family == 'affine_phase_sync' else 8
        )
        params['rounds'] = args.rounds
        params['delay'] = args.delay
        params['inputs'] = args.inputs
        params['topology'] = args.topology
    elif args.family == 'crc_equiv':
        params['polynomial'] = args.polynomial
        params['symbol_bits'] = args.symbol_bits
        params['updates'] = args.updates
    elif args.family == 'aes_linear_equiv':
        params['columns'] = args.columns
        params['rounds'] = args.rounds
        params['left_topology'] = args.left_topology
        params['right_topology'] = args.right_topology
        params['input_bits'] = args.input_bits
    elif args.family == 'keccak_linear_equiv':
        params.pop('width')
        params['lane_width'] = args.lane_width
        params['rounds'] = args.rounds
        params['left_topology'] = args.left_topology
        params['right_topology'] = args.right_topology
        params['input_bits'] = args.input_bits
    elif args.family in ('adder_equiv', 'arx_equiv'):
        params['rounds'] = args.rounds
        params['left_struct'] = args.left_struct
        params['right_struct'] = args.right_struct
        if args.family == 'arx_equiv':
            params['primitive'] = args.primitive
    elif args.family == 'mac_equiv':
        params['left_multiplier'] = args.left_multiplier
        params['right_multiplier'] = args.right_multiplier
        params['left_adder'] = args.left_struct
        params['right_adder'] = args.right_struct
    elif args.family == 'scrambler_recovery':
        params.pop('width')
        params['symbol_bits'] = args.symbol_bits
        params['topology'] = args.topology
    elif args.family in ('crc_frame_align', 'crc_frame_lock', 'crc_frame_residue'):
        params['polynomial'] = args.polynomial
        params['symbol_bits'] = args.symbol_bits
        if args.family == 'crc_frame_lock':
            params['confirm_headers'] = args.confirm_headers
        if args.family == 'crc_frame_residue':
            params['payload_cycles'] = args.payload_cycles
            params['fcs_topology'] = args.topology
    entry = build_benchmark(args.family, {'family': args.family, **params})
    entry['params'] = {'family': args.family, **params}
    m = make_manifest(entry)
    stem = f"{args.family}_w{args.width}"
    if args.family == 'adder':
        stem += f"_{args.struct}_{args.mode}"
    elif args.family == 'shiftmix':
        stem += f"_{args.smode}"
    paths = write_outputs(entry, args.out, stem)
    m['paths'] = paths
    m['stem'] = stem
    print(json.dumps(m, indent=2, default=str))
    # write manifest.json
    manifest_out = os.path.join(args.out, "manifest.json")
    if os.path.exists(manifest_out):
        with open(manifest_out) as f:
            existing = json.load(f)
    else:
        existing = []
    existing.append(m)
    with open(manifest_out, "w") as f:
        json.dump(existing, f, indent=2)


def main():
    p = argparse.ArgumentParser(description="Path B benchmark generator")
    sub = p.add_subparsers(dest="cmd")

    ps = sub.add_parser("single", help="generate one benchmark")
    ps.add_argument("--family", required=True,
                    choices=["lfsr", "adder", "shiftmix", "affine_equiv",
                             "affine_warmup", "affine_phase_sync", "crc_equiv",
                             "aes_linear_equiv", "keccak_linear_equiv",
                             "adder_equiv", "arx_equiv", "mac_equiv",
                             "scrambler_recovery", "crc_frame_align",
                             "crc_frame_lock", "crc_frame_residue",
                             "crc_frame_align_unsafe",
                             "scrambler_equiv_unsafe",
                             "syndrome_equiv_unsafe"])
    ps.add_argument("--width", type=int, required=True)
    ps.add_argument("--seed", type=int, default=0)
    ps.add_argument("--out", required=True)
    ps.add_argument("--taps", help="comma-separated LFSR tap indices")
    ps.add_argument("--use-bias", action="store_true")
    ps.add_argument("--init", type=int)
    ps.add_argument("--struct", choices=["ripple", "prefix", "carrysave"],
                    default="ripple")
    ps.add_argument("--mode", choices=["invariant", "counter"],
                    default="invariant")
    ps.add_argument("--target", type=int)
    ps.add_argument("--smode", choices=["chain", "acc"], default="chain",
                    help="shiftmix mode")
    ps.add_argument("--badbits", default=None,
                    help="comma-separated latch indices for bad (shiftmix)")
    ps.add_argument("--weight", type=int,
                    help="state variables per affine row (phase-sync requires odd)")
    ps.add_argument("--rounds", type=int, default=1,
                    help="combinational affine rounds per transition")
    ps.add_argument("--delay", type=int, default=4,
                    help="warm-up frames before affine equality is required")
    ps.add_argument("--inputs", type=int, default=4,
                    help="shared primary inputs mixed into the affine update")
    ps.add_argument("--topology", choices=["serial", "balanced"],
                    default="balanced", help="XOR reduction topology")
    ps.add_argument("--polynomial", type=lambda value: int(value, 0), default=0x1021)
    ps.add_argument("--symbol-bits", type=int, default=8)
    ps.add_argument("--confirm-headers", type=int, default=4)
    ps.add_argument("--payload-cycles", type=int, default=4)
    ps.add_argument("--updates", type=int, default=1)
    ps.add_argument("--columns", type=int, default=1)
    ps.add_argument("--lane-width", type=int, default=4)
    ps.add_argument("--input-bits", type=int, default=8)
    ps.add_argument("--left-topology", choices=["serial", "balanced"], default="serial")
    ps.add_argument("--right-topology", choices=["serial", "balanced"], default="balanced")
    ps.add_argument("--left-struct", choices=["ripple", "prefix", "carrysave"], default="ripple")
    ps.add_argument("--right-struct", choices=["ripple", "prefix", "carrysave"], default="prefix")
    ps.add_argument("--primitive", choices=["chacha", "speck"], default="chacha")
    ps.add_argument("--left-multiplier", choices=["schoolbook", "wallace"], default="schoolbook")
    ps.add_argument("--right-multiplier", choices=["schoolbook", "wallace"], default="wallace")

    pm = sub.add_parser("manifest", help="generate from a manifest JSON")
    pm.add_argument("--manifest", required=True)
    pm.add_argument("--out", required=True)

    args = p.parse_args()
    if args.cmd == "single":
        run_single(args)
    elif args.cmd == "manifest":
        run_manifest(args.manifest, args.out)
    else:
        p.print_help()


if __name__ == "__main__":
    main()

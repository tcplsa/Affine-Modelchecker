#!/usr/bin/env python3
"""Configurable, log-free benchmark runner for MC, rIC3, and custom tools."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
import shlex
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
DEFAULT_MC = ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
DEFAULT_RIC3 = Path(os.environ.get("RIC3", str(Path.home() / ".cargo" / "bin" / "ric3")))
VALID_STATUS = {"SAFE", "UNSAFE"}
_MODEL_STEM_COUNTS: Dict[str, Dict[str, int]] = {}
MC_LANE_OPTIONS = (
    ("forward_aig", "--forward-aig"),
    ("forward_compact_aig", "--forward-aig-compact"),
    ("forward_lowered_xag", "--forward-xag-lowered"),
    ("forward_xag", "--forward-xag"),
    ("forward_auto", "--forward-auto"),
    ("reverse_aig", "--reverse-aig"),
    ("reverse_compact_aig", "--reverse-aig-compact"),
    ("reverse_lowered_xag", "--reverse-xag-lowered"),
    ("reverse_xag", "--reverse-xag"),
)
MC_STAT_FIELDS = (
    "pdr_runtime", "pdr_depth", "pdr_representation", "pdr_seed", "seed_mode",
    "active_query", "portfolio_lanes", "portfolio_max_depth",
    "portfolio_sum_queries",
    "heuristic", "punishment", "pr", "earliest", "assumption_allsort",
    "mic_order", "mic_feedback_weight", "obligation_order",
    "certify_early", "certify_early_max_cube", "certify_early_min_push",
    "distance_max_depth",
    "mic_effective_order", "distance_bad_support_latches",
    "distance_reached_latches", "distance_max_observed", "distance_truncated",
    "published", "received", "imported", "rejected", "certified",
    "not_inductive", "permanent", "attempted", "early_attempted",
    "early_succeeded",
    "ctg_depth", "ctg_tries",
    "minisat_freeze_policy", "minisat_freeze_fanout",
    "preprocessor", "minisat_grow", "minisat_clause_limit", "minisat_elim_order",
    "minisat_width_weight", "minisat_translation_width_weight",
    "minisat_lift_width_weight",
    "minisat_asymm", "minisat_rcheck", "cadical_pre_rounds",
    "cadical_elimprod", "cadical_elimsum",
    "original_ands", "candidate_xors", "recognized_xors", "removed_ands", "xag_policy",
    "xag_fraction", "xag_seed", "xag_deep_fraction", "xag_min_fanout",
    "xag_allowlist", "xag_allowlist_size",
    "input_order_runtime", "conversion_runtime",
    "perturb_modes", "perturb_seed",
    "structural_gate_vars", "structural_gate_clauses",
    "encoded_gate_instances", "encoded_gate_clauses",
    "auto_choice", "auto_next_depth", "auto_recognized_xors",
    "auto_and_reduction", "auto_min_next_depth", "auto_min_and_reduction",
    "affine_next_count", "affine_next_total", "affine_rank",
    "affine_support_sum", "affine_support_max", "affine_support_avg",
    "affine_summary_enabled", "affine_summary_equations",
    "affine_summary_literals",
    "affine_island_enabled", "affine_island_replace", "affine_island_min_xors",
    "affine_island_max_support_limit", "affine_island_count",
    "affine_island_xor_nodes", "affine_island_support_sum",
    "affine_island_support_max", "affine_island_encoded_equations",
    "affine_island_encoded_literals", "affine_island_replaced_gates",
    "affine_island_validation_attempted", "affine_island_validation_passed",
    "affine_island_validation_seconds",
    "affine_guarded_enabled", "affine_guarded_controls",
    "affine_guarded_auto_enabled", "affine_guarded_auto_min_coverage",
    "affine_guarded_next_count", "affine_guarded_modes",
    "affine_guarded_support_sum", "affine_guarded_support_max",
    "affine_guarded_selection_gain", "affine_guarded_selection_next_roots",
    "affine_guarded_selection_property_roots",
    "affine_guarded_encoded_modes", "affine_guarded_guard_clauses",
    "affine_guarded_validation_attempted",
    "affine_guarded_validation_passed",
    "affine_cadical_hints", "affine_cadical_hint_equations",
    "affine_cadical_hint_clauses",
    "affine_auto_enabled", "affine_auto_choice",
    "affine_auto_cadical_max_support",
    "affine_gauss_disable_depth", "affine_gauss_disabled",
    "affine_gauss_disabled_at_depth", "affine_gauss_disabled_solvers",
    "affine_gauss_auto_gate", "affine_gauss_auto_min_depth",
    "affine_gauss_auto_min_checks", "affine_gauss_auto_max_useful_ppm",
    "affine_gauss_auto_max_avg_matrix_cells", "affine_gauss_auto_patience",
    "gauss_checks", "gauss_row_xors", "gauss_propagations",
    "gauss_conflicts", "gauss_matrices", "gauss_rows", "gauss_columns",
    "input_order", "input_order_seed",
    "queries", "inductive", "cti", "ctg", "mic", "block", "generalize",
    "extract", "pre", "propagate", "push", "unpush",
    "lemma_added", "lemma_literals", "block_lemma_added", "block_lemma_literals",
    "push_lemma_added", "push_lemma_literals",
    "frame_core", "frame_core_input_literals", "frame_core_literals",
    "lift_core", "lift_core_input_literals", "lift_core_literals",
    "translation_raw_vars", "translation_raw_clauses",
    "translation_simplified_vars", "translation_simplified_clauses",
    "translation_simplified_literals", "translation_binary_clauses",
    "translation_ternary_clauses", "translation_long_clauses",
    "translation_max_clause_size", "translation_frozen_gate_vars",
    "lift_raw_vars", "lift_raw_clauses",
    "lift_simplified_vars", "lift_simplified_clauses",
    "lift_simplified_literals", "lift_binary_clauses", "lift_ternary_clauses",
    "lift_long_clauses", "lift_max_clause_size", "lift_frozen_gate_vars",
    "translation_bve_attempted", "translation_bve_eliminated",
    "translation_bve_rejected_growth", "translation_bve_rejected_clause_limit",
    "translation_bve_removed_clauses", "translation_bve_resolvents",
    "translation_bve_resolvent_literals", "translation_bve_positive_occurrences",
    "translation_bve_negative_occurrences", "translation_bve_max_resolvent_size",
    "translation_bve_merge_checks",
    "lift_bve_attempted", "lift_bve_eliminated",
    "lift_bve_rejected_growth", "lift_bve_rejected_clause_limit",
    "lift_bve_removed_clauses", "lift_bve_resolvents",
    "lift_bve_resolvent_literals", "lift_bve_positive_occurrences",
    "lift_bve_negative_occurrences", "lift_bve_max_resolvent_size",
    "lift_bve_merge_checks",
    "frame_sat_conflicts", "frame_sat_decisions", "frame_sat_propagations",
    "frame_sat_restarts", "lift_sat_conflicts", "lift_sat_decisions",
    "lift_sat_propagations", "lift_sat_restarts", "init_sat_conflicts",
    "init_sat_decisions", "init_sat_propagations", "init_sat_restarts",
    "checker_sat_conflicts", "checker_sat_decisions",
    "checker_sat_propagations", "checker_sat_restarts",
    "translation_build", "translation_simplify", "translation_inject",
    "lift_build", "lift_simplify", "lift_inject", "bmc0_solve",
    "first_pre_solve", "first_lift_solve",
)
RIC3_STAT_FIELDS = (
    "bve_order", "bve_width_weight",
    "bve_input_clauses", "bve_input_literals",
    "bve_output_clauses", "bve_output_literals",
    "bve_attempted", "bve_eliminated", "bve_rejected_growth",
    "bve_rejected_clause_limit", "bve_removed_clauses",
    "bve_resolvents", "bve_resolvent_literals",
    "bve_positive_occurrences", "bve_negative_occurrences",
    "bve_max_resolvent_size", "bve_merge_checks", "bve_simplify_seconds",
)


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return value or "config"


def config_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no"}
    return bool(value)


def dataset_data_dir(settings: Dict[str, Any]) -> Path:
    year = str(settings.get("year", "2015"))
    return Path(
        settings.get("data_dir")
        or ROOT / "test_tools" / ("hwmcc%s" % year) / "data"
    )


def model_name(path: Path, settings: Dict[str, Any]) -> str:
    """Return a stable TSV key while preserving legacy flat-dataset names."""
    root = dataset_data_dir(settings).resolve()
    cache_key = str(root)
    counts = _MODEL_STEM_COUNTS.get(cache_key)
    if counts is None:
        counts = {}
        for candidate in list(root.rglob("*.aig")) + list(root.rglob("*.aag")):
            counts[candidate.stem] = counts.get(candidate.stem, 0) + 1
        _MODEL_STEM_COUNTS[cache_key] = counts
    if counts.get(path.stem, 0) <= 1:
        return path.stem
    try:
        relative = path.resolve().relative_to(root).with_suffix("")
    except ValueError:
        return path.stem
    return "__".join(relative.parts)


def parse_status(kind: str, output: str, exit_code: int) -> str:
    lower = output.lower()
    if kind == "mc":
        if "result: unsafe" in lower:
            return "UNSAFE"
        if "result: safe" in lower:
            return "SAFE"
        # The MC also prints the AIGER convention as a standalone final result.
        tokens = [line.strip() for line in lower.splitlines()]
        if "0" in tokens:
            return "UNSAFE"
        if "1" in tokens:
            return "SAFE"
    else:
        for line in lower.splitlines():
            token = line.strip()
            if token in {"unsat", "safe"} or token.startswith("result: safe"):
                return "SAFE"
            if token in {"sat", "unsafe"} or token.startswith("result: unsafe"):
                return "UNSAFE"
        if re.search(r"\bunsafe\b", lower):
            return "UNSAFE"
        if re.search(r"\bsafe\b", lower):
            return "SAFE"
    return "UNKNOWN" if exit_code == 0 else "ERROR"


def parse_mc_stats(output: str) -> Dict[str, str]:
    blocks: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in output.splitlines():
        if line.startswith("c PDR_STATS "):
            current = {}
            blocks.append(current)
        if current is None or not line.startswith((
            "c PDR_STATS ",
            "c PDR_CONFIG ",
            "c PDR_REPRESENTATION ",
            "c PDR_COUNTERS ",
            "c PDR_SELECTOR ",
            "c PDR_AFFINE ",
            "c CMSAT_GAUSS_TOTAL ",
            "c PDR_PHASE_TIMES ",
            "c PDR_PHASE_CNF ",
            "c PDR_PHASE_BVE ",
            "c PDR_SAT_ROLE ",
            "c PDR_SHARE ",
        )):
            continue
        for key, value in re.findall(r"([A-Za-z_]+)=([^ ]+)", line):
            if line.startswith("c PDR_AFFINE "):
                key = "affine_" + key
            elif line.startswith("c CMSAT_GAUSS_TOTAL "):
                key = "gauss_" + key
            current[key] = value
    if not blocks:
        return {}
    terminal = next(
        (block for block in blocks if block.get("result") in {"safe", "unsafe"}),
        None,
    )

    def progress_key(block: Dict[str, str]) -> Tuple[float, float]:
        def number(name: str) -> float:
            try:
                return float(block.get(name, "-1"))
            except ValueError:
                return -1.0

        return number("runtime"), number("depth")

    latest_by_thread: Dict[str, Dict[str, str]] = {}
    for block in blocks:
        thread = block.get("thread", "unknown")
        previous = latest_by_thread.get(thread)
        if previous is None or progress_key(block) > progress_key(previous):
            latest_by_thread[thread] = block
    latest_lanes = list(latest_by_thread.values())

    # A timeout portfolio has no winner.  Keep the deepest lane's final
    # snapshot, not whichever lane happened to flush last.
    chosen = terminal or max(
        latest_lanes,
        key=lambda block: (progress_key(block)[1], progress_key(block)[0]),
    )
    aliases = {
        "runtime": "pdr_runtime",
        "depth": "pdr_depth",
        "representation": "pdr_representation",
        "seed": "pdr_seed",
    }
    parsed: Dict[str, str] = {}
    parsed["portfolio_lanes"] = str(len(latest_lanes))
    parsed["portfolio_max_depth"] = str(max(
        (progress_key(block)[1] for block in latest_lanes), default=-1.0
    ))
    parsed["portfolio_sum_queries"] = str(sum(
        float(block.get("queries", "0"))
        for block in latest_lanes
        if block.get("queries", "").replace(".", "", 1).isdigit()
    ))
    for source, target in aliases.items():
        if source in chosen:
            parsed[target] = chosen[source]
    for field in MC_STAT_FIELDS:
        if field in chosen:
            parsed[field] = chosen[field]
    return parsed


def parse_ric3_stats(output: str) -> Dict[str, str]:
    aliases = {
        "order": "bve_order",
        "width_weight": "bve_width_weight",
        "input_clauses": "bve_input_clauses",
        "input_literals": "bve_input_literals",
        "output_clauses": "bve_output_clauses",
        "output_literals": "bve_output_literals",
        "attempted": "bve_attempted",
        "eliminated": "bve_eliminated",
        "rejected_growth": "bve_rejected_growth",
        "rejected_clause_limit": "bve_rejected_clause_limit",
        "removed_clauses": "bve_removed_clauses",
        "resolvents": "bve_resolvents",
        "resolvent_literals": "bve_resolvent_literals",
        "positive_occurrences": "bve_positive_occurrences",
        "negative_occurrences": "bve_negative_occurrences",
        "max_resolvent_size": "bve_max_resolvent_size",
        "merge_checks": "bve_merge_checks",
        "simplify_seconds": "bve_simplify_seconds",
    }
    parsed: Dict[str, str] = {}
    totals: Dict[str, float] = {}
    for line in output.splitlines():
        if not line.startswith("c RIC3_BVE_STATS "):
            continue
        values = dict(re.findall(r"([A-Za-z_]+)=([^ ]+)", line))
        for source, target in aliases.items():
            if source not in values:
                continue
            if target == "bve_order":
                parsed[target] = values[source]
            elif target == "bve_max_resolvent_size":
                totals[target] = max(totals.get(target, 0.0), float(values[source]))
            else:
                totals[target] = totals.get(target, 0.0) + float(values[source])
    for field, value in totals.items():
        parsed[field] = ("%.6f" % value) if field == "bve_simplify_seconds" else str(int(value))
    return parsed


def normalize_configs(raw_configs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    used: Set[str] = set()
    for index, source in enumerate(raw_configs):
        cfg = dict(source)
        kind = str(cfg.get("kind", "mc")).lower()
        if kind not in {"mc", "ric3", "custom"}:
            raise ValueError("config kind must be mc, ric3, or custom")
        label = str(cfg.get("label") or "%s %d" % (kind, index + 1)).strip()
        base = slug(str(cfg.get("id") or label))
        config_id = base
        suffix = 2
        while config_id in used:
            config_id = "%s_%d" % (base, suffix)
            suffix += 1
        used.add(config_id)
        cfg.update({"id": config_id, "label": label, "kind": kind})

        if kind == "mc":
            cfg["binary"] = str(cfg.get("binary") or DEFAULT_MC)
            cfg["seed"] = int(cfg.get("seed", 1))
            cfg["ctg_depth"] = int(cfg.get("ctg_depth", 1))
            cfg["progress_seconds"] = int(cfg.get("progress_seconds", 0))
            if cfg["ctg_depth"] < 0 or cfg["ctg_depth"] > 128:
                raise ValueError("%s.ctg_depth must be between 0 and 128" % label)
            if cfg["progress_seconds"] < 0:
                raise ValueError("%s.progress_seconds must be non-negative" % label)
            if cfg["seed"] < 0 or cfg["seed"] > 2147483647:
                raise ValueError("%s.seed must fit signed 32-bit" % label)
            for field, _option in MC_LANE_OPTIONS:
                cfg[field] = int(cfg.get(field, 0))
                if cfg[field] < 0 or cfg[field] > 128:
                    raise ValueError("%s.%s must be between 0 and 128" % (label, field))
            cfg["mode"] = str(cfg.get("mode", "aig"))
            cfg["direction"] = str(cfg.get("direction", "forward"))
            cfg["input_order"] = str(cfg.get("input_order", "original"))
            cfg["xag_policy"] = str(cfg.get("xag_policy", "all"))
            cfg["xag_fraction"] = float(cfg.get("xag_fraction", 1.0))
            cfg["xag_seed"] = int(cfg.get("xag_seed", 1))
            cfg["xag_deep_fraction"] = float(cfg.get("xag_deep_fraction", 0.5))
            cfg["xag_min_fanout"] = int(cfg.get("xag_min_fanout", 2))
            cfg["xag_allowlist"] = str(cfg.get("xag_allowlist", "")).strip()
            deterministic = cfg.get("deterministic_lanes", False)
            if isinstance(deterministic, str):
                deterministic = deterministic.lower() not in {"", "0", "false", "off", "no"}
            cfg["deterministic_lanes"] = bool(deterministic)
            for field, default in (
                ("pdr_heuristic", False),
                ("pdr_punishment", True),
                ("pdr_pr", False),
                ("pdr_earliest", True),
                ("pdr_assumption_allsort", False),
            ):
                cfg[field] = int(config_bool(cfg.get(field, default)))
            cfg["perturb_modes"] = str(cfg.get("perturb_modes", "")).strip()
            cfg["perturb_seed"] = int(cfg.get("perturb_seed", 1))
            cfg["first_pre_phase_lanes"] = str(
                cfg.get("first_pre_phase_lanes", "")
            ).strip()
            cfg["first_pre_phase_seeds"] = str(
                cfg.get("first_pre_phase_seeds", "")
            ).strip()
            cfg["predecessor_phase_lanes"] = str(
                cfg.get("predecessor_phase_lanes", "")
            ).strip()
            cfg["predecessor_phase_seeds"] = str(
                cfg.get("predecessor_phase_seeds", "")
            ).strip()
            cfg["mic_order"] = str(
                cfg.get("mic_order", "legacy")
            ).strip().lower()
            cfg["mic_order_lanes"] = str(
                cfg.get("mic_order_lanes", "")
            ).strip().lower()
            cfg["mic_feedback_weight"] = float(
                cfg.get("mic_feedback_weight", 1.0)
            )
            cfg["obligation_order"] = str(
                cfg.get("obligation_order", "legacy")
            ).strip().lower()
            cfg["obligation_order_lanes"] = str(
                cfg.get("obligation_order_lanes", "")
            ).strip().lower()
            cfg["certify_early"] = config_bool(
                cfg.get("certify_early", False)
            )
            cfg["certify_early_lanes"] = str(
                cfg.get("certify_early_lanes", "")
            ).strip().lower()
            cfg["certify_early_max_cube"] = int(
                cfg.get("certify_early_max_cube", 12)
            )
            cfg["certify_early_min_push"] = int(
                cfg.get("certify_early_min_push", 2)
            )
            cfg["distance_max_depth"] = int(
                cfg.get("distance_max_depth", 32)
            )
            cfg["minisat_freeze_policy"] = str(
                cfg.get("minisat_freeze_policy", "none")
            ).strip().lower()
            cfg["minisat_freeze_fanout"] = int(
                cfg.get("minisat_freeze_fanout", 4)
            )
            cfg["preprocessor"] = str(
                cfg.get("preprocessor", "minisat")
            ).strip().lower()
            cfg["minisat_grow"] = int(cfg.get("minisat_grow", 0))
            cfg["minisat_clause_limit"] = int(
                cfg.get("minisat_clause_limit", 20)
            )
            cfg["minisat_elim_order"] = str(
                cfg.get("minisat_elim_order", "legacy")
            ).strip().lower()
            cfg["minisat_elim_order_lanes"] = str(
                cfg.get("minisat_elim_order_lanes", "")
            ).strip().lower()
            cfg["minisat_translation_elim_order"] = str(
                cfg.get("minisat_translation_elim_order", "")
            ).strip().lower()
            cfg["minisat_lift_elim_order"] = str(
                cfg.get("minisat_lift_elim_order", "")
            ).strip().lower()
            cfg["minisat_width_weight"] = int(cfg.get("minisat_width_weight", 0))
            cfg["minisat_translation_width_weight"] = int(
                cfg.get("minisat_translation_width_weight", cfg["minisat_width_weight"])
            )
            cfg["minisat_lift_width_weight"] = int(
                cfg.get("minisat_lift_width_weight", cfg["minisat_width_weight"])
            )
            cfg["minisat_asymm"] = int(config_bool(cfg.get("minisat_asymm", False)))
            cfg["minisat_rcheck"] = int(config_bool(cfg.get("minisat_rcheck", False)))
            cfg["cadical_pre_rounds"] = int(cfg.get("cadical_pre_rounds", 3))
            cfg["cadical_elimprod"] = int(cfg.get("cadical_elimprod", 1))
            cfg["cadical_elimsum"] = int(cfg.get("cadical_elimsum", 1))
            raw_extra_env = cfg.get("extra_env", {})
            if not isinstance(raw_extra_env, dict):
                raise ValueError("%s.extra_env must be a mapping" % label)
            cfg["extra_env"] = {
                str(key): str(value)
                for key, value in raw_extra_env.items()
                if str(key)
            }
            if cfg["minisat_freeze_policy"] not in {
                "none", "all", "high-fanout", "shared", "bad", "next", "xor", "hybrid",
            }:
                raise ValueError("%s.minisat_freeze_policy is not supported" % label)
            valid_mic_orders = {
                "legacy", "distance-near", "distance-far", "feedback",
                "distance-feedback", "structure-auto",
            }
            if cfg["mic_order"] not in valid_mic_orders:
                raise ValueError("%s.mic_order is not supported" % label)
            if cfg["mic_order_lanes"]:
                lane_orders = cfg["mic_order_lanes"].split(",")
                if any(order not in valid_mic_orders for order in lane_orders):
                    raise ValueError("%s.mic_order_lanes is not supported" % label)
            if cfg["mic_feedback_weight"] < 0.0:
                raise ValueError("%s.mic_feedback_weight must be non-negative" % label)
            valid_obligation_orders = {"legacy", "source-near", "source-far"}
            if cfg["obligation_order"] not in valid_obligation_orders:
                raise ValueError("%s.obligation_order is not supported" % label)
            if cfg["obligation_order_lanes"]:
                lane_orders = cfg["obligation_order_lanes"].split(",")
                if any(order not in valid_obligation_orders for order in lane_orders):
                    raise ValueError(
                        "%s.obligation_order_lanes is not supported" % label
                    )
            if cfg["certify_early_max_cube"] < 1:
                raise ValueError("%s.certify_early_max_cube must be positive" % label)
            if cfg["certify_early_min_push"] < 0:
                raise ValueError(
                    "%s.certify_early_min_push must be non-negative" % label
                )
            if cfg["distance_max_depth"] < 0 or cfg["distance_max_depth"] > 1024:
                raise ValueError("%s.distance_max_depth must be between 0 and 1024" % label)
            if cfg["preprocessor"] not in {"minisat", "cadical"}:
                raise ValueError("%s.preprocessor must be minisat or cadical" % label)
            if cfg["minisat_elim_order"] not in {
                "legacy", "low", "high", "sum-low", "sum-high",
            }:
                raise ValueError("%s.minisat_elim_order is not supported" % label)
            if cfg["minisat_elim_order_lanes"]:
                lane_orders = cfg["minisat_elim_order_lanes"].split(",")
                if any(order not in {"legacy", "low", "high", "sum-low", "sum-high"}
                       for order in lane_orders):
                    raise ValueError("%s.minisat_elim_order_lanes is not supported" % label)
            for field in ("minisat_translation_elim_order", "minisat_lift_elim_order"):
                if cfg[field] and cfg[field] not in {
                    "legacy", "low", "high", "sum-low", "sum-high",
                }:
                    raise ValueError("%s.%s is not supported" % (label, field))
            if cfg["minisat_freeze_fanout"] < 1:
                raise ValueError("%s.minisat_freeze_fanout must be positive" % label)
            if cfg["minisat_clause_limit"] < -1:
                raise ValueError("%s.minisat_clause_limit must be -1 or non-negative" % label)
            for field in (
                "minisat_width_weight", "minisat_translation_width_weight",
                "minisat_lift_width_weight",
            ):
                if cfg[field] < 0:
                    raise ValueError("%s.%s must be non-negative" % (label, field))
            if cfg["cadical_pre_rounds"] < 0 or cfg["cadical_pre_rounds"] > 128:
                raise ValueError("%s.cadical_pre_rounds must be between 0 and 128" % label)
            if cfg["mode"] not in {"aig", "aig-compact", "xag-lowered", "xag", "auto"}:
                raise ValueError(
                    "%s.mode must be aig, aig-compact, xag-lowered, xag, or auto" % label
                )
            if cfg["direction"] not in {"forward", "reverse"}:
                raise ValueError("%s.direction must be forward or reverse" % label)
            cfg["input_order_seed"] = int(cfg.get("input_order_seed", 1))
            if cfg["input_order"] not in {
                "original", "fanout-desc", "fanout-asc", "swap", "random",
                "bad-first", "bad-last", "next-first", "next-last",
                "shared-first", "shared-last",
            }:
                raise ValueError(
                    "%s.input_order is not a supported ordering policy"
                    % label
                )
            if cfg["input_order_seed"] < 0 or cfg["input_order_seed"] > 4294967295:
                raise ValueError("%s.input_order_seed must fit unsigned 32-bit" % label)
            if cfg["xag_policy"] not in {
                "all", "next", "bad", "shared", "next-only", "bad-only",
                "cone", "deep", "shallow", "high-fanout", "low-fanout",
                "next-low-fanout", "bad-low-fanout",
                "shared-low-fanout", "cone-low-fanout", "sample",
            }:
                raise ValueError(
                    "%s.xag_policy is not supported" % label
                )
            if cfg["xag_fraction"] < 0.0 or cfg["xag_fraction"] > 1.0:
                raise ValueError("%s.xag_fraction must be between 0 and 1" % label)
            if cfg["xag_deep_fraction"] < 0.0 or cfg["xag_deep_fraction"] > 1.0:
                raise ValueError("%s.xag_deep_fraction must be between 0 and 1" % label)
            if cfg["xag_min_fanout"] < 1:
                raise ValueError("%s.xag_min_fanout must be positive" % label)
            if cfg["xag_seed"] < 0 or cfg["xag_seed"] > 4294967295:
                raise ValueError("%s.xag_seed must fit unsigned 32-bit" % label)
            allowed_perturbations = {
                "", "input", "input-swap", "input-swap-random",
                "input-fanout", "input-fanout-rev",
                "input-bad", "input-bad-rev", "input-next", "input-next-rev",
                "input-shared", "input-shared-rev",
                "latch", "gate-run", "all",
            }
            requested_perturbations = {
                item.strip() for item in cfg["perturb_modes"].split(",") if item.strip()
            }
            invalid_perturbations = requested_perturbations - allowed_perturbations
            if invalid_perturbations:
                raise ValueError(
                    "%s has invalid perturbation mode(s): %s"
                    % (label, ", ".join(sorted(invalid_perturbations)))
                )
            if cfg["perturb_seed"] < 0 or cfg["perturb_seed"] > 4294967295:
                raise ValueError("%s.perturb_seed must fit unsigned 32-bit" % label)
            cfg["preprocess_only"] = config_bool(cfg.get("preprocess_only", False))
            cfg["replicas"] = 1
        elif kind == "ric3":
            cfg["binary"] = str(cfg.get("binary") or DEFAULT_RIC3)
            cfg["engine"] = str(cfg.get("engine", "ic3"))
            cfg["aig_encoding"] = str(cfg.get("aig_encoding", "native")).lower()
            cfg["bve_width_weight"] = int(cfg.get("bve_width_weight", 0))
            if cfg["aig_encoding"] not in {"native", "aig", "xag"}:
                raise ValueError(
                    "%s.aig_encoding must be native, aig, or xag" % label
                )
            if cfg["bve_width_weight"] < 0:
                raise ValueError("%s.bve_width_weight must be non-negative" % label)
            cfg["replicas"] = int(cfg.get("replicas", 1))
            cfg["seed"] = int(cfg.get("seed", 1))
            cfg["collect_stats"] = config_bool(cfg.get("collect_stats", False))
            replica_global_args = cfg.get("replica_global_args", [])
            if isinstance(replica_global_args, str):
                replica_global_args = [
                    value.strip() for value in replica_global_args.split("|")
                ] if replica_global_args.strip() else []
            if not isinstance(replica_global_args, (list, tuple)):
                raise ValueError("%s.replica_global_args must be a list" % label)
            cfg["replica_global_args"] = [str(value).strip() for value in replica_global_args]
            replica_seeds = cfg.get("replica_seeds", [])
            if isinstance(replica_seeds, str):
                replica_seeds = [
                    value.strip() for value in replica_seeds.split(",")
                    if value.strip()
                ]
            if not isinstance(replica_seeds, (list, tuple)):
                raise ValueError("%s.replica_seeds must be a list" % label)
            cfg["replica_seeds"] = [int(value) for value in replica_seeds]
        else:
            cfg["command"] = str(cfg.get("command", "")).strip()
            if "{model}" not in cfg["command"]:
                raise ValueError("%s custom command must contain {model}" % label)
            cfg["replicas"] = int(cfg.get("replicas", 1))
            cfg["seed"] = int(cfg.get("seed", 1))
        if cfg["replicas"] < 1 or cfg["replicas"] > 128:
            raise ValueError("%s.replicas must be between 1 and 128" % label)
        if cfg.get("replica_global_args") and len(cfg["replica_global_args"]) != cfg["replicas"]:
            raise ValueError(
                "%s.replica_global_args must contain exactly one entry per replica" % label
            )
        if cfg.get("replica_seeds") and len(cfg["replica_seeds"]) != cfg["replicas"]:
            raise ValueError(
                "%s.replica_seeds must contain exactly one entry per replica" % label
            )
        if any(value < 0 or value > 2147483647 for value in cfg.get("replica_seeds", [])):
            raise ValueError("%s.replica_seeds must fit signed 32-bit" % label)
        cfg["global_args"] = str(cfg.get("global_args", "")).strip()
        cfg["extra_args"] = str(cfg.get("extra_args", "")).strip()
        configs.append(cfg)
    if not configs:
        raise ValueError("at least one comparison config is required")
    return configs


def result_header(
    configs: Iterable[Dict[str, Any]], metadata_fields: Iterable[str] = (),
) -> List[str]:
    header = [
        "name", "size_bytes", "year", "group", "winner", "outcome",
        "outcome_conflict", "benchmark_wall_seconds", "timeout_seconds",
    ]
    metadata = list(metadata_fields)
    header[4:4] = metadata
    for cfg in configs:
        prefix = cfg["id"]
        header.extend([
            "%s_status" % prefix,
            "%s_wall_seconds" % prefix,
            "%s_exit_code" % prefix,
            "%s_replica" % prefix,
        ])
        if cfg["kind"] == "mc":
            header.extend("%s_%s" % (prefix, field) for field in MC_STAT_FIELDS)
        elif cfg["kind"] == "ric3" and cfg.get("collect_stats"):
            header.extend("%s_%s" % (prefix, field) for field in RIC3_STAT_FIELDS)
    return header


def load_group_names(groups_file: Path, group: str) -> Optional[Set[str]]:
    if group == "all":
        return None
    with groups_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    try:
        return {str(name) for name in data["groups"][group]}
    except KeyError as error:
        raise ValueError("group %r is missing from %s" % (group, groups_file)) from error


def discover_models(settings: Dict[str, Any]) -> List[Path]:
    explicit_paths = settings.get("model_paths")
    if explicit_paths is not None:
        paths = [Path(path) for path in explicit_paths]
        missing = [path for path in paths if not path.exists()]
        if missing:
            raise ValueError("missing explicit model: %s" % missing[0])
        limit = int(settings.get("limit", 0))
        return paths[:limit] if limit else paths

    year = str(settings.get("year", "2015"))
    data_dir = dataset_data_dir(settings)
    groups_file = Path(settings.get("groups_file") or SCRIPT_DIR / ("hwmcc%s_groups_ric3_1800.json" % year))
    group = str(settings.get("group", "all"))
    names = load_group_names(groups_file, group)
    paths = list(data_dir.rglob("*.aig")) + list(data_dir.rglob("*.aag"))
    if names is not None:
        paths = [
            path for path in paths
            if path.stem in names or model_name(path, settings) in names
        ]
    order = str(settings.get("sort", "name"))
    if order == "size":
        paths.sort(key=lambda path: (path.stat().st_size, path.name))
    elif order == "random":
        paths.sort(key=lambda path: path.name)
        random.Random(1).shuffle(paths)
    else:
        paths.sort(key=lambda path: path.name)
    limit = int(settings.get("limit", 0))
    return paths[:limit] if limit else paths


def build_command(cfg: Dict[str, Any], model: Path, replica: int) -> List[str]:
    template_values = {
        "model": str(model),
        "name": model.stem,
        "model_key": hashlib.sha1(str(model.resolve()).encode("utf-8")).hexdigest()[:12],
        "config": cfg["id"],
        "replica": replica,
        "seed": cfg["seed"] + replica,
    }
    global_args_text = cfg.get("global_args", "")
    replica_global_args = cfg.get("replica_global_args", [])
    if replica_global_args:
        global_args_text = replica_global_args[replica]
    global_args = shlex.split(global_args_text.format(**template_values))
    extra = shlex.split(cfg.get("extra_args", "").format(**template_values))
    if cfg["kind"] == "mc":
        counts = [cfg[name] for name, _option in MC_LANE_OPTIONS]
        command = [cfg["binary"]]
        if sum(counts):
            for (_name, option), count in zip(MC_LANE_OPTIONS, counts):
                command.extend([option, str(count)])
        else:
            command.extend(["-" + cfg["mode"], "-engine", cfg["direction"]])
        return command + extra + [str(model)]
    if cfg["kind"] == "ric3":
        command = [
            cfg["binary"], "check", "--ui", "false", *global_args,
            "--aig-encoding", cfg["aig_encoding"],
            "--bve-width-weight", str(cfg["bve_width_weight"]),
            str(model), cfg["engine"],
        ]
        if "--rseed" not in extra:
            replica_seeds = cfg.get("replica_seeds", [])
            seed = replica_seeds[replica] if replica_seeds else cfg["seed"] + replica
            command.extend(["--rseed", str(seed)])
        return command + extra
    rendered = cfg["command"].format(**template_values)
    return shlex.split(rendered) + extra


class ProcessRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: Set[subprocess.Popen] = set()

    def add(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._processes.add(proc)

    def discard(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(proc)

    @staticmethod
    def terminate(proc: subprocess.Popen, grace: float = 1.0) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._processes)
        for proc in processes:
            self.terminate(proc)


class ExperimentRunner:
    """Run one experiment and stream compact rows through a callback."""

    def __init__(
        self,
        settings: Dict[str, Any],
        progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.settings = dict(settings)
        self.configs = normalize_configs(self.settings.get("configs", []))
        self.settings["configs"] = self.configs
        self.timeout = float(self.settings.get("timeout", 1800))
        self.workers = int(self.settings.get("workers", 10))
        self.mc_seed = int(self.settings.get("mc_seed", self.settings.get("sample_seed", 1)))
        if self.timeout <= 0 or self.workers <= 0 or self.workers > 512:
            raise ValueError("timeout must be positive and workers must be between 1 and 512")
        if self.mc_seed < 0 or self.mc_seed > 2147483647:
            raise ValueError("mc_seed must be between 0 and 2147483647")
        self.output = Path(self.settings["output"])
        self.model_metadata = {
            str(Path(path).resolve()): dict(metadata)
            for path, metadata in self.settings.get("model_metadata", {}).items()
        }
        self.metadata_fields = [str(field) for field in self.settings.get("metadata_fields", [])]
        reserved = {
            "name", "size_bytes", "year", "group", "winner", "outcome",
            "outcome_conflict", "benchmark_wall_seconds", "timeout_seconds",
        }
        if len(set(self.metadata_fields)) != len(self.metadata_fields):
            raise ValueError("metadata_fields must be unique")
        if reserved.intersection(self.metadata_fields):
            raise ValueError("metadata_fields collide with fixed result columns")
        self.progress = progress or (lambda _event: None)
        self.cancelled = threading.Event()
        self.registry = ProcessRegistry()
        self.write_lock = threading.Lock()
        self.header = result_header(self.configs, self.metadata_fields)

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def _run_replica(
        self,
        cfg: Dict[str, Any],
        model: Path,
        replica: int,
        decided: threading.Event,
        sibling_lock: threading.Lock,
        siblings: Set[subprocess.Popen],
    ) -> Dict[str, Any]:
        if self.cancelled.is_set() or decided.is_set():
            return {"status": "CANCELLED", "exit_code": "", "wall_seconds": 0.0, "replica": replica + 1}
        command = build_command(cfg, model, replica)
        # Keep a watchdog outside the Python runner.  If this process is killed
        # by SSH loss, OOM handling, or maintenance, the solver must not escape
        # the configured limit as an orphan.  --foreground keeps the watchdog
        # and solver in the session/process group managed by ProcessRegistry.
        watchdog_seconds = self.timeout + 10.0
        command = [
            "/usr/bin/timeout",
            "--foreground",
            "--signal=TERM",
            "--kill-after=5s",
            "%.6fs" % watchdog_seconds,
            *command,
        ]
        env = os.environ.copy()
        lane_count = sum(int(cfg.get(name, 0)) for name, _option in MC_LANE_OPTIONS)
        if cfg["kind"] == "mc":
            env["MC_PDR_STATS"] = "1"
            if cfg["preprocess_only"]:
                env["MC_PDR_PREPROCESS_ONLY"] = "1"
            else:
                env.pop("MC_PDR_PREPROCESS_ONLY", None)
            env["MC_PDR_CTG_DEPTH"] = str(cfg["ctg_depth"])
            if cfg["progress_seconds"]:
                env["MC_PDR_PROGRESS_SECONDS"] = str(cfg["progress_seconds"])
            else:
                env.pop("MC_PDR_PROGRESS_SECONDS", None)
            env["MC_PDR_HEURISTIC"] = str(cfg["pdr_heuristic"])
            env["MC_PDR_PUNISHMENT"] = str(cfg["pdr_punishment"])
            env["MC_PDR_PR"] = str(cfg["pdr_pr"])
            env["MC_PDR_EARLIEST"] = str(cfg["pdr_earliest"])
            env["MC_PDR_ASSUMPTION_ALLSORT"] = str(
                cfg["pdr_assumption_allsort"]
            )
            env["MC_PDR_MIC_ORDER"] = cfg["mic_order"]
            if cfg["mic_order_lanes"]:
                env["MC_PDR_MIC_ORDER_LANES"] = cfg["mic_order_lanes"]
            else:
                env.pop("MC_PDR_MIC_ORDER_LANES", None)
            env["MC_PDR_MIC_FEEDBACK_WEIGHT"] = str(
                cfg["mic_feedback_weight"]
            )
            env["MC_PDR_OBLIGATION_ORDER"] = cfg["obligation_order"]
            if cfg["obligation_order_lanes"]:
                env["MC_PDR_OBLIGATION_ORDER_LANES"] = \
                    cfg["obligation_order_lanes"]
            else:
                env.pop("MC_PDR_OBLIGATION_ORDER_LANES", None)
            env["MC_PDR_CERTIFY_EARLY"] = str(int(cfg["certify_early"]))
            if cfg["certify_early_lanes"]:
                env["MC_PDR_CERTIFY_EARLY_LANES"] = cfg["certify_early_lanes"]
            else:
                env.pop("MC_PDR_CERTIFY_EARLY_LANES", None)
            env["MC_PDR_CERTIFY_EARLY_MAX_CUBE"] = str(
                cfg["certify_early_max_cube"]
            )
            env["MC_PDR_CERTIFY_EARLY_MIN_PUSH"] = str(
                cfg["certify_early_min_push"]
            )
            env["MC_PDR_DISTANCE_MAX_DEPTH"] = str(cfg["distance_max_depth"])
            env["MC_PDR_MINISAT_FREEZE_POLICY"] = cfg["minisat_freeze_policy"]
            env["MC_PDR_MINISAT_FREEZE_FANOUT"] = str(cfg["minisat_freeze_fanout"])
            env["MC_PDR_PREPROCESSOR"] = cfg["preprocessor"]
            env["MC_PDR_MINISAT_GROW"] = str(cfg["minisat_grow"])
            env["MC_PDR_MINISAT_CLAUSE_LIMIT"] = str(cfg["minisat_clause_limit"])
            env["MC_PDR_MINISAT_ELIM_ORDER"] = cfg["minisat_elim_order"]
            env["MC_PDR_MINISAT_WIDTH_WEIGHT"] = str(cfg["minisat_width_weight"])
            env["MC_PDR_MINISAT_TRANSLATION_WIDTH_WEIGHT"] = \
                str(cfg["minisat_translation_width_weight"])
            env["MC_PDR_MINISAT_LIFT_WIDTH_WEIGHT"] = \
                str(cfg["minisat_lift_width_weight"])
            if cfg["minisat_elim_order_lanes"]:
                env["MC_PDR_MINISAT_ELIM_ORDER_LANES"] = cfg["minisat_elim_order_lanes"]
            else:
                env.pop("MC_PDR_MINISAT_ELIM_ORDER_LANES", None)
            if cfg["minisat_translation_elim_order"]:
                env["MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER"] = \
                    cfg["minisat_translation_elim_order"]
            else:
                env.pop("MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER", None)
            if cfg["minisat_lift_elim_order"]:
                env["MC_PDR_MINISAT_LIFT_ELIM_ORDER"] = cfg["minisat_lift_elim_order"]
            else:
                env.pop("MC_PDR_MINISAT_LIFT_ELIM_ORDER", None)
            env["MC_PDR_MINISAT_ASYMM"] = str(cfg["minisat_asymm"])
            env["MC_PDR_MINISAT_RCHECK"] = str(cfg["minisat_rcheck"])
            env["MC_PDR_CADICAL_PRE_ROUNDS"] = str(cfg["cadical_pre_rounds"])
            env["MC_PDR_CADICAL_ELIMPROD"] = str(cfg["cadical_elimprod"])
            env["MC_PDR_CADICAL_ELIMSUM"] = str(cfg["cadical_elimsum"])
            env["MC_PDR_INPUT_ORDER"] = cfg["input_order"]
            env["MC_PDR_INPUT_ORDER_SEED"] = str(cfg["input_order_seed"])
            env["MC_PDR_XAG_POLICY"] = cfg["xag_policy"]
            env["MC_PDR_XAG_FRACTION"] = str(cfg["xag_fraction"])
            env["MC_PDR_XAG_SEED"] = str(cfg["xag_seed"])
            env["MC_PDR_XAG_DEEP_FRACTION"] = str(cfg["xag_deep_fraction"])
            env["MC_PDR_XAG_MIN_FANOUT"] = str(cfg["xag_min_fanout"])
            if cfg["xag_allowlist"]:
                env["MC_PDR_XAG_ALLOWLIST_FILE"] = cfg["xag_allowlist"].format(
                    model=str(model), name=model.stem, config=cfg["id"],
                )
            else:
                env.pop("MC_PDR_XAG_ALLOWLIST_FILE", None)
            env["MC_PDR_PERTURB"] = cfg["perturb_modes"]
            env["MC_PDR_PERTURB_SEED"] = str(cfg["perturb_seed"])
            if cfg["first_pre_phase_lanes"]:
                env["MC_PDR_FIRST_PRE_PHASE_LANES"] = cfg["first_pre_phase_lanes"]
            else:
                env.pop("MC_PDR_FIRST_PRE_PHASE_LANES", None)
            if cfg["first_pre_phase_seeds"]:
                env["MC_PDR_FIRST_PRE_PHASE_SEEDS"] = cfg["first_pre_phase_seeds"]
            else:
                env.pop("MC_PDR_FIRST_PRE_PHASE_SEEDS", None)
            if cfg["predecessor_phase_lanes"]:
                env["MC_PDR_PRE_PHASE_LANES"] = cfg["predecessor_phase_lanes"]
            else:
                env.pop("MC_PDR_PRE_PHASE_LANES", None)
            if cfg["predecessor_phase_seeds"]:
                env["MC_PDR_PRE_PHASE_SEEDS"] = cfg["predecessor_phase_seeds"]
            else:
                env.pop("MC_PDR_PRE_PHASE_SEEDS", None)
            if lane_count <= 1 or cfg["deterministic_lanes"]:
                env["MC_PDR_SEED"] = str(self.mc_seed)
            else:
                env.pop("MC_PDR_SEED", None)
            env.update(cfg["extra_env"])
        elif cfg["kind"] == "ric3":
            if cfg.get("collect_stats"):
                env["RIC3_BVE_STATS"] = "1"
            else:
                env.pop("RIC3_BVE_STATS", None)
        started = time.monotonic()
        capture = tempfile.TemporaryFile(
            mode="w+t", encoding="utf-8", errors="replace"
        )
        try:
            proc = subprocess.Popen(
                command,
                # Long-running telemetry can exceed a pipe buffer.  A regular
                # temporary file keeps solver progress from blocking on I/O.
                stdout=capture,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,
                env=env,
            )
        except OSError:
            capture.close()
            return {"status": "ERROR", "exit_code": "", "wall_seconds": time.monotonic() - started, "replica": replica + 1}
        self.registry.add(proc)
        with sibling_lock:
            siblings.add(proc)
        output = ""
        status = "UNKNOWN"
        try:
            while True:
                if self.cancelled.is_set() or decided.is_set():
                    self.registry.terminate(proc)
                    status = "CANCELLED"
                    break
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    self.registry.terminate(proc)
                    status = "TIMEOUT"
                    break
                if proc.poll() is not None:
                    break
                time.sleep(min(0.5, remaining))
            if proc.poll() is None:
                proc.wait()
            capture.seek(0)
            output = capture.read()
            if status not in {"TIMEOUT", "CANCELLED"}:
                status = parse_status(cfg["kind"], output, proc.returncode)
        finally:
            self.registry.discard(proc)
            with sibling_lock:
                siblings.discard(proc)
            capture.close()
        result = {
            "status": status,
            "exit_code": proc.returncode if proc.returncode is not None else "",
            "wall_seconds": time.monotonic() - started,
            "replica": replica + 1,
        }
        if cfg["kind"] == "mc":
            result.update(parse_mc_stats(output))
            result["input_order"] = cfg["input_order"]
            result["input_order_seed"] = cfg["input_order_seed"]
        elif cfg["kind"] == "ric3" and cfg.get("collect_stats"):
            result.update(parse_ric3_stats(output))
        if status in VALID_STATUS and not decided.is_set():
            decided.set()
            with sibling_lock:
                others = list(siblings)
            for sibling in others:
                if sibling is not proc:
                    self.registry.terminate(sibling)
        return result

    def _run_config(self, cfg: Dict[str, Any], model: Path) -> Dict[str, Any]:
        started = time.monotonic()
        replicas = int(cfg.get("replicas", 1))
        decided = threading.Event()
        sibling_lock = threading.Lock()
        siblings: Set[subprocess.Popen] = set()
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=replicas) as pool:
            futures = [
                pool.submit(self._run_replica, cfg, model, replica, decided, sibling_lock, siblings)
                for replica in range(replicas)
            ]
            for future in as_completed(futures):
                results.append(future.result())
        valid = [result for result in results if result["status"] in VALID_STATUS]
        if valid:
            chosen = min(valid, key=lambda result: result["wall_seconds"])
        else:
            priority = {"TIMEOUT": 0, "ERROR": 1, "UNKNOWN": 2, "CANCELLED": 3}
            chosen = min(results, key=lambda result: priority.get(result["status"], 9))
        return dict(chosen)

    def _run_model(self, model: Path) -> Dict[str, str]:
        started = time.monotonic()
        metadata = self.model_metadata.get(str(model.resolve()), {})
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(self.configs)) as pool:
            future_to_cfg = {pool.submit(self._run_config, cfg, model): cfg for cfg in self.configs}
            for future in as_completed(future_to_cfg):
                cfg = future_to_cfg[future]
                try:
                    results[cfg["id"]] = future.result()
                except Exception:
                    results[cfg["id"]] = {
                        "status": "ERROR", "wall_seconds": time.monotonic() - started,
                        "exit_code": "", "replica": "",
                    }
        valid = [
            (cfg, results[cfg["id"]]) for cfg in self.configs
            if results[cfg["id"]]["status"] in VALID_STATUS
        ]
        winner = min(valid, key=lambda item: item[1]["wall_seconds"])[0]["label"] if valid else ""
        statuses = {result["status"] for _, result in valid}
        outcome = next(iter(statuses)) if len(statuses) == 1 else ("CONFLICT" if statuses else "UNKNOWN")
        row: Dict[str, str] = {
            "name": model_name(model, self.settings),
            "size_bytes": str(model.stat().st_size),
            "year": str(metadata.get("year", self.settings.get("year", ""))),
            "group": str(metadata.get("group", metadata.get(
                "tier", self.settings.get("group", "all")
            ))),
            "winner": winner,
            "outcome": outcome,
            "outcome_conflict": "1" if len(statuses) > 1 else "0",
            "benchmark_wall_seconds": "%.6f" % (time.monotonic() - started),
            "timeout_seconds": "%.6f" % self.timeout,
        }
        for field in self.metadata_fields:
            row[field] = str(metadata.get(field, ""))
        for cfg in self.configs:
            result = results[cfg["id"]]
            prefix = cfg["id"]
            row["%s_status" % prefix] = str(result["status"])
            row["%s_wall_seconds" % prefix] = "%.6f" % float(result["wall_seconds"])
            row["%s_exit_code" % prefix] = str(result["exit_code"])
            row["%s_replica" % prefix] = str(result["replica"])
            if cfg["kind"] == "mc":
                for field in MC_STAT_FIELDS:
                    row["%s_%s" % (prefix, field)] = str(result.get(field, ""))
            elif cfg["kind"] == "ric3" and cfg.get("collect_stats"):
                for field in RIC3_STAT_FIELDS:
                    row["%s_%s" % (prefix, field)] = str(result.get(field, ""))
        return row

    def _prepare_output(self) -> Set[str]:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        done: Set[str] = set()
        if self.output.exists() and self.output.stat().st_size:
            with self.output.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                if reader.fieldnames != self.header:
                    raise ValueError("existing output header does not match this experiment")
                if self.settings.get("skip_existing"):
                    done = {row["name"] for row in reader if row.get("name")}
        else:
            with self.output.open("w", encoding="utf-8", newline="") as handle:
                csv.DictWriter(handle, fieldnames=self.header, delimiter="\t").writeheader()
        return done

    def run(self) -> Dict[str, Any]:
        done = self._prepare_output()
        models = [
            model for model in discover_models(self.settings)
            if model_name(model, self.settings) not in done
        ]
        self.progress({"type": "started", "total": len(models), "output": str(self.output)})
        completed = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            future_to_model = {pool.submit(self._run_model, model): model for model in models}
            for future in as_completed(future_to_model):
                if self.cancelled.is_set():
                    break
                row = future.result()
                with self.write_lock:
                    with self.output.open("a", encoding="utf-8", newline="") as handle:
                        csv.DictWriter(handle, fieldnames=self.header, delimiter="\t").writerow(row)
                completed += 1
                self.progress({"type": "row", "completed": completed, "total": len(models), "row": row})
        if self.cancelled.is_set():
            self.registry.terminate_all()
        result = {"completed": completed, "total": len(models), "cancelled": self.cancelled.is_set()}
        self.progress({"type": "finished", **result})
        return result

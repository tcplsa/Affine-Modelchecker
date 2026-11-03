#!/usr/bin/env python3
"""Analyze the preregistered AIG-hard BVE domain experiment."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
MIN_INTERACTION_MATCHES = 8
CONFIGS = {
    "mc": ("mc_sumhigh4", "mc_high4", "mc_legacy4", "mc_aig4"),
    "ric3": ("ric3_sumhigh4", "ric3_high4", "ric3_legacy4", "ric3_aig4"),
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=("mc", "ric3"), required=True)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    cells: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key in cells:
                    raise ValueError(f"duplicate observation {key}")
                cells[key] = row
    return list(cells.values())


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def percentile(values: list[float], probability: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * probability
    low = int(position)
    high = min(low + 1, len(values) - 1)
    weight = position - low
    return values[low] * (1 - weight) + values[high] * weight


def cluster_ci(rows: list[dict[str, str]], candidate: str, reference: str, iterations: int) -> tuple[float, float]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if solved(row, candidate) and solved(row, reference):
            by_family[row["family"]].append(math.log(runtime(row, candidate) / runtime(row, reference)))
    families = sorted(by_family)
    if not families:
        return math.nan, math.nan
    rng = random.Random(20260812)
    samples = []
    for _ in range(iterations):
        values = [value for _ in families for value in by_family[rng.choice(families)]]
        samples.append(math.exp(statistics.mean(values)))
    return percentile(samples, 0.025), percentile(samples, 0.975)


def interaction_ci(
    rows: list[dict[str, str]], candidate: str, reference: str, iterations: int,
) -> tuple[float, float, float, int]:
    cells = {(row["match_id"], row["seed_block"], row["domain"]): row for row in rows}
    by_match: dict[str, list[float]] = defaultdict(list)
    for match_id, seed, domain in cells:
        if not match_id or domain != "aig-hard-xor-rich":
            continue
        rich = cells[(match_id, seed, domain)]
        poor = cells.get((match_id, seed, "aig-hard-xor-poor"))
        if poor is None:
            continue
        if not all(solved(row, config) for row in (rich, poor) for config in (candidate, reference)):
            continue
        by_match[match_id].append(
            math.log(runtime(rich, candidate) / runtime(rich, reference))
            - math.log(runtime(poor, candidate) / runtime(poor, reference))
        )
    matches = sorted(by_match)
    if not matches:
        return math.nan, math.nan, math.nan, 0
    observed = math.exp(statistics.mean(value for match in matches for value in by_match[match]))
    rng = random.Random(20260813)
    samples = []
    for _ in range(iterations):
        values = [value for _ in matches for value in by_match[rng.choice(matches)]]
        samples.append(math.exp(statistics.mean(values)))
    return observed, percentile(samples, 0.025), percentile(samples, 0.975), len(matches)


def stats(rows: list[dict[str, str]], candidate: str, reference: str, bootstrap: int) -> dict[str, float | int]:
    common = [row for row in rows if solved(row, candidate) and solved(row, reference)]
    informative = [row for row in rows if solved(row, candidate) or solved(row, reference)]
    ratios = [runtime(row, candidate) / runtime(row, reference) for row in common]
    penalty = lambda row, config: runtime(row, config) if solved(row, config) else 1.5 * float(row["timeout_seconds"])
    ci_low, ci_high = cluster_ci(rows, candidate, reference, bootstrap)
    candidate_sum = sum(runtime(row, candidate) for row in common)
    reference_sum = sum(runtime(row, reference) for row in common)
    return {
        "rows": len(rows),
        "candidate_solved": sum(solved(row, candidate) for row in rows),
        "reference_solved": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "summed": candidate_sum / reference_sum if reference_sum else math.nan,
        "par": (
            sum(penalty(row, candidate) for row in informative)
            / sum(penalty(row, reference) for row in informative)
        ) if informative else math.nan,
        "wins": sum(runtime(row, candidate) + 2 < runtime(row, reference) for row in common),
        "losses": sum(runtime(row, reference) + 2 < runtime(row, candidate) for row in common),
    }


def fmt(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return "-" if math.isnan(value) else f"{value:.3f}"


def add_table(
    lines: list[str], title: str, groups: list[tuple[str, list[dict[str, str]]]],
    candidate: str, reference: str, bootstrap: int,
) -> None:
    lines += [
        "", f"## {title}", "",
        "| Group | Obs | Solved C/R | Net solves | Only/lost | Common | Geo (family CI) | Summed common | PAR-1.5 | W/L >2s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, group in groups:
        value = stats(group, candidate, reference, bootstrap)
        net = int(value["candidate_solved"]) - int(value["reference_solved"])
        lines.append(
            f"| {label} | {value['rows']} | {value['candidate_solved']}/{value['reference_solved']} | "
            f"{net:+d} | {value['only']}/{value['lost']} | {value['common']} | "
            f"{fmt(value['geo'])} [{fmt(value['ci_low'])}, {fmt(value['ci_high'])}] | "
            f"{fmt(value['summed'])} | {fmt(value['par'])} | {value['wins']}/{value['losses']} |"
        )


def main() -> int:
    args = arguments()
    rows = read_rows(args.inputs)
    candidate, ablation, reference, aig_reference = CONFIGS[args.tool]
    all_hard = [("All AIG-hard", rows)]
    domains = (
        ("AIG-hard XOR-rich", [row for row in rows if row["domain"] == "aig-hard-xor-rich"]),
        ("AIG-hard XOR-poor control", [row for row in rows if row["domain"] == "aig-hard-xor-poor"]),
    )
    lines = [
        f"# Cross-year AIG-hard BVE domain: {args.tool}", "",
        f"Rows: {len(rows)}; models: {len({row['model_id'] for row in rows})}; "
        f"seed blocks: {len({row['seed_block'] for row in rows})}; outcome conflicts: "
        f"{sum(row['outcome_conflict'] == '1' for row in rows)}.", "",
        "The primary domain was frozen from a 60-second fixed-AIG baseline before XOR labels "
        "were assigned. No candidate BVE result or XOR feature participates in primary sampling. "
        "Net solved count is the primary metric.",
    ]
    add_table(
        lines, "Full method versus traditional AIG baseline",
        [*all_hard, *domains], candidate, aig_reference, args.bootstrap,
    )
    add_table(
        lines, "Isolated BVE effect: sum-high versus representation-matched legacy",
        [*all_hard, *domains], candidate, reference, args.bootstrap,
    )
    add_table(lines, "High-ID versus legacy", [*all_hard, *domains], ablation, reference, args.bootstrap)
    add_table(lines, "Sum term ablation: sum-high versus high-ID", [*all_hard, *domains], candidate, ablation, args.bootstrap)

    rich = domains[0][1]
    seeds = sorted({row["seed_block"] for row in rows})
    add_table(
        lines, "XOR-rich by seed",
        [(seed, [row for row in rich if row["seed_block"] == seed]) for seed in seeds],
        candidate, reference, min(args.bootstrap, 3000),
    )
    years = sorted({row["model_id"].split("__", 1)[0] for row in rich})
    add_table(
        lines, "XOR-rich by benchmark year",
        [(year, [row for row in rich if row["model_id"].startswith(f"{year}__")]) for year in years],
        candidate, reference, min(args.bootstrap, 3000),
    )

    all_pipeline_stats = stats(rows, candidate, aig_reference, args.bootstrap)
    all_bve_stats = stats(rows, candidate, reference, args.bootstrap)
    rich_stats = stats(rich, candidate, reference, args.bootstrap)
    poor_stats = stats(domains[1][1], candidate, reference, args.bootstrap)
    interaction, interaction_low, interaction_high, interaction_pairs = interaction_ci(
        rows, candidate, reference, args.bootstrap,
    )
    sum_interaction, sum_interaction_low, sum_interaction_high, sum_interaction_pairs = interaction_ci(
        rows, candidate, ablation, args.bootstrap,
    )
    lines += [
        "", "## Domain interaction", "",
        "The interaction is `(candidate/reference in XOR-rich) / "
        "(candidate/reference in matched XOR-poor)`. Values below one mean that the "
        "treatment is more effective in the preregistered rich domain.", "",
        "| Comparison | Matched families | Ratio of geometric effects | 95% match-cluster CI |",
        "|---|---:|---:|---:|",
        f"| Full / legacy | {interaction_pairs} | {fmt(interaction)} | "
        f"[{fmt(interaction_low)}, {fmt(interaction_high)}] |",
        f"| Full / high-ID | {sum_interaction_pairs} | {fmt(sum_interaction)} | "
        f"[{fmt(sum_interaction_low)}, {fmt(sum_interaction_high)}] |",
    ]
    lines += ["", "## Preregistered decision", ""]
    if (
        int(all_pipeline_stats["candidate_solved"]) > int(all_pipeline_stats["reference_solved"])
        and float(all_pipeline_stats["par"]) < 1.0
    ):
        lines.append("**AIG-hard application success:** the full method gains net solves and lowers PAR versus traditional AIG.")
    elif (
        int(all_pipeline_stats["candidate_solved"]) >= int(all_pipeline_stats["reference_solved"])
        and float(all_pipeline_stats["par"]) < 1.0
        and float(all_pipeline_stats["summed"]) < 1.0
    ):
        lines.append("**AIG-hard runtime success:** the full method preserves coverage and lowers PAR and common-solve cost versus traditional AIG.")
    else:
        lines.append("**AIG-hard application domain not confirmed.**")
    if (
        int(all_bve_stats["candidate_solved"]) >= int(all_bve_stats["reference_solved"])
        and float(all_bve_stats["par"]) < 1.0
    ):
        lines.append("The representation-matched comparison supports BVE order as a contributing treatment.")
    else:
        lines.append("The representation-matched comparison does not support attributing the domain gain to BVE order.")
    if (
        int(rich_stats["candidate_solved"]) > int(rich_stats["reference_solved"])
        and float(rich_stats["par"]) < 1.0
        and float(rich_stats["summed"]) < 1.0
    ):
        lines.append("**Coverage-domain success:** XOR-rich gains net solves and improves PAR and summed common runtime.")
    elif (
        int(rich_stats["candidate_solved"]) >= int(rich_stats["reference_solved"])
        and float(rich_stats["par"]) < 1.0
        and float(rich_stats["summed"]) < 1.0
        and float(rich_stats["geo"]) < 1.0
    ):
        lines.append("**Runtime-domain success:** XOR-rich is coverage-neutral and improves all three runtime metrics.")
    else:
        lines.append("**Domain not confirmed:** do not claim an AIG-hard XOR-rich advantage from this experiment.")
    if interaction_pairs < MIN_INTERACTION_MATCHES:
        lines.append(
            f"The full-versus-legacy XOR interaction is underpowered: only "
            f"{interaction_pairs} matched families contribute, below the minimum of "
            f"{MIN_INTERACTION_MATCHES}."
        )
    elif not math.isnan(interaction_high) and interaction_high < 1.0:
        lines.append("The matched interaction confirms that the XOR-rich effect is specifically stronger.")
    elif math.isnan(float(rich_stats["geo"])) or math.isnan(float(poor_stats["geo"])):
        lines.append("The XOR interaction is unavailable because too few matched pairs solved in both configurations.")
    elif float(poor_stats["geo"]) >= float(rich_stats["geo"]):
        lines.append("The point estimate is stronger in XOR-rich, but the interaction is not yet conclusive.")
    else:
        lines.append("The XOR-poor control improves more; property-cone XOR richness is not a specific domain explanation.")
    if sum_interaction_pairs < MIN_INTERACTION_MATCHES:
        lines.append(
            f"The sum-term interaction is also underpowered: only {sum_interaction_pairs} "
            "matched families contribute."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

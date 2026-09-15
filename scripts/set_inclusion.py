"""Assign each benchmark card to the core analysis set or to reference.

A card is `core` when all of these hold:
  * record_type == "benchmark" (a defined task set with a scoring rule, not a demonstration, framework or survey)
  * benchmark_features.n_tasks is reported
  * at least one metric is named (primary_metric or metric_types)
  * provenance.confidence is not "low" (i.e. not an unverified discovery-sweep stub)

Everything else becomes `reference`: it stays in the repository, keeps its extracted data, and is browsable in the
atlas, but is excluded from coverage, distance and gap analysis.

A card whose inclusion_reason begins with "manual:" is left untouched, so hand decisions survive re-runs.

Usage: python scripts/set_inclusion.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from aig.features import get_path  # noqa: E402
from ingest_extractions import Dumper  # noqa: E402

MANUAL = "manual:"


def decide(card: dict) -> tuple[str, str]:
    rt = card.get("record_type")
    n = get_path(card, "benchmark_features.n_tasks")
    metric = get_path(card, "benchmark_features.primary_metric") or get_path(card, "benchmark_features.metric_types")
    conf = get_path(card, "provenance.confidence")
    if rt != "benchmark":
        return "reference", f"record_type is {rt}: evaluation is not a reusable task set with a scoring rule"
    if conf == "low":
        return "reference", "unverified discovery-sweep stub; promote to core after full extraction"
    if n is None:
        return "reference", "no task count reported, so size and coverage cannot be compared"
    if not metric:
        return "reference", "no metric reported, so results cannot be interpreted"
    return "core", "benchmark with a reported task count, a named metric and verified extraction"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    counts = {"core": 0, "reference": 0, "manual": 0}
    for p in sorted((ROOT / "data" / "benchmarks").glob("*.yaml")):
        card = yaml.safe_load(open(p))
        reason = card.get("inclusion_reason") or ""
        if reason.startswith(MANUAL):
            counts["manual"] += 1
            counts[card.get("inclusion", "reference")] = counts.get(card.get("inclusion", "reference"), 0) + 1
            continue
        inc, why = decide(card)
        counts[inc] += 1
        if card.get("inclusion") == inc and card.get("inclusion_reason") == why:
            continue
        if a.dry_run:
            print(f"{p.name}: {card.get('inclusion')} -> {inc}")
            continue
        out = {}
        for k, v in card.items():
            out[k] = v
            if k == "record_type":
                out["inclusion"] = inc
                out["inclusion_reason"] = why
        out.setdefault("inclusion", inc)
        out.setdefault("inclusion_reason", why)
        with open(p, "w") as f:
            yaml.dump(out, f, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=110)
    print(f"core {counts['core']}, reference {counts['reference']} ({counts['manual']} manual decisions preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

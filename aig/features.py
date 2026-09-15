"""Encode benchmark cards into a flat, comparable feature table.

The encoding is deliberately simple and transparent (WP1 is infrastructure, not modelling):
  * ordinal vocabularies -> integer rank in [0, n-1], scaled to [0, 1]
  * nominal single-valued -> one-hot columns
  * nominal multi-valued  -> multi-hot columns
  * booleans             -> 0/1
  * counts               -> log10(1 + n), later min-max scaled across the table
Missing values stay None and are ignored pairwise by the Gower distance in compare.py.
"""
from __future__ import annotations

import math
from typing import Any

from .records import load_vocab

# (card path, vocab key, encoding)
ORDINAL_FIELDS = [
    ("task_features.workflow_depth", "workflow_depth"),
    ("task_features.perceptual_demand", "perceptual_demand"),
    ("task_features.reasoning_demand", "reasoning_demand"),
    ("task_features.safety_criticality", "safety_criticality"),
    ("benchmark_features.scoring_granularity", "scoring_granularity"),
]
NOMINAL_FIELDS = [
    ("benchmark_features.execution_mode", "execution_mode"),
    ("benchmark_features.task_source", "task_source"),
    ("sample_environment_features.sample_real_or_simulated", "sample_real_or_simulated"),
    ("agent_features_evaluated.rag_or_memory", "rag_or_memory"),
    ("agent_features_evaluated.planner", "planner"),
    ("agent_features_evaluated.verifier_or_self_debug", "verifier"),
    ("agent_features_evaluated.guards_or_safety_layer", "guards"),
]
MULTI_FIELDS = [
    ("benchmark_features.evaluation_target", "evaluation_target"),
    ("benchmark_features.metric_types", "metric_type"),
    ("task_features.tool_interface", "tool_interface"),
    ("sample_environment_features.novelty_levels_tested", "novelty_level"),
]
BOOL_FIELDS = [
    "benchmark_features.has_human_baseline",
    "benchmark_features.has_safety_eval",
    "benchmark_features.has_abstention_eval",
    "benchmark_features.open_source",
    "task_features.closed_loop_feedback",
    "sample_environment_features.injected_faults",
    "agent_features_evaluated.multi_agent",
    "agent_features_evaluated.deterministic_execution",
]
COUNT_FIELDS = [
    "benchmark_features.n_tasks",
    "benchmark_features.n_task_families",
    "benchmark_features.n_instances_or_runs_reported",
    "benchmark_features.n_agent_configs",
]

# Values that mean "spans several levels" and should not be forced onto the ordinal scale.
ORDINAL_WILDCARDS = {"mixed"}

# Feature groups used by the site and by group-wise distances.
GROUP_OF_PREFIX = {
    "benchmark_features": "benchmark",
    "task_features": "task",
    "sample_environment_features": "sample_environment",
    "agent_features_evaluated": "agent",
}


def get_path(card: dict[str, Any], dotted: str) -> Any:
    cur: Any = card
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def modalities(card: dict[str, Any]) -> list[str]:
    out = []
    for inst in get_path(card, "benchmark_features.instruments") or []:
        m = inst.get("modality")
        if m and m not in out:
            out.append(m)
    return out


class FeatureEncoder:
    """Builds column definitions from the vocab so encoding is reproducible."""

    def __init__(self, vocab: dict[str, Any] | None = None):
        self.vocab = vocab or load_vocab()
        self.columns: list[dict[str, Any]] = []  # {name, kind, group, weight}
        self._build()

    def _values(self, key: str) -> list[str]:
        return list(self.vocab[key]["values"].keys())

    def _group(self, path: str) -> str:
        return GROUP_OF_PREFIX.get(path.split(".")[0], "other")

    def _build(self) -> None:
        for path, key in ORDINAL_FIELDS:
            self.columns.append({"name": path, "kind": "ordinal", "group": self._group(path), "weight": 1.0})
        for path, key in NOMINAL_FIELDS:
            vals = self._values(key)
            for v in vals:
                self.columns.append({"name": f"{path}={v}", "kind": "nominal", "group": self._group(path), "weight": 1.0 / len(vals)})
        for path, key in MULTI_FIELDS:
            vals = self._values(key)
            for v in vals:
                self.columns.append({"name": f"{path}={v}", "kind": "multi", "group": self._group(path), "weight": 1.0 / len(vals)})
        for v in self._values("instrument_modality"):
            self.columns.append({"name": f"benchmark_features.instruments.modality={v}", "kind": "multi", "group": "benchmark", "weight": 1.0 / 9})
        for path in BOOL_FIELDS:
            self.columns.append({"name": path, "kind": "bool", "group": self._group(path), "weight": 1.0})
        for path in COUNT_FIELDS:
            self.columns.append({"name": path, "kind": "count", "group": self._group(path), "weight": 1.0})

    def encode(self, card: dict[str, Any]) -> dict[str, float | None]:
        row: dict[str, float | None] = {}
        for path, key in ORDINAL_FIELDS:
            v = get_path(card, path)
            vals = [x for x in self._values(key) if x not in ORDINAL_WILDCARDS]
            if v in vals and len(vals) > 1:
                row[path] = vals.index(v) / (len(vals) - 1)
            else:
                row[path] = None
        for path, key in NOMINAL_FIELDS:
            v = get_path(card, path)
            for cand in self._values(key):
                row[f"{path}={cand}"] = None if v is None else float(v == cand)
        for path, key in MULTI_FIELDS:
            v = get_path(card, path)
            for cand in self._values(key):
                row[f"{path}={cand}"] = None if v is None else float(cand in v)
        mods = modalities(card)
        for cand in self._values("instrument_modality"):
            row[f"benchmark_features.instruments.modality={cand}"] = float(cand in mods) if mods else None
        for path in BOOL_FIELDS:
            v = get_path(card, path)
            row[path] = None if v is None or v == "mixed" else float(bool(v))
        for path in COUNT_FIELDS:
            v = get_path(card, path)
            row[path] = None if v is None else math.log10(1 + float(v))
        return row

    def encode_all(self, cards: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, float | None]]]:
        rows = [self.encode(c) for c in cards]
        # min-max scale count columns so they live in [0, 1] like everything else
        for path in COUNT_FIELDS:
            vals = [r[path] for r in rows if r[path] is not None]
            if len(vals) >= 2 and max(vals) > min(vals):
                lo, hi = min(vals), max(vals)
                for r in rows:
                    if r[path] is not None:
                        r[path] = (r[path] - lo) / (hi - lo)
        return [c["name"] for c in self.columns], rows


def coverage(card: dict[str, Any]) -> dict[str, float]:
    """Fraction of schema fields that are populated (not None / empty) per feature group."""
    out: dict[str, float] = {}
    for prefix, group in GROUP_OF_PREFIX.items():
        block = card.get(prefix) or {}
        if not block:
            out[group] = 0.0
            continue
        filled = sum(1 for v in block.values() if v not in (None, [], "", {}))
        out[group] = filled / len(block)
    return out

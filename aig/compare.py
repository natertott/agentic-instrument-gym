"""Pairwise comparison of benchmark cards: Gower distance, coverage matrix, gap analysis."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .features import FeatureEncoder, GROUP_OF_PREFIX, get_path, modalities
from .records import load_vocab


def gower_distance(a: dict[str, float | None], b: dict[str, float | None], columns: list[dict[str, Any]], group: str | None = None) -> float | None:
    """Weighted Gower distance over columns with pairwise deletion of missing values.

    Returns None when the two cards share no populated column.
    """
    num = 0.0
    den = 0.0
    for col in columns:
        if group and col["group"] != group:
            continue
        x, y = a.get(col["name"]), b.get(col["name"])
        if x is None or y is None:
            continue
        w = col["weight"]
        num += w * abs(x - y)
        den += w
    return None if den == 0 else num / den


def distance_matrix(cards: list[dict[str, Any]], group: str | None = None) -> tuple[list[str], list[list[float | None]]]:
    enc = FeatureEncoder()
    _, rows = enc.encode_all(cards)
    ids = [c["id"] for c in cards]
    n = len(cards)
    mat: list[list[float | None]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = gower_distance(rows[i], rows[j], enc.columns, group)
            mat[i][j] = mat[j][i] = d
    return ids, mat


def nearest_neighbours(cards: list[dict[str, Any]], k: int = 3) -> dict[str, list[tuple[str, float]]]:
    ids, mat = distance_matrix(cards)
    out: dict[str, list[tuple[str, float]]] = {}
    for i, rid in enumerate(ids):
        cands = [(ids[j], mat[i][j]) for j in range(len(ids)) if j != i and mat[i][j] is not None]
        cands.sort(key=lambda t: t[1])
        out[rid] = cands[:k]
    return out


# Axes the proposal cares about, with a predicate deciding whether a card "covers" the axis.
AXES: list[tuple[str, str, Any]] = [
    ("physical_execution", "Actions run on real hardware", lambda c: get_path(c, "benchmark_features.execution_mode") in ("physical_instrument", "hybrid")),
    ("digital_twin", "Faithful instrument simulator", lambda c: get_path(c, "benchmark_features.execution_mode") == "digital_twin"),
    ("microscopy", "Any microscopy modality", lambda c: "microscopy" in modalities(c)),
    ("closed_loop", "Agent acts on instrument feedback", lambda c: get_path(c, "task_features.closed_loop_feedback") is True),
    ("image_interpretation", "Requires domain image interpretation", lambda c: get_path(c, "task_features.perceptual_demand") in ("image_interpretation", "mixed")),
    ("long_horizon", "Long-horizon workflows", lambda c: get_path(c, "task_features.workflow_depth") in ("long_horizon", "mixed")),
    ("quantitative_tolerance", "Scores quantitative outputs against tolerances", lambda c: bool(get_path(c, "task_features.quantitative_tolerance")) and "no" not in str(get_path(c, "task_features.quantitative_tolerance")).lower()[:3]),
    ("safety_eval", "Scores safety / prohibited actions", lambda c: get_path(c, "benchmark_features.has_safety_eval") is True),
    ("abstention_eval", "Scores abstention", lambda c: get_path(c, "benchmark_features.has_abstention_eval") is True),
    ("repetitions", "Repeated runs per task reported", lambda c: _reps(c)),
    ("family_holdout", "Holds out tasks, task families, sample classes or environments", lambda c: bool(set(get_path(c, "sample_environment_features.novelty_levels_tested") or []) & {"held_out_task", "held_out_task_family", "held_out_sample_class", "held_out_environment", "held_out_combination"})),
    ("env_state_variation", "Varies calibration / API / instrument state", lambda c: bool(get_path(c, "sample_environment_features.calibration_or_api_state_variation")) and str(get_path(c, "sample_environment_features.calibration_or_api_state_variation")).lower()[:4] not in ("none", "no ", "not ")),
    ("injected_faults", "Injects faults", lambda c: get_path(c, "sample_environment_features.injected_faults") is True),
    ("agent_ablation", "Compares more than one agent configuration beyond the base model", lambda c: (get_path(c, "benchmark_features.n_agent_configs") or 0) > len(get_path(c, "agent_features_evaluated.models") or []) or get_path(c, "agent_features_evaluated.planner") == "varied" or get_path(c, "agent_features_evaluated.verifier_or_self_debug") == "varied" or get_path(c, "agent_features_evaluated.rag_or_memory") == "varied"),
    ("human_baseline", "Reports a human baseline", lambda c: get_path(c, "benchmark_features.has_human_baseline") is True),
    ("open_source", "Tasks and harness released", lambda c: get_path(c, "benchmark_features.open_source") is True),
]


def _reps(card: dict[str, Any]) -> bool:
    r = get_path(card, "benchmark_features.repetitions_per_task")
    if r is None:
        return False
    if isinstance(r, int):
        return r > 1
    s = str(r).lower()
    return not (s.startswith("1") or s.startswith("single") or s.startswith("none") or s.startswith("no "))


def axis_coverage(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Which cards cover which axes, plus the axes nobody covers (the gaps WP3 must fill)."""
    table: dict[str, dict[str, bool]] = {}
    for card in cards:
        if card.get("record_type") not in ("benchmark", "system"):
            continue
        table[card["id"]] = {axis: bool(pred(card)) for axis, _, pred in AXES}
    counts = Counter()
    for row in table.values():
        for axis, val in row.items():
            counts[axis] += int(val)
    return {
        "axes": [{"id": a, "label": lbl, "n_covering": counts[a]} for a, lbl, _ in AXES],
        "table": table,
        "gaps": [a for a, _, _ in AXES if counts[a] == 0],
        "rare": [a for a, _, _ in AXES if 0 < counts[a] <= 2],
    }


def vocabulary_usage(cards: list[dict[str, Any]]) -> dict[str, Counter]:
    """How often each vocab value is used; values never used are candidates to drop or explain."""
    vocab = load_vocab()
    usage: dict[str, Counter] = {}
    paths = {
        "execution_mode": "benchmark_features.execution_mode",
        "task_source": "benchmark_features.task_source",
        "scoring_granularity": "benchmark_features.scoring_granularity",
        "workflow_depth": "task_features.workflow_depth",
        "perceptual_demand": "task_features.perceptual_demand",
        "reasoning_demand": "task_features.reasoning_demand",
        "safety_criticality": "task_features.safety_criticality",
        "sample_real_or_simulated": "sample_environment_features.sample_real_or_simulated",
        "planner": "agent_features_evaluated.planner",
        "rag_or_memory": "agent_features_evaluated.rag_or_memory",
        "verifier": "agent_features_evaluated.verifier_or_self_debug",
        "guards": "agent_features_evaluated.guards_or_safety_layer",
    }
    multi = {
        "evaluation_target": "benchmark_features.evaluation_target",
        "metric_type": "benchmark_features.metric_types",
        "tool_interface": "task_features.tool_interface",
        "novelty_level": "sample_environment_features.novelty_levels_tested",
    }
    for key, path in paths.items():
        usage[key] = Counter({v: 0 for v in vocab[key]["values"]})
        for c in cards:
            v = get_path(c, path)
            if v is not None:
                usage[key][v] += 1
    for key, path in multi.items():
        usage[key] = Counter({v: 0 for v in vocab[key]["values"]})
        for c in cards:
            for v in get_path(c, path) or []:
                usage[key][v] += 1
    usage["instrument_modality"] = Counter({v: 0 for v in vocab["instrument_modality"]["values"]})
    for c in cards:
        for m in modalities(c):
            usage["instrument_modality"][m] += 1
    return usage

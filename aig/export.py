"""Export site/data/*.json consumed by the static explorer in site/."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from . import SITE_DATA_DIR
from .compare import axis_coverage, distance_matrix, nearest_neighbours, vocabulary_usage
from .features import FeatureEncoder, coverage, modalities
from .records import load_cards, load_executions, load_vocab, select


def _strip(card: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in card.items() if not k.startswith("_")}


def build_site_data(out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or SITE_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = load_cards()
    cards.sort(key=lambda c: (c.get("inclusion") != "core", c.get("record_type") != "benchmark", -int(c.get("year", 0)), c.get("name", "")))
    vocab = load_vocab()
    enc = FeatureEncoder()
    columns, rows = enc.encode_all(cards)

    ids_all, mat_all = distance_matrix(cards)
    groups = {}
    for g in ("benchmark", "task", "sample_environment", "agent"):
        _, m = distance_matrix(cards, group=g)
        groups[g] = m

    payload_cards = []
    for card, row in zip(cards, rows):
        c = _strip(card)
        c["_derived"] = {
            "modalities": modalities(card),
            "coverage": coverage(card),
        }
        payload_cards.append(c)

    executions = load_executions()
    exec_summary = {}
    for r in executions:
        b = r.get("benchmark_id")
        s = exec_summary.setdefault(b, {"n_rows": 0, "n_success": 0, "n_with_success": 0})
        s["n_rows"] += 1
        if r.get("outcome", {}).get("success") is not None:
            s["n_with_success"] += 1
            s["n_success"] += int(bool(r["outcome"]["success"]))

    written = {}
    files = {
        "benchmarks.json": {"generated_on": date.today().isoformat(), "n_cards": len(cards), "cards": payload_cards},
        "vocab.json": vocab,
        "features.json": {"columns": enc.columns, "ids": [c["id"] for c in cards], "rows": rows},
        "distances.json": {"ids": ids_all, "all": mat_all, "by_group": groups, "nearest": nearest_neighbours(cards), "core_ids": [c["id"] for c in select(cards, "core")]},
        "axes.json": axis_coverage(cards, scope="all"),
        "vocab_usage.json": {k: dict(v) for k, v in vocabulary_usage(cards).items()},
        "executions_summary.json": exec_summary,
    }
    for name, obj in files.items():
        p = out_dir / name
        with open(p, "w") as f:
            json.dump(obj, f, indent=1, default=str)
        written[name] = p
    return written


def inline_into_html(html_path: Path, data_dir: Path | None = None, out_path: Path | None = None) -> Path:
    """Produce a single-file build of the explorer with all JSON inlined (for artifact publishing / offline use)."""
    data_dir = data_dir or SITE_DATA_DIR
    out_path = out_path or html_path.with_name("index.standalone.html")
    html = html_path.read_text()
    blobs = []
    for p in sorted(data_dir.glob("*.json")):
        txt = p.read_text().replace("</", "<\\/")
        blobs.append(f'<script type="application/json" id="data-{p.stem}">{txt}</script>')
    marker = "<!-- INLINE_DATA -->"
    if marker not in html:
        raise ValueError("index.html lacks the INLINE_DATA marker")
    out_path.write_text(html.replace(marker, "\n".join(blobs)))
    return out_path

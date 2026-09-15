"""Load, validate and normalise benchmark cards and execution records."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator

from . import DATA_DIR, SCHEMA_DIR


def load_vocab(path: Path | None = None) -> dict[str, Any]:
    path = path or SCHEMA_DIR / "vocab.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _iter_yaml_docs(path: Path) -> Iterable[dict[str, Any]]:
    with open(path) as f:
        for doc in yaml.safe_load_all(f):
            if doc:
                yield doc


def load_cards(directory: Path | None = None) -> list[dict[str, Any]]:
    """Load every benchmark card under data/benchmarks (one YAML file per card, or multi-doc)."""
    directory = directory or DATA_DIR / "benchmarks"
    cards: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        for doc in _iter_yaml_docs(path):
            doc.setdefault("_source_file", path.name)
            cards.append(doc)
    return cards


def load_executions(directory: Path | None = None) -> list[dict[str, Any]]:
    directory = directory or DATA_DIR / "executions"
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    for path in sorted(directory.glob("*.yaml")):
        rows.extend(_iter_yaml_docs(path))
    return rows


@dataclass
class ValidationReport:
    n_records: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (record id, message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.ok:
            return f"{self.n_records} records valid"
        lines = [f"{len(self.errors)} error(s) in {self.n_records} records:"]
        lines += [f"  [{rid}] {msg}" for rid, msg in self.errors]
        return "\n".join(lines)


def _validator(schema_name: str) -> Draft202012Validator:
    with open(SCHEMA_DIR / schema_name) as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


def validate_cards(cards: list[dict[str, Any]]) -> ValidationReport:
    v = _validator("benchmark_card.schema.json")
    report = ValidationReport(n_records=len(cards))
    seen: set[str] = set()
    for card in cards:
        rid = str(card.get("id", "<no id>"))
        clean = {k: val for k, val in card.items() if not k.startswith("_")}
        for err in sorted(v.iter_errors(clean), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            report.errors.append((rid, f"{loc}: {err.message}"))
        if rid in seen:
            report.errors.append((rid, "duplicate id"))
        seen.add(rid)
    # referential integrity of `related`
    ids = {c["id"] for c in cards if "id" in c}
    for card in cards:
        for rel in card.get("related", []) or []:
            if rel not in ids:
                report.errors.append((card.get("id", "?"), f"related id not found: {rel}"))
    return report


def validate_executions(rows: list[dict[str, Any]], cards: list[dict[str, Any]] | None = None) -> ValidationReport:
    v = _validator("execution_record.schema.json")
    report = ValidationReport(n_records=len(rows))
    card_ids = {c["id"] for c in cards} if cards else None
    for row in rows:
        rid = str(row.get("execution_id", "<no id>"))
        for err in sorted(v.iter_errors(row), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            report.errors.append((rid, f"{loc}: {err.message}"))
        if card_ids is not None and row.get("benchmark_id") not in card_ids:
            report.errors.append((rid, f"benchmark_id not found: {row.get('benchmark_id')}"))
    return report

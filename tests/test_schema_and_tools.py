import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aig.records import load_cards, load_executions, validate_cards, validate_executions, load_vocab  # noqa: E402
from aig.features import FeatureEncoder  # noqa: E402
from aig.compare import distance_matrix, axis_coverage  # noqa: E402


def test_vocab_matches_schema_enums():
    """Every enum in the benchmark card schema must be a subset of the vocab (single source of truth)."""
    vocab = load_vocab()
    schema = json.load(open(ROOT / "schema" / "benchmark_card.schema.json"))
    bf = schema["properties"]["benchmark_features"]["properties"]
    tf = schema["properties"]["task_features"]["properties"]
    assert set(schema["$defs"]["execution_mode_or_null"]["enum"]) - {None} == set(vocab["execution_mode"]["values"])
    assert set(schema["$defs"]["evaluation_target"]["enum"]) == set(vocab["evaluation_target"]["values"])
    assert set(bf["metric_types"]["items"]["enum"]) == set(vocab["metric_type"]["values"])
    assert set(tf["workflow_depth"]["enum"]) - {None} == set(vocab["workflow_depth"]["values"])
    assert set(tf["perceptual_demand"]["enum"]) - {None} == set(vocab["perceptual_demand"]["values"])
    assert set(tf["safety_criticality"]["enum"]) - {None} == set(vocab["safety_criticality"]["values"])


def test_all_cards_validate():
    cards = load_cards()
    assert cards, "no cards found under data/benchmarks"
    rep = validate_cards(cards)
    assert rep.ok, rep.summary()


def test_all_executions_validate():
    cards = load_cards()
    rows = load_executions()
    rep = validate_executions(rows, cards)
    assert rep.ok, rep.summary()


def test_encoder_is_deterministic_and_bounded():
    cards = load_cards()
    enc = FeatureEncoder()
    cols, rows = enc.encode_all(cards)
    assert len(cols) == len(enc.columns)
    for r in rows:
        for v in r.values():
            assert v is None or 0.0 <= v <= 1.0


def test_distance_matrix_symmetric_and_bounded():
    cards = [c for c in load_cards() if c.get("record_type") in ("benchmark", "system")]
    ids, m = distance_matrix(cards)
    n = len(ids)
    for i in range(n):
        assert m[i][i] == 0.0
        for j in range(n):
            assert m[i][j] == m[j][i]
            assert m[i][j] is None or 0.0 <= m[i][j] <= 1.0


def test_axis_coverage_shape():
    cov = axis_coverage(load_cards())
    assert cov["axes"] and all("n_covering" in a for a in cov["axes"])


def test_cli_validate_runs():
    r = subprocess.run([sys.executable, "-m", "aig", "validate"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

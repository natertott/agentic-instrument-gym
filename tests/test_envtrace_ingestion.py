"""Offline regression tests using three attributed release records plus mutations."""
import csv
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from aig.records import load_cards, validate_executions

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ingest_envtrace", ROOT / "scripts/ingest_envtrace_runs.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)
FIXTURE = ROOT / "tests/fixtures/envtrace/results_op_agent.csv"
BASE = "saved_named_runs/campaign/gpt-4o/20250920_130058"


def fixture_rows():
    return list(csv.DictReader(io.StringIO(FIXTURE.read_text())))


def archive(rows=None, copies=1, model="gpt-4o", stats=None):
    rows = fixture_rows() if rows is None else rows
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for run in range(copies):
            directory = BASE.replace("gpt-4o", model) + f"/run_{run}"
            z.writestr(directory + "/results_op_agent.csv", text.getvalue())
            z.writestr(directory + "/system_prompt.txt", "fixture prompt")
            if stats is not None:
                z.writestr(directory + "/run_statistics.json", json.dumps(stats))
    data.seek(0)
    return zipfile.ZipFile(data)


def test_release_fixture_maps_labels_and_preserves_unknowns():
    with archive(stats={"total_entries": 3, "correct_matches": 2}) as z:
        rows, evidence, audit = ingest.convert(z)
    report = validate_executions(rows, load_cards())
    assert report.ok, report.summary()
    assert [r["outcome"]["success"] for r in rows] == [True, True, False]
    assert [r["outcome"]["score"] for r in rows] == [float(r["full_score"]) for r in fixture_rows()]
    assert all(r["outcome"]["wall_time_s"] is None for r in rows)
    assert all(r["timestamp"] is None and r["agent"]["temperature"] is None for r in rows)
    assert evidence[0]["evaluation_path"] == "exact_code_shortcut"
    assert evidence[1]["evaluation_path"] == "trace_or_cached_trace"
    assert evidence[0]["inference_time_reported"] == fixture_rows()[0]["inference_time"]
    assert audit["imported_records"] == 3
    assert all(r["provenance"]["aggregation"] == "single_run" for r in rows)


def test_missing_label_is_not_a_failure_or_inferred_from_score():
    source = fixture_rows()
    source[0]["full_match"] = ""
    source[0]["full_score"] = ""
    with archive(source) as z:
        rows, _, audit = ingest.convert(z)
    assert rows[0]["outcome"]["success"] is None
    assert rows[0]["outcome"]["score"] is None
    assert audit["unknown_success"] == 1


def test_older_score_only_csv_is_inventoried_not_expanded():
    source = fixture_rows()
    for r in source:
        del r["full_match"]
    with archive(source) as z:
        rows, _, audit = ingest.convert(z)
    assert rows == []
    assert audit["result_files"][0]["disposition"] == "excluded_no_trial_binary_label"


def test_identical_result_files_are_collapsed_with_locator():
    with archive(copies=2) as z:
        rows, _, audit = ingest.convert(z)
    assert len(rows) == 3
    assert audit["result_files"][1]["duplicate_of"].endswith("run_0/results_op_agent.csv")


def test_debug_reference_is_excluded():
    with archive(model="debug") as z:
        rows, _, audit = ingest.convert(z)
    assert not rows
    assert audit["dispositions"] == {"excluded_debug_reference": 1}


def test_deterministic_conversion_and_reference_sensitive_task_identity():
    with archive() as z:
        first = ingest.convert(z)
        assert first == ingest.convert(z)
    source = fixture_rows()
    source[0]["expected_codes"] = '["different reference"]'
    with archive(source) as z:
        changed, _, _ = ingest.convert(z)
    assert first[0][0]["task_id"] != changed[0]["task_id"]
    assert first[0][1]["task_id"] == changed[1]["task_id"]


@pytest.mark.parametrize("field,value", [("full_match", "yes"), ("full_score", "NaN"),
                                        ("full_score", "1.01"), ("full_score", "-0.1")])
def test_invalid_outcome_rejected(field, value):
    source = fixture_rows()
    source[0][field] = value
    with archive(source) as z, pytest.raises(ValueError):
        ingest.convert(z)


def test_aggregate_is_only_used_as_consistency_check():
    with archive(stats={"total_entries": 3, "correct_matches": 1}) as z, pytest.raises(ValueError, match="success mismatch"):
        ingest.convert(z)


def test_duplicate_task_in_one_trial_rejected():
    source = fixture_rows()
    with archive(source + [source[0]]) as z, pytest.raises(ValueError, match="Duplicate task"):
        ingest.convert(z)


def test_cli_rejects_unpinned_archive_without_writing(tmp_path):
    source = tmp_path / "wrong.zip"
    source.write_bytes(b"not the released archive")
    output = tmp_path / "output"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ingest_envtrace_runs.py"),
                             str(source), "--output-root", str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "differs from pinned" in result.stderr
    assert not output.exists()


def test_committed_release_inventory_and_evidence_are_consistent():
    rows = [json.loads(line) for line in (ROOT / "data/executions/envtrace.jsonl").read_text().splitlines()]
    evidence = [json.loads(line) for line in (ROOT / "data/raw/envtrace/envtrace_evidence.jsonl").read_text().splitlines()]
    audit = json.loads((ROOT / "data/raw/envtrace/ingestion_audit.json").read_text())
    ids = [r["execution_id"] for r in rows]
    assert len(ids) == len(set(ids)) == audit["imported_records"] == 8432
    assert ids == [e["execution_id"] for e in evidence]
    assert len(audit["result_files"]) == 580
    assert sum(f["rows"] for f in audit["result_files"]) == 40072
    assert sum(f["rows"] for f in audit["result_files"] if f["disposition"] == "imported") == len(rows)
    assert len({r["task_id"] for r in rows}) == 136
    assert sum(r["outcome"]["success"] for r in rows) == audit["known_successes"] == 6464
    locators = {f["member"]: f for f in audit["result_files"] if f["disposition"] == "imported"}
    for e in evidence:
        assert e["csv_sha256"] == locators[e["member"]]["sha256"]
        assert 1 <= e["csv_record_1based"] <= locators[e["member"]]["rows"]

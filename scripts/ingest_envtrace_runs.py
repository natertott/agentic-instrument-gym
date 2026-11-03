"""Conservative, offline conversion of the pinned EnvTrace Zenodo ZIP.

Download: https://zenodo.org/records/17526264/files/EnvTrace_experiments.zip
Usage: python scripts/ingest_envtrace_runs.py /path/to/EnvTrace_experiments.zip
No released code is executed. Older score-only CSVs are inventoried, not inferred.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aig.records import load_cards, validate_executions  # noqa: E402

SOURCE = "https://zenodo.org/records/17526264"
ARCHIVE_MD5 = "61229997d75dea73f0ef2cba3a039f3f"
ARCHIVE_SIZE = 98090917
csv.field_size_limit(100_000_000)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def boolean(value: str | None) -> bool | None:
    if value in (None, "", "None", "null"):
        return None
    if value not in ("True", "False"):
        raise ValueError(f"Invalid released Boolean: {value!r}")
    return value == "True"


def score(value: str | None) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"Invalid released full_score: {value!r}")
    return number


def convert(z: zipfile.ZipFile) -> tuple[list[dict], list[dict], dict]:
    """Return records, companion evidence, and a complete result-file inventory.

    This lower-level entry point also permits tiny ZIP fixtures in offline tests.
    The CLI checks the published archive size and checksum before calling it.
    """
    records, evidence, inventory = [], [], []
    seen_files, seen_ids = {}, set()
    names = z.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Duplicate ZIP member names")
    for name in sorted(n for n in names if n.endswith("/results_op_agent.csv")):
        raw = z.read(name)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        rows = list(reader)
        item = {"member": name, "sha256": digest(raw), "rows": len(rows)}
        inventory.append(item)
        parts = PurePosixPath(name).parts
        # Do not silently reinterpret an unfamiliar release layout.
        if len(parts) < 6 or not re.fullmatch(r"run_\d+", parts[-2]):
            raise ValueError(f"Unrecognised result path: {name}")
        model, session, run = parts[-4:-1]
        campaign = "/".join(parts[1:-4])
        if model == "debug":
            item["disposition"] = "excluded_debug_reference"
            continue
        if not rows:
            item["disposition"] = "excluded_empty"
            continue
        if "full_match" not in (reader.fieldnames or []):
            item["disposition"] = "excluded_no_trial_binary_label"
            continue
        # Only collapse byte-identical files inside the SAME experimental session.
        # Same code/score in different trials is not evidence of duplication.
        key = (str(PurePosixPath(name).parent.parent), digest(raw))
        if key in seen_files:
            item.update(disposition="excluded_identical_result_file", duplicate_of=seen_files[key])
            continue
        seen_files[key] = name
        item["disposition"] = "imported"
        prompt_name = str(PurePosixPath(name).parent / "system_prompt.txt")
        prompt_hash = digest(z.read(prompt_name)) if prompt_name in names else None
        # Aggregates are QA only: never expanded into trial records.
        stats_name = str(PurePosixPath(name).parent / "run_statistics.json")
        if stats_name in names:
            stats = json.loads(z.read(stats_name))
            if stats.get("total_entries") != len(rows):
                raise ValueError(f"Trial/aggregate count mismatch: {name}")
            if all(boolean(r.get("full_match")) is not None for r in rows):
                if stats.get("correct_matches") != sum(boolean(r["full_match"]) for r in rows):
                    raise ValueError(f"Trial/aggregate success mismatch: {name}")
        commands = set()
        for index, r in enumerate(rows, 1):
            if None in r or any(v is None for v in r.values()):
                raise ValueError(f"Malformed CSV record {index}: {name}")
            command = r["command"]
            references = json.loads(r["expected_codes"])
            if not command or not isinstance(references, list) or not all(isinstance(s, str) for s in references):
                raise ValueError(f"Missing task identity: {name} record {index}")
            identity = json.dumps([command, references], ensure_ascii=False, separators=(",", ":"))
            task_id = "task-" + digest(identity.encode())
            if task_id in commands:
                raise ValueError(f"Duplicate task in trial: {name}")
            commands.add(task_id)
            execution_id = "envtrace:" + digest(f"{name}#{index}".encode())
            if execution_id in seen_ids:
                raise ValueError("Duplicate execution identifier")
            seen_ids.add(execution_id)
            complex_task = boolean(r.get("is_complex"))
            family = None if complex_task is None else ("complex" if complex_task else "simple")
            exact = boolean(r.get("exact_match"))
            pred_trace = json.loads(r["pred_pv_logs"]) if r.get("pred_pv_logs") else None
            success = boolean(r.get("full_match"))
            full_score = score(r.get("full_score"))
            records.append({
                "execution_id": execution_id, "benchmark_id": "envtrace", "task_id": task_id,
                "task_family_id": family, "repetition_index": int(run[4:]), "timestamp": None,
                "outcome": {"success": success, "score": full_score, "failure_mode": None,
                            "wall_time_s": None, "cost_usd": None, "tokens_total": None,
                            "safety_violation": None},
                "agent": {"agent_id": f"vision:{campaign}:{model}:prompt-{prompt_hash or 'unknown'}",
                          "model": model, "model_provider": None, "temperature": None,
                          "prompt_version": f"sha256:{prompt_hash}" if prompt_hash else None,
                          "rag_or_memory": "unknown", "planner": "unknown", "verifier": "unknown",
                          "guards": "unknown", "multi_agent": None, "deterministic_execution": False},
                "task": {"instrument_modality": "synchrotron", "task_family": family,
                         "tool_interface": ["python_api"], "instruction_text": command,
                         "workflow_depth": None, "reasoning_demand": None, "tolerance_rel": None},
                "sample_environment": {"sample_real_or_simulated": "none", "novelty": None},
                "benchmark": {"execution_mode": "hybrid", "metric_type": "trace_alignment",
                              "scoring_granularity": "continuous", "repetitions_designed": None,
                              "split_role": "unknown", "leakage_risk": "unknown"},
                "provenance": {"source_type": "released_logs", "aggregation": "single_run",
                               "confidence": "high", "source_ref":
                               f"{SOURCE}/files/EnvTrace_experiments.zip; {name}; CSV record {index}; "
                               f"sha256:{item['sha256']}; full_match/full_score; see envtrace_evidence.jsonl"},
            })
            evidence.append({
                "execution_id": execution_id, "member": name, "csv_record_1based": index,
                "campaign": campaign, "model_alias": model, "session_label": session,
                "csv_sha256": item["sha256"], "prompt_sha256": prompt_hash,
                "exact_match": exact, "pred_pv_event_count": len(pred_trace) if pred_trace is not None else None,
                "evaluation_path": ("exact_code_shortcut" if exact and pred_trace == [] else
                                    "trace_or_cached_trace" if pred_trace else "no_pred_trace_unknown"),
                "timing_match": boolean(r.get("timing_match")), "temp_match": boolean(r.get("temp_match")),
                "inference_time_reported": r.get("inference_time") or None,
                "expected_codes": references,
            })
    audit = {"source": SOURCE, "doi": "10.5281/zenodo.17526264", "license": "CC-BY-4.0",
             "published_archive_md5": ARCHIVE_MD5, "published_archive_bytes": ARCHIVE_SIZE,
             "result_files": inventory, "dispositions": dict(Counter(i["disposition"] for i in inventory)),
             "imported_records": len(records), "known_successes": sum(r["outcome"]["success"] is True for r in records),
             "known_failures": sum(r["outcome"]["success"] is False for r in records),
             "unknown_success": sum(r["outcome"]["success"] is None for r in records)}
    return records, evidence, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT,
                        help="Repository-shaped output directory (default: this checkout)")
    args = parser.parse_args()
    raw = args.archive.read_bytes()
    if len(raw) != ARCHIVE_SIZE or hashlib.md5(raw).hexdigest() != ARCHIVE_MD5:
        parser.error("Archive differs from pinned Zenodo release (size/MD5)")
    with zipfile.ZipFile(args.archive) as z:
        records, evidence, audit = convert(z)
    report = validate_executions(records, load_cards())
    if not report.ok:
        raise ValueError(report.summary())
    outputs = {
        "data/executions/envtrace.jsonl": "".join(json.dumps(r, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n" for r in records),
        "data/raw/envtrace/envtrace_evidence.jsonl": "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in evidence),
        "data/raw/envtrace/ingestion_audit.json": json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    }
    for path, content in outputs.items():
        target = args.output_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(report.summary())
    print(json.dumps({k: v for k, v in audit.items() if k != "result_files"}, indent=2))


if __name__ == "__main__":
    main()

"""Re-encode the released X-ray-microscopy agent benchmark run logs into execution records.

Sources (copied verbatim into data/raw/xrm_agent_benchmarks/ from
https://github.com/natertott/agentic_microscopy_benchmarks_XRM, MIT licence):
  * tests/*.yaml — the 53 benchmark tests plus 5 validation-holdout tests (id, category, tags, prompt, expected checks)
  * full_suite_optimal_configs/**/suite*.json (byte-identical duplicate copies removed) — per-test results for the selected configurations that were re-run 3x
    over the full suite and over the validation tasks (status, failures, tokens, cost, duration, agents visited, config)

Only these released suites are ingested (the full 1,949-run sweep archive is not in the public repository).
Duplicate copies of the same suite file (top-level and per-config) are collapsed on (suite_run_id, test_id).

Output: data/executions/xrm_agent_benchmarks.jsonl
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "xrm_agent_benchmarks"
OUT = ROOT / "data" / "executions" / "xrm_agent_benchmarks.jsonl"
SOURCE = "https://github.com/natertott/agentic_microscopy_benchmarks_XRM"

CHECK_TO_FAILURE = {
    "expected_tool": "tool_error", "forbidden_tool": "unsafe_action", "min_tool_calls": "hallucinated_completion",
    "expected_file": "other", "file_exists": "other", "file_content": "wrong_quantity", "expected_file_contents": "wrong_quantity",
    "output_contains": "other", "expected_agent": "planning", "max_tool_calls": "timeout", "max_llm_calls": "timeout", "max_duration": "timeout",
}


def load_tests() -> dict[str, dict]:
    tests = {}
    for p in sorted((RAW / "tests").glob("*.yaml")):
        d = yaml.safe_load(open(p)) or {}
        for t in d.get("tests", []):
            t = dict(t)
            t["_suite_file"] = p.stem
            tests[t["test_id"]] = t
    return tests


def task_block(t: dict) -> dict:
    exp = t.get("expected") or {}
    tags = list(t.get("tags") or [])
    n_tools = len(exp.get("expected_tools") or [])
    min_calls = exp.get("min_tool_calls")
    steps = max(n_tools, min_calls or 0)
    depth = "single_step" if steps <= 1 else ("multi_step" if steps <= 8 else "long_horizon")
    contents = exp.get("expected_file_contents") or {}
    tolerances = [c.get("tolerance") / c["value"] for checks in contents.values() for c in checks if isinstance(c, dict) and c.get("op") == "approx" and c.get("value")]
    quantitative = bool(tolerances)
    perceptual = "image_reading" if ("image" in tags or "segmentation" in tags or "histogram" in tags) else "structured_readout"
    reasoning = "high" if (t.get("category") in ("integration", "tdp", "validation") or "workflow" in tags) else ("medium" if quantitative or depth != "single_step" else "low")
    safety = "medium" if ("safety" in tags or "xray" in tags or "source" in tags) else "low"
    return {
        "instrument": "ZEISS Xradia Versa X-ray microscope", "instrument_modality": "microscopy",
        "task_family": t["_suite_file"], "capability_tags": [f"category:{t.get('category')}"] + tags,
        "workflow_depth": depth, "n_required_steps": steps or None,
        "perceptual_demand": perceptual, "reasoning_demand": reasoning,
        "tool_interface": ["mcp"], "n_tools_required": n_tools or None, "requires_tool_chaining": n_tools > 1,
        "has_quantitative_target": quantitative, "tolerance_rel": (min(tolerances) if tolerances else None),
        "closed_loop_feedback": True, "safety_criticality": safety, "instruction_text": t.get("user_prompt"),
    }


def agent_block(r: dict, condition: str) -> dict:
    cfg = r.get("config_snapshot") or {}
    model = (cfg.get("model") or {}).get("model")
    rag = cfg.get("rag") or {}
    ep, ctx = rag.get("episodic_top_k") or 0, rag.get("contextual_top_k") or 0
    rag_mode = "both" if ep and ctx else ("episodic" if ep else ("static_docs" if ctx else "none"))
    visited = r.get("agents_visited") or []
    n_agents = 2 if "worker" in visited or "two_agent" in condition or "two-agent" in condition or "two_agents" in condition else 1
    tools_enabled = [k for k, v in (cfg.get("tools_enabled") or {}).items() if v]
    return {
        "agent_id": f"xrm:{condition}:{model}", "model": model, "model_provider": "Anthropic" if model and "claude" in model else ("OpenAI" if model and "gpt" in model else None),
        "model_release_date": None, "vision": False, "rag_or_memory": rag_mode, "planner": "react",
        "n_tools_available": None, "tools": tools_enabled, "verifier": "none", "guards": "allowlist",
        "multi_agent": n_agents > 1, "n_agents": n_agents, "deterministic_execution": "code_execution" not in tools_enabled,
        "temperature": (cfg.get("model") or {}).get("temperature"), "prompt_version": "pruned_rag" if "pruned" in condition and "no-pruned" not in condition else None,
        "max_steps": (cfg.get("agent") or {}).get("recursion_limit"),
    }


def outcome_block(r: dict) -> dict:
    status = r.get("status")
    fails = r.get("failures") or []
    fmode = None
    if status == "timeout":
        fmode = "timeout"
    elif status == "error":
        fmode = "execution_error"
    elif status == "failed":
        names = [f.get("check_name") for f in fails if isinstance(f, dict)]
        for n in names:  # first mapped check wins; unsafe actions take priority
            if n == "forbidden_tool":
                fmode = "unsafe_action"
                break
        if fmode is None and names:
            fmode = CHECK_TO_FAILURE.get(names[0], "other")
    return {
        "success": status == "passed", "score": 1.0 if status == "passed" else 0.0, "partial_credit": None,
        "safety_violation": any(isinstance(f, dict) and f.get("check_name") == "forbidden_tool" for f in fails),
        "abstained": None, "abstention_correct": None, "failure_mode": fmode,
        "n_steps": r.get("tool_calls"), "wall_time_s": (r.get("duration_ms") or 0) / 1000 or None,
        "cost_usd": r.get("estimated_cost"), "tokens_total": r.get("total_tokens"), "quantitative_error_rel": None,
    }


def main():
    tests = load_tests()
    seen = set()
    rows = []
    for p in sorted((RAW / "full_suite_optimal_configs").rglob("suite*.json")):
        d = json.load(open(p))
        condition = p.relative_to(RAW / "full_suite_optimal_configs").parts[0]
        for pos, r in enumerate(d.get("results", [])):
            recovered = False
            if r.get("test_id") in (None, "unknown") and "validation" in condition:
                # validation suite logs record only the first test id; the five tasks run in file order
                r["test_id"] = f"validation_{pos + 1:03d}"
                recovered = True
            key = (d.get("suite_run_id"), r.get("test_id"))
            if key in seen:
                continue
            seen.add(key)
            t = tests.get(r["test_id"])
            if t is None:
                continue
            is_holdout = t["_suite_file"] == "validation_holdout"
            rows.append({
                "execution_id": f"xrm:{d.get('suite_run_id')}:{r['test_id']}",
                "benchmark_id": "xrm_agent_benchmarks", "task_id": r["test_id"], "task_family_id": t["_suite_file"],
                "repetition_index": None, "timestamp": r.get("start_time"),
                "outcome": outcome_block(r), "agent": agent_block(r, condition), "task": task_block(t),
                "sample_environment": {
                    "sample_id": None, "material_class": "additively manufactured test artefact", "form_factor": "3D-printed lattice / mounted specimen",
                    "sample_real_or_simulated": None, "signal_quality": "unknown", "snr": None,
                    "novelty": "held_out_task" if is_holdout else "seen_in_development",
                    "calibration_state": "unknown", "api_state": "nominal", "injected_fault": None, "facility_or_site": "Carl Zeiss Research Microscopy Solutions",
                },
                "benchmark": {
                    "execution_mode": "physical_instrument", "metric_type": "success_rate", "scoring_granularity": "binary",
                    "repetitions_designed": 3, "split_role": "holdout_task" if is_holdout else "test", "leakage_risk": "low",
                },
                "provenance": {
                    "source_type": "released_logs", "source_ref": f"{SOURCE} full_suite_optimal_configs/{p.relative_to(RAW / 'full_suite_optimal_configs')}",
                    "aggregation": "single_run", "confidence": "medium" if recovered else "high",
                },
            })
    # assign repetition indices per (condition, test) in time order
    rows.sort(key=lambda r: (r["agent"]["agent_id"], r["task_id"], r["timestamp"] or ""))
    counter: dict[tuple, int] = {}
    for r in rows:
        k = (r["agent"]["agent_id"], r["task_id"])
        r["repetition_index"] = counter.get(k, 0)
        counter[k] = r["repetition_index"] + 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} XRM execution rows to {OUT.relative_to(ROOT)} (from {len(seen)} unique suite results)")


if __name__ == "__main__":
    main()

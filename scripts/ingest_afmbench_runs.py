"""Re-encode AFMBench per-trial results into execution records.

Sources (copied verbatim into data/raw/afmbench/ from the AFMBench GitHub repository):
  * Results_raw.xlsx, sheet "Multi-Agent-Multi-Tool": 100 tasks x 4 models x 3 trials, correctness label per trial
    (YES, Y/PARTIAL, N/CODE, N/EXTRA, N/TOOL, N/AGENT) plus the task's "Require Tool" / "Require Agent" keywords.
  * Result_raw_metrices.xlsx, per-model sheets: per (task, trial) steps, tokens, cost, wall time, agent-call counts.
  * questions/question_<n>.json: task text and keywords (Operation Type, Require Tool, Require Agent, Requires).

Output: data/executions/afmbench.jsonl (one row per task x model x trial).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "afmbench"
OUT = ROOT / "data" / "executions" / "afmbench.jsonl"
SOURCE = "https://github.com/M3RG-IITD/AFMBench"

MODEL_COLS = {"GPT-4o": "gpt-4o-2024-08-06", "GPT-3.5": "gpt-3.5-turbo-0125", "Llama-3.3": "llama-3.3-70b-versatile", "Claude-3.5": "claude-3-5-sonnet-20241022"}
PROVIDER = {"gpt-4o-2024-08-06": "OpenAI", "gpt-3.5-turbo-0125": "OpenAI", "llama-3.3-70b-versatile": "Meta (via Groq)", "claude-3-5-sonnet-20241022": "Anthropic"}
METRIC_SHEET = {"gpt-4o-2024-08-06": "gpt_4o_1", "gpt-3.5-turbo-0125": "gpt-35", "llama-3.3-70b-versatile": "Llama", "claude-3-5-sonnet-20241022": "claude"}
LABEL = {
    "YES": (True, 1.0, None),
    "Y/PARTIAL": (False, 0.5, "other"),
    "N/CODE": (False, 0.0, "execution_error"),
    "N/TOOL": (False, 0.0, "tool_error"),
    "N/AGENT": (False, 0.0, "planning"),
    "N/EXTRA": (False, 0.0, "other"),
}
LABEL_NOTE = {"Y/PARTIAL": "partially correct", "N/EXTRA": "performed extra or unrequested operations"}


def load_labels() -> dict[tuple[int, str, int], str]:
    wb = openpyxl.load_workbook(RAW / "Results_raw.xlsx", read_only=True, data_only=True)
    rows = list(wb["Multi-Agent-Multi-Tool"].iter_rows(values_only=True))
    header = rows[0]
    col_model: dict[int, str] = {}
    cur = None
    for i, h in enumerate(header):
        if h in MODEL_COLS:
            cur = MODEL_COLS[h]
        if cur and 2 <= i <= 13:
            col_model[i] = cur
    labels = {}
    trial_of_col: dict[int, int] = {}
    seen: dict[str, int] = {}
    for i in sorted(col_model):
        m = col_model[i]
        seen[m] = seen.get(m, 0) + 1
        trial_of_col[i] = seen[m]
    for r in rows[1:]:
        if r[0] is None or not str(r[0]).strip().isdigit():
            continue
        q = int(str(r[0]).strip())
        for i, m in col_model.items():
            v = r[i]
            if v is None:
                continue
            labels[(q, m, trial_of_col[i])] = str(v).strip()
    return labels


def load_metrics() -> dict[tuple[int, str, int], dict]:
    wb = openpyxl.load_workbook(RAW / "Result_raw_metrices.xlsx", read_only=True, data_only=True)
    out = {}
    for model, sheet in METRIC_SHEET.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
        idx = {h: i for i, h in enumerate(hdr)}
        for r in rows[1:]:
            try:
                q = int(str(r[idx["File Name"]]).strip())
                t = int(str(r[idx["Trial No"]]).strip())
            except (ValueError, TypeError):
                continue
            def num(name):
                i = idx.get(name)
                if i is None or r[i] in (None, ""):
                    return None
                try:
                    return float(r[i])
                except ValueError:
                    return None
            agent_calls = {a: num(a) for a in ("AILA", "AFM_Handler", "Code_Executor", "Document_Retriever", "Data_Handler", "Image_Analyzer") if num(a) is not None}
            out[(q, model, t)] = {
                "n_steps": num("Total Steps"), "tokens_total": num("Total Tokens"), "cost_usd": num("Total Cost (USD)"),
                "wall_time_s": num("Total Time Taken (s)"), "agent_calls": agent_calls,
            }
    return out


def load_questions() -> dict[int, dict]:
    out = {}
    for p in (RAW / "questions").glob("question_*.json"):
        q = int(re.search(r"(\d+)", p.stem).group(1))
        d = json.load(open(p))
        kw = d["keywords"][0] if d.get("keywords") else {}
        out[q] = {"text": d["question"][0]["input"] if d.get("question") else None, **kw}
    return out


def main():
    labels, metrics, questions = load_labels(), load_metrics(), load_questions()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(OUT, "w") as f:
        for (q, model, trial), lab in sorted(labels.items()):
            success, score, fmode = LABEL.get(lab, (None, None, "other"))
            qi = questions.get(q, {})
            met = metrics.get((q, model, trial), {})
            requires = [s.strip().lower() for s in str(qi.get("Requires", "")).split(",") if s.strip() and s.strip() != "None"]
            multi_tool = qi.get("Require Tool") == "Multiple tools"
            multi_agent_req = qi.get("Require Agent") == "Multiple agents"
            tags = [f"operation:{str(qi.get('Operation Type','')).lower()}"] + [f"requires:{r}" for r in requires]
            n_steps = met.get("n_steps")
            row = {
                "execution_id": f"afmbench:q{q:03d}:{model}:t{trial}",
                "benchmark_id": "afmbench",
                "task_id": f"q{q:03d}",
                "task_family_id": str(qi.get("Operation Type", "unknown")).lower(),
                "repetition_index": trial - 1,
                "timestamp": None,
                "outcome": {
                    "success": success, "score": score, "partial_credit": score if lab == "Y/PARTIAL" else None,
                    "safety_violation": None, "abstained": None, "abstention_correct": None, "failure_mode": fmode,
                    "n_steps": int(n_steps) if n_steps is not None else None, "wall_time_s": met.get("wall_time_s"),
                    "cost_usd": met.get("cost_usd"), "tokens_total": int(met["tokens_total"]) if met.get("tokens_total") is not None else None,
                    "quantitative_error_rel": None,
                },
                "agent": {
                    "agent_id": f"aila:{model}", "model": model, "model_provider": PROVIDER[model], "model_release_date": None,
                    "vision": False, "rag_or_memory": "static_docs", "planner": "react",
                    "n_tools_available": None, "tools": ["Document_Retriever", "Code_Executor", "AFM_Handler", "Data_Handler", "Image_Analyzer"],
                    "verifier": "none", "guards": "none", "multi_agent": True, "n_agents": None,
                    "deterministic_execution": False, "temperature": 0.0, "prompt_version": None, "max_steps": None,
                },
                "task": {
                    "instrument": "Atomic force microscope (AILA test bed)", "instrument_modality": "microscopy",
                    "task_family": str(qi.get("Operation Type")), "capability_tags": tags,
                    "workflow_depth": "multi_step" if (multi_tool or multi_agent_req) else "single_step", "n_required_steps": None,
                    "perceptual_demand": "image_reading" if "analysis" in requires else "structured_readout",
                    "reasoning_demand": "high" if qi.get("Operation Type") == "Advanced" else "low",
                    "tool_interface": ["python_api"], "n_tools_required": 2 if multi_tool else 1, "requires_tool_chaining": multi_tool,
                    "has_quantitative_target": "calculation" in requires, "tolerance_rel": None, "closed_loop_feedback": True,
                    "safety_criticality": None, "instruction_text": qi.get("text"),
                },
                "sample_environment": {
                    "sample_id": None, "material_class": None, "form_factor": None, "sample_real_or_simulated": "real",
                    "signal_quality": "unknown", "snr": None, "novelty": None, "calibration_state": "unknown", "api_state": "nominal",
                    "injected_fault": None, "facility_or_site": None,
                },
                "benchmark": {
                    "execution_mode": "physical_instrument", "metric_type": "success_rate", "scoring_granularity": "partial",
                    "repetitions_designed": 3, "split_role": "test", "leakage_risk": "low",
                },
                "provenance": {
                    "source_type": "released_logs", "source_ref": f"{SOURCE} Results_raw.xlsx[Multi-Agent-Multi-Tool] + Result_raw_metrices.xlsx[{METRIC_SHEET[model]}]; label {lab}" + (f" ({LABEL_NOTE[lab]})" if lab in LABEL_NOTE else ""),
                    "aggregation": "single_run", "confidence": "high" if met else "medium",
                },
            }
            f.write(json.dumps(row) + "\n")
            n += 1
    print(f"wrote {n} AFMBench execution rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

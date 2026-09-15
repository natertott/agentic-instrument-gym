"""Normalise raw LLM-assisted extractions into benchmark cards.

Usage: python scripts/ingest_extractions.py [--batch data/raw/extractions_2026-09-14] [--overwrite]

Existing cards under data/benchmarks are NOT overwritten unless --overwrite is given, so hand edits survive re-runs.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aig.records import load_vocab  # noqa: E402

VOCAB = load_vocab()
EXTRACTED_ON = "2026-09-14"

# raw id -> canonical id. Several extractors covered the same paper; the first listed raw id is the primary source.
ALIASES = {
    "labosbench": "labosbench", "labosbench_2026": "labosbench",
    "afmbench_aila": "afmbench", "afmbench_2025": "afmbench",
    "johnson2026_agentic_xrm_benchmarks": "xrm_agent_benchmarks", "xrm_agent_benchmarks_johnson2026": "xrm_agent_benchmarks",
    "johnson_abshire_2026_microscopy_agent_benchmarks": "xrm_agent_benchmarks",
    "johnson2025_mm_llm_versa_xrm": "llm_xrm_2025", "xrm_llm_mm2025_johnson": "llm_xrm_2025",
    "eaa_experiment_automation_agents": "experiment_automation_agents", "eaa_du2026": "experiment_automation_agents",
    "spm_bench_xiao2026": "spm_bench", "spm_bench": "spm_bench",
    "sciraplicate_bench": "scireplicate_bench",
    "microbench_lozano2024": "micro_bench", "microvqa_burgess2025": "microvqa", "macbench_alampara2025": "macbench", "mmsci_li2024": "mmsci",
    "volk_abolhasani_2024_sdl_performance_metrics": "sdl_performance_metrics", "adesiji_2026_benchmarking_sdls": "benchmarking_sdls",
    "canty_abolhasani_2026_sdl_review": "sdl_review_2026", "leong_2025_safe_sdls": "safe_sdls", "agentabstain_2026": "agentabstain",
    "zhang_2026_agent_generalizability_survey": "agent_generalizability_survey", "labsafety_bench_2024": "labsafety_bench",
    "scisafeeval_2024": "scisafeeval", "zhou_2026_lost_in_benchmarks_irt": "lost_in_benchmarks_irt", "jiang_2026_trust_irt": "trust_irt",
    "chen_2026_agentic_sdl_soft_matter_taxonomy": "agentic_sdl_soft_matter_taxonomy", "zhang_2026_safe_sdl_framework": "safe_sdl_framework",
    "tem_agent_wall2025": "tem_agent", "emseek_chen2026": "emseek", "llmicroscopilot_schloz2024": "llmicroscopilot",
    "em_copilot_fibsem_2025": "em_copilot_fibsem", "thinking_microscopes_jamali2026": "thinking_microscopes",
    "microscopygpt_choudhary2025": "microscopygpt", "plantmicro_wei2026": "plantmicro", "atomic_yang2025": "atomic_microscopy",
    "agentic_j_johanns2026": "agentic_j", "liu_vasudevan_2024_llm_spm": "llm_spm_2024", "diao_2024_llm_sns_spm": "llm_sns_spm_2024",
    "diao_2026_domain_slm_spm": "domain_slm_spm_2026", "slautin_2026_llm_hypothesis_spm": "llm_hypothesis_spm_2026",
    "schema_bound_mcp_skills_2026": "schema_bound_mcp_instrument_control", "stemgym_2026": "stemgym",
    "ai_xray_scientist_nmi2026": "ai_xray_scientist", "hellert_als_agentic_accelerator": "als_agentic_accelerator",
    "vriza_learn_on_the_job": "learn_on_the_job_agents", "autoxrd_xrdbench": "autoxrd", "labos_coscientist": "labos",
    "protoact_biop2e": "protoact", "pipette_wetlab_sim": "pipette_wetlab_sim", "experiment_automation_agents": "experiment_automation_agents",
}
# Extraction files in priority order (earlier = preferred base when duplicates exist).
PRIORITY = ["extract_E.yaml", "extract_B.yaml", "extract_C.yaml", "extract_D.yaml", "extract_F.yaml", "extract_A.yaml", "extract_G.yaml"]

RECORD_TYPE_OVERRIDES = {
    "vision": "system", "labos": "system", "experiment_automation_agents": "system", "ai_xray_scientist": "system",
    "osprey_als_bl531": "system", "als_agentic_accelerator": "system", "lightfall": "system", "learn_on_the_job_agents": "system",
    "llm_xrm_2025": "system", "tem_agent": "system", "llmicroscopilot": "system", "em_copilot_fibsem": "system",
    "thinking_microscopes": "survey", "atomic_microscopy": "system", "agentic_j": "system", "llm_spm_2024": "system",
    "llm_sns_spm_2024": "system", "domain_slm_spm_2026": "system", "llm_hypothesis_spm_2026": "system",
    "schema_bound_mcp_instrument_control": "system", "troubleshootingbench": "benchmark", "bioplanner": "benchmark",
    "biolp_bench": "benchmark", "mmsci": "benchmark", "plantmicro": "benchmark", "microscopygpt": "system",
}
EXECUTION_MODE_OVERRIDES = {
    "labosbench": "digital_twin",      # eight instrument-specific stateful GUI simulators
    "stemgym": "digital_twin",         # simulated STEM with dose physics
    "agentabstain": "simulator",       # executable MCP sandboxes
    "labsafety_bench": "static_text", "scisafeeval": "static_text",
    "benchmarking_sdls": "simulator",
    "xrm_agent_benchmarks": "physical_instrument",
    "afmbench": "physical_instrument",
    "experiment_automation_agents": "physical_instrument",
}

ENUM_FIXES = {
    "verifier_or_self_debug": {"verifier": "external_verifier", "self-debug": "self_debug"},
    "guards_or_safety_layer": {"some": "some"},
}


def load_all(batch: Path) -> dict[str, list[tuple[str, dict]]]:
    groups: dict[str, list[tuple[str, dict]]] = OrderedDict()
    for fname in PRIORITY:
        p = batch / fname
        if not p.exists():
            continue
        for doc in yaml.safe_load_all(open(p)):
            if not doc or "id" not in doc:
                continue
            cid = ALIASES.get(doc["id"], doc["id"])
            groups.setdefault(cid, []).append((fname, doc))
    return groups


def n_filled(d) -> int:
    if isinstance(d, dict):
        return sum(n_filled(v) for v in d.values())
    if isinstance(d, list):
        return sum(n_filled(v) for v in d) or 0
    return 0 if d in (None, "", "null") else 1


def merge(docs: list[tuple[str, dict]]) -> tuple[dict, list[str]]:
    docs = sorted(docs, key=lambda t: -n_filled(t[1]))
    base = yaml.safe_load(yaml.safe_dump(docs[0][1]))
    sources = [docs[0][0]]
    for fname, other in docs[1:]:
        sources.append(fname)
        for k, v in other.items():
            if k in ("id", "provenance"):
                continue
            if isinstance(v, dict):
                base.setdefault(k, {})
                for kk, vv in v.items():
                    cur = base[k].get(kk)
                    if cur in (None, [], "") and vv not in (None, [], ""):
                        base[k][kk] = vv
                    elif isinstance(cur, list) and isinstance(vv, list) and kk in ("headline_results",):
                        for item in vv:
                            if item not in cur:
                                cur.append(item)
            elif isinstance(v, list) and k in ("transfer_relevant_findings", "limitations", "related", "schema_axes_proposed"):
                base.setdefault(k, [])
                for item in v:
                    if item not in base[k]:
                        base[k].append(item)
            elif k == "notes" and v:
                base["notes"] = (base.get("notes") or "") + f"\n[{fname}] " + str(v)
            elif base.get(k) in (None, "", []) and v not in (None, "", []):
                base[k] = v
    return base, sources


def norm_execution_mode(v):
    if v is None:
        return None
    s = str(v).lower()
    if s in VOCAB["execution_mode"]["values"]:
        return s
    if "web ui" in s or "digital twin" in s:
        return "digital_twin"
    if "sandbox" in s or "simulat" in s:
        return "simulator"
    if "static" in s or "qa" in s or "prompt-response" in s:
        return "static_text"
    if "trace" in s:
        return "execution_trace"
    return "hybrid"


def norm_enum(value, key, allowed):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip()
    s = ENUM_FIXES.get(key, {}).get(s, s)
    if s in allowed:
        return s
    s2 = s.lower().replace("-", "_").replace(" ", "_")
    if s2 in allowed:
        return s2
    return None  # dropped; reported by validator diff


def normalise(card: dict, cid: str, sources: list[str]) -> dict:
    card["id"] = cid
    rt = card.get("record_type")
    bf = card.setdefault("benchmark_features", {}) or {}
    tf = card.setdefault("task_features", {}) or {}
    se = card.setdefault("sample_environment_features", {}) or {}
    af = card.setdefault("agent_features_evaluated", {}) or {}
    if cid in RECORD_TYPE_OVERRIDES:
        rt = RECORD_TYPE_OVERRIDES[cid]
    elif rt not in VOCAB["record_type"]["values"]:
        rt = "benchmark" if bf.get("n_tasks") else "system"
    card["record_type"] = rt
    bf["execution_mode"] = EXECUTION_MODE_OVERRIDES.get(cid, norm_execution_mode(bf.get("execution_mode")))
    # coerce enum-ish scalars
    bf["task_source"] = norm_enum(bf.get("task_source"), "task_source", VOCAB["task_source"]["values"])
    bf["scoring_granularity"] = norm_enum(bf.get("scoring_granularity"), "scoring_granularity", VOCAB["scoring_granularity"]["values"])
    for k, vk in (("workflow_depth", "workflow_depth"), ("perceptual_demand", "perceptual_demand"), ("reasoning_demand", "reasoning_demand"), ("safety_criticality", "safety_criticality")):
        tf[k] = norm_enum(tf.get(k), k, VOCAB[vk]["values"])
    se["sample_real_or_simulated"] = norm_enum(se.get("sample_real_or_simulated"), "sample_real_or_simulated", VOCAB["sample_real_or_simulated"]["values"])
    af["rag_or_memory"] = norm_enum(af.get("rag_or_memory"), "rag_or_memory", set(VOCAB["rag_or_memory"]["values"]) | {"some"})
    af["planner"] = norm_enum(af.get("planner"), "planner", VOCAB["planner"]["values"])
    af["verifier_or_self_debug"] = norm_enum(af.get("verifier_or_self_debug"), "verifier_or_self_debug", set(VOCAB["verifier"]["values"]) | {"verifier"})
    af["guards_or_safety_layer"] = norm_enum(af.get("guards_or_safety_layer"), "guards_or_safety_layer", set(VOCAB["guards"]["values"]) | {"some"})
    if af.get("vision_used") not in (True, False, "mixed", None):
        af["vision_used"] = "mixed" if str(af.get("vision_used")).lower() in ("varied", "some", "partial") else None
    # list enums
    def filt(lst, allowed):
        if not lst:
            return []
        out = []
        for x in lst:
            y = norm_enum(x, "", allowed)
            if y and y not in out:
                out.append(y)
        return out
    bf["evaluation_target"] = filt(bf.get("evaluation_target"), VOCAB["evaluation_target"]["values"])
    bf["metric_types"] = filt(bf.get("metric_types"), VOCAB["metric_type"]["values"])
    tf["tool_interface"] = filt(tf.get("tool_interface"), VOCAB["tool_interface"]["values"])
    se["novelty_levels_tested"] = filt(se.get("novelty_levels_tested"), VOCAB["novelty_level"]["values"])
    insts = []
    for inst in bf.get("instruments") or []:
        if not isinstance(inst, dict):
            inst = {"name": str(inst), "modality": "generic_lab"}
        mod = norm_enum(inst.get("modality"), "", VOCAB["instrument_modality"]["values"]) or "generic_lab"
        ros = norm_enum(inst.get("real_or_simulated"), "", VOCAB["real_or_simulated"]["values"])
        insts.append({"name": str(inst.get("name", "?")), "modality": mod, "real_or_simulated": ros})
    bf["instruments"] = insts
    for k in ("n_tasks", "n_task_families", "n_instances_or_runs_reported", "n_agent_configs"):
        v = bf.get(k)
        if isinstance(v, str):
            m = re.search(r"\d[\d,]*", v)
            bf[k] = int(m.group(0).replace(",", "")) if m else None
    for k in ("has_human_baseline", "has_safety_eval", "has_abstention_eval", "open_source"):
        if bf.get(k) not in (True, False, None):
            bf[k] = None
    for k in ("closed_loop_feedback",):
        if tf.get(k) not in (True, False, None):
            tf[k] = None
    if se.get("injected_faults") not in (True, False, None):
        se["injected_faults"] = None
    for k in ("multi_agent", "deterministic_execution"):
        if af.get(k) not in (True, False, None):
            af[k] = None
    if card.get("status") not in ("published", "preprint", "withdrawn"):
        card["status"] = "preprint" if "arxiv" in str(card.get("venue", "")).lower() else ("published" if card.get("doi") else None)
    if isinstance(card.get("year"), str):
        card["year"] = int(re.search(r"\d{4}", card["year"]).group(0))
    for k in ("arxiv", "doi", "license", "code_url", "data_url", "short_name", "venue", "authors_short", "notes"):
        if card.get(k) is not None and not isinstance(card[k], str):
            card[k] = str(card[k])
    card["related"] = [ALIASES.get(r, r) for r in (card.get("related") or []) if r]
    card["related"] = [r for r in dict.fromkeys(card["related"]) if r != cid]
    def strlist(lst):
        out = []
        for x in lst or []:
            if isinstance(x, dict):
                out.append("; ".join(f"{k}: {v}" for k, v in x.items()))
            elif x is not None:
                out.append(str(x))
        return out
    for k in ("transfer_relevant_findings", "limitations", "schema_axes_proposed"):
        card[k] = strlist(card.get(k))
    for blk, keys in ((bf, ("scientific_domains", "agents_evaluated", "headline_results")), (tf, ("task_taxonomy",)), (se, ("sample_types",)), (af, ("models", "tools"))):
        for k in keys:
            blk[k] = strlist(blk.get(k))
    if not card["schema_axes_proposed"]:
        card.pop("schema_axes_proposed")
    srcs = [u for u in (card.get("url"), card.get("code_url")) if u and str(u).startswith("http")]
    card["provenance"] = {
        "extracted_on": EXTRACTED_ON,
        "extraction_method": "llm_assisted",
        "sources_consulted": srcs,
        "confidence": "medium",
        "review_status": "unreviewed",
        "reviewer_notes": f"Merged from {', '.join(sources)}." if len(sources) > 1 else None,
    }
    # drop unknown top-level keys
    allowed_top = {"id", "record_type", "name", "short_name", "year", "venue", "authors_short", "arxiv", "doi", "url", "code_url", "data_url", "license", "status", "summary", "schema_axes_proposed", "benchmark_features", "task_features", "sample_environment_features", "agent_features_evaluated", "transfer_relevant_findings", "limitations", "related", "notes", "provenance"}
    for k in list(card):
        if k not in allowed_top:
            card.pop(k)
    order = ["id", "record_type", "name", "short_name", "year", "venue", "authors_short", "arxiv", "doi", "url", "code_url", "data_url", "license", "status", "summary", "schema_axes_proposed", "benchmark_features", "task_features", "sample_environment_features", "agent_features_evaluated", "transfer_relevant_findings", "limitations", "related", "notes", "provenance"]
    return {k: card[k] for k in order if k in card}


class Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data):
    if "\n" in data or len(data) > 100:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


Dumper.add_representer(str, _str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=str(ROOT / "data" / "raw" / "extractions_2026-09-14"))
    ap.add_argument("--out", default=str(ROOT / "data" / "benchmarks"))
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    groups = load_all(Path(a.batch))
    known = set(groups)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for cid, docs in groups.items():
        p = out / f"{cid}.yaml"
        if p.exists() and not a.overwrite:
            continue
        card, sources = merge(docs)
        card = normalise(card, cid, sources)
        card["related"] = [r for r in card["related"] if r in known]
        with open(p, "w") as f:
            yaml.dump(card, f, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=110)
        n += 1
    print(f"wrote {n} cards to {out} ({len(groups)} canonical ids from {sum(len(v) for v in groups.values())} raw docs)")


if __name__ == "__main__":
    main()

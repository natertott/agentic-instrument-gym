# Raw extraction batch, 2026-09-14

Seven LLM-assisted literature extractions (A–G), each covering one cluster of benchmarks, produced against a shared template
and written with primary-source verification where the network allowed it. arxiv.org and most publisher sites were blocked by the
session's egress proxy, so most numeric facts come from GitHub repositories (READMEs, notebooks, supplementary PDFs) and
web-search snippets; every record's `notes` field says what could not be verified.

| File | Cluster |
|---|---|
| extract_A.yaml | ScienceAgentBench and data-driven discovery benchmarks (DiscoveryWorld, ScienceWorld, DiscoveryBench, SciGym, ScienceBoard, SciAgentBench, SciReplicate, ResearchCodeBench, AutoSDT) |
| extract_B.yaml | AFMBench / AILA and scanning-probe LLM agents |
| extract_C.yaml | LabOSBench, LabOS, LAB-Bench, protocol benchmarks (BioProBench, BioPlanner, BioLP-bench, BenchBench-Protocol, ProtoAct, Pipette) |
| extract_D.yaml | EnvTrace, VISION, experiment automation agents (APS), ALS Osprey / Lightfall, AI X-ray scientist, AutoXRD |
| extract_E.yaml | Johnson & Abshire X-ray microscopy benchmark (with repo SI and notebooks), STEMGym |
| extract_F.yaml | Electron-microscopy agents and microscopy perception benchmarks (MicroVQA, µ-Bench, MaCBench, MMSci, SPM-Bench) |
| extract_G.yaml | Frameworks and metric proposals (Volk & Abolhasani, Adesiji, Canty, Leong, AgentAbstain, generalizability survey, IRT papers, safety benchmarks) |

`scripts/ingest_extractions.py` dedupes and normalises these into `data/benchmarks/*.yaml`. The raw files are kept verbatim
(one YAML quoting fix in extract_F) so every normalised value can be traced back.

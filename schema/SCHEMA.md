# Benchmark evidence schema (WP1)

This document defines the **execution-level evidence schema** used to compare benchmarks for LLM agents that control scientific instruments. It is the enabling infrastructure for the transferability programme: every later work package (surrogate transfer models, the microscopy testbed, agent ablations, qualification cards) consumes rows written in this schema.

It is deliberately **not** a universal benchmark ontology. It records what each benchmark actually measured, on what, with which agent, under which design choices, so that two benchmarks can be placed side by side and the gaps between them made explicit.

## Two levels

| Level | File | One record is | Used for |
|---|---|---|---|
| Benchmark card | `schema/benchmark_card.schema.json` | one benchmark, system, framework, or survey | the explorer site, coverage / gap analysis, benchmark-to-benchmark similarity |
| Execution record | `schema/execution_record.schema.json` | one agent run on one task instance | the transfer dataset that WP2 models train on |

Both share the same four descriptor groups from the proposal, and both draw every enumerated value from `schema/vocab.yaml`, which is the single source of truth for controlled vocabularies.

## The four descriptor groups

### 1. Agent features
What the evaluated agent *is*. Changing any of these changes what a benchmark result licenses.

| Field | Meaning | Why it matters for transfer |
|---|---|---|
| `model` | Base model(s) | Capability floor; also a proxy for training-data contamination |
| `vision` | Whether images / frames reach the model | Perception-heavy tasks cannot transfer to a blind agent |
| `rag_or_memory` | Documentation retrieval, episodic memory, both, none | Memory converts held-out instances into seen ones |
| `planner` | none / ReAct / plan-and-execute / tree search | Governs long-horizon behaviour |
| `tools` / `n_tools_available` | Tool surface exposed to the agent | Tool composition is a transfer axis in its own right |
| `verifier` | self-debug, external verifier, human | Verification is what converts a lucky run into a reliable one |
| `guards` | allowlists, hard limits, human approval | Safety is a non-compensatory endpoint |
| `multi_agent`, `deterministic_execution` | Decomposition and whether actions run through fixed code paths | Candidates for WP4 ablations |

### 2. Task features
What the task *demands*, independent of who attempts it.

| Field | Vocabulary | Notes |
|---|---|---|
| `instrument_modality` | microscopy, spectroscopy, diffraction, synchrotron, liquid_handling, robotics, generic_lab, computation, none | multi-valued at card level |
| `workflow_depth` | single_step < multi_step < long_horizon | ordinal; execution rows also carry `n_required_steps` |
| `perceptual_demand` | none < structured_readout < image_reading < image_interpretation | ordinal |
| `reasoning_demand` | low < medium < high | ordinal |
| `tool_interface` | python_api, cli, gui, rest_api, mcp, natural_language, physical | multi-valued |
| `tool_composition` / `n_tools_required` / `requires_tool_chaining` | free text at card level, numeric at row level | |
| `quantitative_tolerance` / `has_quantitative_target` / `tolerance_rel` | is a number scored against a tolerance? | separates "took an image" from "measured 3.2 ± 0.1 µm" |
| `closed_loop_feedback` | boolean | does the agent observe the instrument and react? |
| `safety_criticality` | none < low < medium < high | high = irreversible or hazardous |
| `task_taxonomy` / `task_family` | the benchmark's own labels, verbatim | never re-labelled at ingest; cross-benchmark `capability_tags` are added separately |

### 3. Sample / environment features
What the agent was *pointed at*, and in what state.

| Field | Vocabulary | Notes |
|---|---|---|
| `sample_types`, `material_class`, `form_factor` | free text | e.g. "Au nanoparticles on Si", "TEM grid", "synthetic phantom" |
| `sample_real_or_simulated` | real, simulated, dataset, none | |
| `signal_quality` / `snr` | low, nominal, high or a number | |
| `novelty` | seen_in_development < held_out_instance < held_out_task < held_out_task_family / held_out_sample_class / held_out_environment / held_out_combination | the central variable for transfer |
| `calibration_state`, `api_state` | calibrated / drifted / uncalibrated; nominal / degraded / changed | instrument-state shift |
| `injected_fault` | free text or none | fault-recovery tasks |

### 4. Benchmark features
How the *evidence* was generated.

| Field | Notes |
|---|---|
| `evaluation_target` | what is scored: instrument_control, code_generation, computer_use, QA, perception, protocol_planning, data_analysis, simulation_control, safety |
| `execution_mode` | physical_instrument, digital_twin, simulator, execution_trace, static_code_eval, static_text, hybrid — the biggest single determinant of what a result means |
| `n_tasks`, `n_task_families`, `n_instances_or_runs_reported`, `repetitions_per_task` | size and repetition structure |
| `target_population`, `task_source`, `sampling_strategy` | what population the tasks claim to represent and how they were drawn |
| `metric_types`, `primary_metric`, `scoring_granularity` | binary vs partial vs continuous scoring changes what "success rate" means |
| `holdout_or_split_design`, `leakage_or_contamination_risk` | whether held-out evaluation is even possible |
| `has_human_baseline`, `has_safety_eval`, `has_abstention_eval` | |
| `agents_evaluated`, `n_agent_configs` | breadth of the agent side |

## Outcome (execution rows only)
`success`, `score` in [0, 1], `partial_credit`, `safety_violation`, `abstained`, `abstention_correct`, `failure_mode`, `n_steps`, `wall_time_s`, `cost_usd`, `tokens_total`, `quantitative_error_rel`.

Safety violations are recorded separately from success so they can be treated as a non-compensatory endpoint downstream.

## Provenance
Every card records how it was produced (`manual`, `llm_assisted`, `llm_assisted_reviewed`), which sources were consulted, a confidence level, and a review status. Every execution row records whether it came from released logs, a paper table or figure, a reproduction, or internal data, and whether it is a single run or a mean over runs.

## Encoding for comparison (`aig/features.py`)
* ordinal → rank scaled to [0, 1] (`mixed` is treated as missing, not as a level)
* nominal → one-hot; multi-valued → multi-hot, each block weighted so it counts as one feature
* booleans → 0/1; counts → log10(1 + n), min-max scaled
* distances are weighted Gower with pairwise deletion of missing values, overall and per descriptor group

## Design principles
1. **Record, don't re-label.** A benchmark's own taxonomy is kept verbatim; cross-benchmark labels live in separate fields.
2. **Null means unknown, not absent.** Unreported fields are `null` and excluded from distances rather than imputed.
3. **Separate the evidence from the claim.** Benchmark features describe how evidence was generated; the card never asserts what the evidence licenses.
4. **Safety is its own column.** It is never folded into a composite score.
5. **Everything is diffable.** Cards are YAML, one file per benchmark, validated in CI.

## Extending the vocabularies
Add the value to `schema/vocab.yaml` with a one-line gloss, then add it to the corresponding enum in the JSON schemas. `tests/test_schema_and_tools.py` checks the two stay in sync.

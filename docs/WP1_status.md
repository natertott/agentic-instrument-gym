# WP1 status note — first ingest (2026-09-15)

> Counts in this note describe the 65 fully extracted cards of the first ingest. The discovery sweep later added 31 identity-level stub cards (`confidence: low`); with those included the comparable set is 86 works, 44 on real hardware, and the family-holdout axis is covered by one work (the XRM benchmark's held-out tasks). Run `python -m aig report` for current numbers.

This note records what the first pass of the benchmark evidence schema shows, so the numbers here can be checked
against `python -m aig report` and the atlas as the dataset grows. Everything below is derived from the cards and
execution rows in this repository; nothing is quoted from memory.

## What was gathered

| | count |
|---|---|
| records (cards) | 65 |
| benchmarks and systems (the comparable subset) | 55 |
| that touch a microscope | 25 |
| microscopy records that run on real hardware | 12 |
| microscopy *benchmarks* (task set + scoring rule, not just a demonstration) | 12 |
| execution rows re-encoded from released logs | 1,896 |

Execution mode across the comparable subset: static_text 15, physical_instrument 14, hybrid 9, simulator 7, static_code_eval 7, digital_twin 2, execution_trace 1.

Microscopy benchmarks proper: AFMBench, DiscoveryWorld, EMSeek, LabOSBench, MaCBench, µ-Bench, MicroVQA, MMSci, PlantMicro, SPM-Bench, STEMGym, XRM agent benchmarks.
Microscopy systems with only demonstrations: Agentic-J, ATOMIC, Autonomous Laboratory Agent via Customized Domain-Specific Language Model and Modular AI Interface (later version titled: Integrating Domain-Specialized Language Models with AI Measurement Tools for Deterministic Atomic-Resolution Experimentation), EM CoPilot, EAA, LLM-Guided Open Hypothesis Learning from Autonomous Scanning Probe Microscopy Experiments, Leveraging Large Language Models and Social Media for Automation in Scanning Probe Microscopy (journal title: Leveraging large language model and social network service for automation in scanning probe microscopy), Synergizing human expertise and AI efficiency with language model for microscopy operation and automated experiment design, LLM-XRM (M&M 2025), LLMicroscopilot, MicroscopyGPT, Schema-Bound LLM Control of Scientific Instrumentation through Model Context Protocol Skills, TEM Agent.

## Coverage of the axes the transferability programme needs

Sixteen design axes are checked by `aig.compare.axis_coverage`. Of 55 benchmarks and systems:

| axis | covering |
|---|---|
| Actions run on real hardware | 23 |
| Faithful instrument simulator | 2 |
| Any microscopy modality | 25 |
| Agent acts on instrument feedback | 25 |
| Requires domain image interpretation | 23 |
| Long-horizon workflows | 21 |
| Scores quantitative outputs against tolerances | 21 |
| Scores safety / prohibited actions | 11 |
| Scores abstention | 3 |
| Repeated runs per task reported | 11 |
| Holds out tasks, task families, sample classes or environments | 1 |
| Varies calibration / API / instrument state | 6 |
| Injects faults | 4 |
| Compares more than one agent configuration beyond the base model | 24 |
| Reports a human baseline | 12 |
| Tasks and harness released | 35 |

**Gaps.** No surveyed work covers: none.
Only one or two cover: faithful instrument simulator, holds out tasks, task families, sample classes or environments.

Read together: the field has many benchmarks that act on real or simulated instruments and score closed-loop,
image-dependent, multi-step work, but almost none that hold out a *family* (task family, sample class or instrument
state) rather than an instance, that vary calibration or API state on purpose, or that inject faults. Those three
axes are exactly the ones a transfer claim rests on, and exactly what the WP3 microscopy testbed must supply.

## What the seeded execution rows already show

Two benchmarks released per-run logs, and both are now rows in the transfer dataset.

**X-ray microscopy agent benchmarks** (696 rows from the released selected-configuration suites).
Pass rate on the 53 development tests: 85.8% over 636 runs; on the 5 held-out validation tasks:
40.0% over 60 runs. The held-out drop is the paper's central finding reproduced from its own logs.
Failure modes among failed runs: timeout 55, wrong_quantity 36, tool_error 19, hallucinated_completion 7, execution_error 6, other 2, None 1.
Timeouts (operational limits on duration, LLM calls or tool calls) dominate, not wrong answers.

**AFMBench** (1200 rows: 100 tasks x 4 models x 3 trials). Pass rate on Basic tasks 70.5%
(672 trials) versus Advanced tasks 6.6% (528 trials). Failure modes among failed
trials: execution_error 279, other 184, planning 184, tool_error 44. Code errors and wrong-agent routing dominate; the
label N/EXTRA (unrequested extra operations) is recorded as `other` and is a candidate for its own failure mode in the
next vocabulary revision.

Success by workflow depth, per benchmark:

| benchmark | workflow depth | pass rate | n |
|---|---|---|---|
| afmbench | multi_step | 54.8% | 828 |
| afmbench | single_step | 14.8% | 372 |
| xrm_agent_benchmarks | multi_step | 80.6% | 372 |
| xrm_agent_benchmarks | single_step | 83.3% | 324 |

## Where the anchor benchmarks sit relative to one another

Similarity is 1 - weighted Gower distance over the encoded schema features (missing fields dropped pairwise).

| pair | similarity |
|---|---|
| XRM agent benchmarks vs AFMBench | 0.88 |
| XRM agent benchmarks vs LabOSBench | 0.62 |
| XRM agent benchmarks vs EnvTrace | 0.65 |
| AFMBench vs LabOSBench | 0.69 |
| LabOSBench vs ScienceBoard | 0.84 |
| EnvTrace vs ScienceAgentBench | 0.78 |
| ScienceAgentBench vs AFMBench | 0.69 |

The two physical microscopy benchmarks (XRM, AFMBench) are each other's nearest neighbours; the GUI simulators
(LabOSBench, ScienceBoard) form a second cluster; code-scored benchmarks (ScienceAgentBench, EnvTrace) a third.
That is the expected structure, which is a sanity check on the encoding rather than a finding.

## Schema changes made during ingest

* Added `held_out_task` between `held_out_instance` and `held_out_task_family` in the novelty vocabulary, and
  `holdout_task` as a split role: the XRM benchmark holds out task identities inside seen families, which neither
  existing level described.
* `digital_twin` is used for instrument-specific stateful simulators (LabOSBench's eight GUI simulators, STEMGym),
  `simulator` for abstract environments (ScienceWorld, DiscoveryWorld, AgentAbstain sandboxes).
* Free-text values from extraction that did not map to a vocabulary were set to `null`, never guessed.

## Known limitations of this batch

* Extraction was LLM-assisted with arXiv and most publisher sites unreachable; GitHub repositories and search
  snippets were the main sources. Every card's `notes` lists what could not be verified, and only six core cards
  have `review_status: reviewed`.
* `novelty_levels_tested` is populated only on reviewed cards, so the family-holdout axis undercounts until review
  finishes.
* STEMGym's task and family counts look inverted in the extraction and are flagged low-confidence.
* Execution rows exist for two benchmarks; EnvTrace, ScienceAgentBench and LabOSBench release logs or per-task
  results that can be ingested next.

## Next steps inside WP1

1. Finish human review of the remaining core cards (LabOS, VISION, experiment automation agents, STEMGym, ScienceBoard, AutoXRD).
2. Ingest EnvTrace, ScienceAgentBench and LabOSBench per-task results as execution rows.
3. Add cross-benchmark `capability_tags` to task families (focus, ROI navigation, calibration, measurement, composition, recovery) so WP2 can test capability-level transfer.
4. Draft the universal multi-agent / multi-instrument schema from the fields that proved necessary here.

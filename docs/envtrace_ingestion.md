# EnvTrace release assessment and conservative import

Assessed 2026-11-03 against Agentic Instrument Gym commit
`d2aecfb2881e69fc54a24facd07a86dff330d09c`.

## Source and what the files actually contain

The [EnvTrace README](https://github.com/CFN-softbio/EnvTrace) links the
[Zenodo experimental release](https://zenodo.org/records/17526264), DOI
10.5281/zenodo.17526264, version 1.0.0. Attribution: Noah van der Vleuten,
Anthony Flores, Shray Mathur, Max Rakitin, Thomas Hopkins, Kevin Yager,
Esther Tsai and Brookhaven National Laboratory. The dataset license is CC BY 4.0;
the EnvTrace software has a separate Apache 2.0 license.

The downloaded `EnvTrace_experiments.zip` is 98,090,917 bytes and matches the
published MD5 `61229997d75dea73f0ef2cba3a039f3f`. It contains 3,970 ZIP members,
including 580 `results_op_agent.csv` files with 40,072 parsed records. The four
top-level experimental groups are:

| Campaign directory | CSV files | CSV records | Records with explicit full_match |
|---|---:|---:|---:|
| bluesky_runs_07-26 | 404 | 16,728 | 0 |
| old_prompt_old_dataset_25_08 | 36 | 4,536 | 0 |
| new_dataset_old_prompt_switch_linkam_on_adj_19_09 | 39 | 5,304 | 5,304 |
| new_prompt_new_dataset_12_8 | 101 | 13,504 | 3,672 |

Typical layout is `saved_named_runs/<campaign>/<model alias>/<session>/run_<n>/`.
CSV rows contain a command, reference code alternatives, generated code,
inference time, code similarity scores and, depending on version, PV traces,
continuous scores and explicit Boolean outcomes. Sibling files contain the system
prompt, console/pexpect logs and run statistics. Session-level aggregate statistics
and model comparison summaries are separate files.

These are genuine individual **evaluation trials**, rather than statistics
reverse-engineered into trials. They are not all fresh simulator executions:
the harness can accept exact-code matches without simulation and reuse cached
execution traces. Debug results replay reference code, not a model's response.
The current [VISION evaluator](https://github.com/CFN-softbio/VISION/blob/beec50c2fb22ae4a7393322114bc84e84c80a6d6/backend/tests/test_op_cog.py)
documents the exact-match shortcut and caching; released console logs corroborate
these behaviors. That current commit is interpretive evidence, not a recovered
historical evaluator version for every campaign.

## Included subset and exclusions

| Disposition | CSV files | Records |
|---|---:|---:|
| Imported | 62 | 8,432 |
| Missing per-trial full_match column | 440 | 31,096 |
| Empty CSV | 74 | 0 |
| Debug/reference model | 3 | 408 |
| Byte-identical result-file duplicate | 1 | 136 |

The duplicate is `new_prompt_new_dataset_12_8/grok-4-or/20250916_225002/run_2/`
whose CSV is identical to `run_1/` in the same session. Keep run_1 and record
run_2's alias in the audit. Distinct CSVs with identical codes or outcomes are
retained: those alone do not establish duplication. Byte-identical whole CSVs are
collapsed only within the same model/session, conservatively avoiding duplicate
evidence even though the release does not explain why those files are identical.

The subset contains 136 task identities (116 simple, 20 complex), 21 model aliases,
23 model/campaign/prompt-hash configurations, 6,464 reported passes and 1,968
reported failures. The old-prompt campaign contributes 5,304 records and the
new-prompt campaign contributes 3,128. These are observational campaign labels;
the naming does not establish a randomized or paired prompt comparison.

5,490 rows have `exact_match=True` and an empty predicted PV trace. They are
flagged as exact-code shortcuts in the evidence file. Other records distinguish
present traces (potentially cached) from absent/empty traces with unknown cause.
Do not count cached executions or repeated generated code as statistically
independent draws without further evidence.

## Schema and ingestion mapping

No schema extension is necessary. Like the existing AFMBench and XRM ingestion
scripts, this converter writes one JSONL execution record per released trial.
It adds stricter input checking, duplicate-file auditing and aggregate checks.

| Released evidence | Execution field / treatment |
|---|---|
| Archive member + parsed CSV record ordinal | Deterministic execution_id; exact locator and CSV SHA-256 in provenance |
| Command + ordered reference-code alternatives | SHA-256 task_id; command in instruction_text; references retained in companion evidence |
| is_complex | Verbatim simple/complex family; does not imply workflow-depth or reasoning-demand labels |
| run_n | Zero-based repetition_index preserved, including gaps after deduplication |
| full_match | Boolean outcome.success; blank remains null; never inferred from full_score or exact_pv_match |
| full_score | outcome.score, checked finite and in [0,1]; not rescaled or binarized |
| Model directory | Verbatim model alias; no inferred provider or canonical snapshot |
| Campaign + model + system-prompt hash | agent_id; prompt hash also in prompt_version |
| Session timestamp directory | Evidence session_label; execution timestamp remains null (not a per-row timestamp or known timezone) |
| inference_time | Verbatim in companion evidence; wall_time_s remains null because inference time is not end-to-end execution time |
| PV traces and exact_match | Companion event count and scoring-path flag; benchmark execution_mode=hybrid |
| All included trials | benchmark_id=envtrace, modality=synchrotron, metric_type=trace_alignment, aggregation=single_run |
| Physical specimen | none: this evaluation measures simulated control behavior, not a physical sample |
| Aggregate JSON | QA checks of count and successes only; never expanded into execution rows |
| Unreported cost, tokens, failure cause, safety, decoding settings | null or omitted; no zero defaults or assumed failure taxonomy |

The schema's provenance object disallows extra keys. Rich source information is
therefore kept in `data/raw/envtrace/envtrace_evidence.jsonl`, joined by
execution_id. `ingestion_audit.json` inventories every result CSV, hashes, row
counts, exclusions and duplicate source locators. The original archive is not
vendored; published checksums plus source locators permit recovery of all original
metrics, traces and code. The converter reads data only and never executes released
generated code or extracts arbitrary ZIP paths to disk.

Canonical model identifiers, exact decoding settings, per-trial wall time,
tokens/costs, reliable fresh-versus-cached execution status, historical harness
commit and complete per-task scoring configurations are not supplied uniformly.
Older CSVs often contain useful per-trial full_score values but lack full_match.
A separate continuous-outcome import with success=null is defensible after
version/campaign/dataset and overlap auditing. It is deliberately outside this
binary-labeled subset. Neither aggregate success counts nor score thresholds can
recover which older individual trials passed the strict evaluator.

## Reproduction and validation

Run the commands in the README with the pinned ZIP. The CLI verifies its size and
MD5, validates all records against the existing schema and benchmark foreign key,
then writes the three outputs. `--output-root /tmp/envtrace-rebuild` permits a
clean reconstruction for byte-for-byte comparison. Input and output ordering,
identifiers and hashes are deterministic; generated timestamps are omitted.

Tests use three attributed released records (shortcut pass, trace pass, failure)
plus deliberate mutations. They cover schema compatibility, null outcomes,
unknown runtime, score-only exclusions, debug exclusions, duplicate files/tasks,
reference-sensitive task identity, deterministic conversion, malformed labels,
nonfinite/out-of-range scores and aggregate discrepancies. The complete generated
dataset is validated by the existing repository-wide tests.

Validation of the proposed revision: **25 tests passed** (the unchanged baseline
had 11). `python -m aig validate` reports **96 valid cards and 10,328 valid
execution records**. A clean second conversion reproduces all three generated
outputs byte-for-byte. All 62 imported CSVs agree with their sibling aggregate
counts and success totals. Of 8,432 rows, 5,490 have shortcut scoring, 2,643 have
nonempty predicted PV traces and 299 have no predicted PV trace with unknown cause.
Site exports were regenerated and checked for freshness; the proposed diff passes
`git diff --check`.

## Scientific value and limits

This adds a third benchmark with execution-level outcomes and an independent
research group's beamline API, task population and evaluator. Leaving EnvTrace
entirely out of training creates an external test of whether relationships learned
from AFM/XRM transfer to beamline code generation. Its behavioral trace metric
provides a useful contrast to microscopy task checks and helps expose dependence
on evaluator design. The continuous score can support sensitivity analyses without
pretending that scores are calibrated equally across benchmarks.

For defensible analysis:

1. Hold out the entire benchmark for external transfer. Within benchmarks, group
   all repetitions and reference variants of a command together; avoid random
   row splits that leak task identities. Match commands across revised references
   too, rather than relying solely on the reference-sensitive task_id.
2. Retain campaign/prompt/model structure. Verify overlapping canonical model
   snapshots before comparing model rankings; directory aliases alone are not
   sufficient. Evaluate whether task/configuration covariates have shared support.
3. Report both the full hybrid evaluation subset and a sensitivity analysis
   restricted to records with predicted traces. Filtering changes the population
   and disproportionately removes easy exact matches; it is not an unbiased
   alternative estimate of overall accuracy.
4. Weight by benchmark/task or use a hierarchical analysis so 8,432 new rows do
   not dominate the 1,896 previous records. Bootstrap at task/configuration blocks,
   not independent rows; the release's cache behavior warrants conservative
   uncertainty estimates.

The new dataset improves external validity **testing**, not proof of universal
generalization. Three benchmarks still confound domain, architecture, task set
and metric. This beamline digital twin measures control logic rather than
physical measurement quality, closed-loop discovery or safe real-world operation.
No new transfer-performance result has been claimed or fitted in this change.

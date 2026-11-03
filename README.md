# agentic-instrument-gym

Infrastructure for **Work Package 1** of *When can we trust scientific-instrument agents beyond their benchmarks?* — a
benchmark evidence schema, a growing transfer dataset, and tooling to compare benchmarks for LLM agents that operate
scientific instruments (microscopes first, beamlines, diffractometers, liquid handlers and lab simulators alongside).

The question WP1 serves: *what does success on tasks and samples A, B, C tell us about expected performance on task or
sample D?* Answering it needs every benchmark described in the same terms — what the agent was, what the task demanded,
what it was pointed at, and how the evidence was generated — rather than a single headline score.

## What is here

| Path | Contents |
|---|---|
| `schema/` | The execution-level evidence schema: `benchmark_card.schema.json` (one record per benchmark), `execution_record.schema.json` (one row per agent run), `vocab.yaml` (every controlled vocabulary, with glosses), `SCHEMA.md` (field-by-field rationale) |
| `data/benchmarks/` | One YAML card per benchmark, system, framework or survey (96 after the first ingest and discovery sweep). Each card carries `inclusion: core` or `inclusion: reference` |
| `data/executions/` | The transfer dataset: per-run rows re-encoded from released benchmark logs (10,328 rows: 1,896 existing AFMBench/X-ray microscopy records plus 8,432 EnvTrace evaluation trials; see the EnvTrace audit for exclusions and shortcut scoring) |
| `data/raw/` | Verbatim extraction batches, released run logs, and their provenance notes |
| `data/candidates.yaml` | Works examined in the discovery sweep and not given a card (adjacent or excluded), with the reason |
| `aig/` | Python package: validation, feature encoding, Gower distances, axis-coverage / gap analysis, site export |
| `site/` | The static explorer (no build step; GitHub Pages deploys it from `main`) |
| `scripts/` | Ingestion of raw extractions and of released run logs |

## Quick start

```bash
pip install -e ".[dev]"
python -m aig validate          # every card and execution row against the schemas
python -m aig report            # axis coverage, gaps, nearest neighbours, unused vocabulary
python -m aig matrix --group task   # Gower distance matrix on one descriptor group
python -m aig export --standalone   # regenerate site/data/*.json and a single-file site/index.standalone.html
python -m pytest -q
```

Open `site/index.html` through any static server (or the standalone file directly) to browse the atlas.

## Core set vs reference

Analysis runs on the **core set**: cards that are benchmarks in the strict sense, with a reported task set, a named
metric and verified extraction (29 of 96 today). Everything else stays in the repository with its extracted data intact
but is held as **reference**: agent and platform papers whose evaluation is a demonstration, metric frameworks and
surveys with no task set, and discovery-sweep stubs awaiting full extraction. Reference cards are excluded from
coverage, distance and gap analysis, and every card records why in `inclusion_reason`.

`scripts/set_inclusion.py` applies the rule and never overwrites a reason beginning `manual:`, so hand decisions stick.
The tooling defaults to the core set (`python -m aig report`, `python -m aig matrix`); pass `--scope reference` or
`--scope all` to widen it. The atlas has the same switch in its filter rail, and every view respects it.

## The schema in one paragraph

Every card and every execution row carries four descriptor groups from the proposal: **agent** (model, vision, retrieval /
memory, planner, tools, verifier, guards, multi-agent, deterministic execution), **task** (instrument, workflow depth,
perceptual and reasoning demand, tool composition, quantitative tolerance, closed-loop feedback, safety criticality, the
benchmark's own taxonomy), **sample / environment** (material and form factor, real or simulated, signal quality, novelty
level held out, calibration and API state, injected faults) and **benchmark** (target population, task source and
sampling, size and repetitions, metric type and granularity, split design, leakage risk, safety and abstention scoring).
Safety violations are recorded separately from success so they can be a non-compensatory endpoint. Unknown is `null`,
never imputed. A benchmark's own labels are recorded verbatim; cross-benchmark labels live in separate fields.
See `schema/SCHEMA.md`.

## Adding or correcting a benchmark

1. Copy any card in `data/benchmarks/`, keep the id `snake_case`, fill what the primary source supports, leave the rest `null`.
2. Set `provenance.extraction_method` (`manual`, `llm_assisted`, `llm_assisted_reviewed`) and `review_status`.
3. `python -m aig validate && python -m aig export` and commit the regenerated `site/data`.

New vocabulary values go in `schema/vocab.yaml` first, then in the matching JSON-schema enum; the tests check they agree.

## Status and caveats

The first batch of 65 cards was produced by LLM-assisted extraction against a shared template on 2026-09-14, with
primary-source verification where the network allowed (arXiv and most publisher sites were blocked; GitHub repositories,
supplementary files and search snippets were not). Each card's `notes` says what could not be verified and its
`provenance.review_status` says whether a human has checked it. Treat unreviewed numbers as leads, not citations.

## Roadmap inside WP1

- [x] Schema v0.1 (cards + execution rows) and controlled vocabularies
- [x] First ingest of the anchor benchmarks and their neighbours
- [x] Comparison tooling: encoding, Gower distances, axis coverage, gap report
- [x] Interactive atlas
- [x] Execution rows for the two benchmarks with released per-run logs (AFMBench, X-ray microscopy)
- [x] Conservative EnvTrace import with explicit per-trial labels (8,432 rows; older score-only results excluded)
- [ ] Execution rows for ScienceAgentBench and LabOSBench
- [ ] Human review of every core card (`review_status: reviewed`)
- [ ] Cross-benchmark `capability_tags` on task families (feeds WP2 transfer representations)
- [ ] Universal schema draft for multiple agents and instruments (WP1 → WP3 hand-off)

## EnvTrace released evaluations

See [the ingestion assessment](docs/envtrace_ingestion.md) for field mappings, exclusions, scientific limitations,
and validation. The converter reads the pinned Zenodo ZIP without executing any released code:

```bash
curl -L --fail https://zenodo.org/records/17526264/files/EnvTrace_experiments.zip -o /tmp/EnvTrace_experiments.zip
python scripts/ingest_envtrace_runs.py /tmp/EnvTrace_experiments.zip
python -m aig validate
python -m pytest -q
python -m aig export
```

The archive is not vendored. Its published size and MD5 are checked before conversion.
`data/raw/envtrace/ingestion_audit.json` inventories every result CSV; `envtrace_evidence.jsonl`
retains source locators, prompt hashes, model aliases, reported inference times and scoring-path flags.
These are **hybrid evaluation trials**: some exact-code matches bypass simulation, and trace results can be cached.
They are not evidence of independent physical instrument runs.

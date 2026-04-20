# MESS-Materials

DFT-computed material properties for Microbial Electrochemical Systems
(MES) components — electrodes, membranes, chambers, current collectors,
catalysts, gaskets, and supports. A **sidecar to
[Messai-io/MESS-Parameters](https://github.com/Messai-io/MESS-Parameters)**,
keyed by the same material slugs.

## What this repo is

MESS-Parameters owns the MES parameter ontology and literature
extractions. For each material-named parameter slug in that ontology
(`carbon_cloth`, `nafion_membrane`, `platinum_cathode`,
`anion_exchange_membrane`, …), this repo publishes the **DFT-computed
physical properties** pulled from the Materials Project (MP) and
related open databases:

- Summary properties: band gap, formation energy, energy above hull,
  density, metallicity.
- Pourbaix stability at MES operating conditions (MFC anode, MFC
  cathode, MEC cathode).
- Crystal structure (CIF) — reserved for later ML feature extraction.
- Later (v0.2+): elasticity tensors, surface energies, composite scores
  (EVS / BCS / LSS).

## What this repo is not

- **Not** a replacement for MESS-Parameters. The parameter ontology,
  extraction corpus, and literature-value database stay there.
- **Not** a source of experimental data. Everything here is computed
  from first principles or derived from DFT databases. Experimental
  values belong in MESS-Parameters.
- **Not** an ML training repo. MACE / CHGNet / EquiformerV2 embedding
  and transfer-learning work lives in MESS-Learning. This repo
  publishes the structures those models consume, not the models
  themselves.

## How it connects to MESS-Parameters

```
MESS-Parameters (tag v0.2.0)              MESS-Materials (this repo, tag v0.1.0)
  parameter-definitions-rich.json   ◄── slug join key ──►  mp-materials-rich.json
  (narrative, extractions, slugs)                          (DFT properties)
```

MESS-Parameters is **not modified** by this project. Its v0.2.0 schema
stays frozen. The join happens in downstream consumers (messai-ai)
by matching slugs across both rich.json files.

See `docs/plans/v0.1-mp-ingest.md` for the full producer plan and
`docs/consumer-contract.md` (arriving with v0.1.0-pilot) for the shape
downstream consumers can depend on.

## Status

**v0.0 — scaffolding.** No data yet. Producer plan is at
`docs/plans/v0.1-mp-ingest.md`. First tagged release (v0.1.0-pilot,
100-material pipeline validation) targets end of week 4.

## Licensing

- This repo's code and curated data: see `LICENSE` (to be added with
  v0.1.0-pilot; planned: MIT for code, CC-BY-4.0 for data).
- **Upstream Materials Project data is CC-BY-4.0** — any downstream
  consumer displaying MP-derived values must credit the Materials
  Project per CC-BY-4.0 terms. See `data/SCIENTIFIC_INTEGRITY.md`
  (arriving with v0.1.0-pilot) for the attribution template.

## Layout

```
data/           canonical JSON artifacts (rich.json, pourbaix results, lock file)
data/mp-cache/  raw MP API responses, checked in for reproducibility
schemas/        JSON Schema definitions for all published artifacts
scripts/        Python ingestion + computation pipeline
docs/           plans, consumer contract, methodology
ci/             schema validation + slug-coverage enforcement
```

## Getting involved

This repo is part of the [Messai-io](https://github.com/Messai-io)
open-source ecosystem for microbial electrochemical systems. Issues
and PRs welcome once v0.1.0-pilot lands.

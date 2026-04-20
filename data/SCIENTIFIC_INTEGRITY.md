# MESS-Materials — Scientific Integrity

_Version: v0.1.0-pilot. Sibling to
`open-source/MESS-Parameters/data/SCIENTIFIC_INTEGRITY.md`. Where that
document covers extraction-quality caveats for literature-extracted
values, this one covers the DFT-computation caveats for the MP-derived
data published here._

Read this before citing MESS-Materials values in a paper, report, or
product UI. Every consumer surface showing MP-derived values must link
back to this document.

## Attribution (required)

All property data in `mp-materials-rich.json` is derived from the
**Materials Project** under CC-BY-4.0. Downstream consumers displaying
these values must credit:

> Jain, A., Ong, S. P., Hautier, G., Chen, W., Richards, W. D., Dacek,
> S., Cholia, S., Gunter, D., Skinner, D., Ceder, G., & Persson, K. A.
> (2013). Commentary: The Materials Project: A materials genome approach
> to accelerating materials innovation. *APL Materials*, 1(1), 011002.
> https://doi.org/10.1063/1.4812323

A link to https://materialsproject.org must accompany any visible
MP-derived field.

## Coverage

MESS-Materials v0.1.0-pilot covers 15 of the 26 material-named
parameter slugs in MESS-Parameters (`category=MATERIALS`,
`data_type=OBJECT`). The remaining 11 slugs are explicitly unmapped in
`data/unmapped-materials.json`, each with a reason — most are polymer
electrolytes (Nafion, PEM, AEM, bipolar) or composite descriptors
(catalyst_layer, ammonia_treatment) that have no canonical crystalline
analog in MP. MXene coverage is tagged TEMP pending mp_id verification.

Coverage is expected to grow in lockstep with MESS-Parameters'
vocabulary. If an upstream tag adds new material slugs, CI fails this
repo's next build until they are mapped or explicitly unmapped.

## DFT-coverage tier

Each record carries a `confidence_tier` field:

- **high** — direct crystalline MP match with experimental validation.
  Example: `platinum_cathode → mp-126` (FCC Pt). Treat DFT values as
  trustworthy within standard DFT error bars.
- **medium** — composite with multiple well-matched components. Example
  (hypothetical v0.2): `mno2_on_carbon → [mp-19395, mp-48]`. Aggregated
  fields are weighted averages; individual component fields remain
  trustworthy.
- **low** — any component flagged `proxy: true`. Example: `carbon_cloth
  → mp-48 (graphite)`. The real material is amorphous, disordered, or
  functionally modified in ways that crystalline-DFT on the proxy does
  not capture. **Do not rank low-tier materials against each other
  using DFT-computed EVS/LSS alone** — differentiation lives in the
  MESS-Parameters extraction data (surface treatments, porosity,
  roughness, functional groups).

## Amorphous-carbon limitation

All common MES carbon electrodes — carbon cloth, carbon felt, carbon
paper, activated carbon, carbon nanotubes, graphene oxide, gas diffusion
layer — are proxied to **graphite (mp-48)**. The consequences:

1. Any metric that varies between these materials in practice (surface
   area, porosity, conductivity after surface treatment, biofilm
   attachment) is not distinguishable from mp-48 alone. MESS-Materials
   scores for these slugs will appear near-identical.
2. The literature treats these carbons as interchangeable only to
   first approximation. Real performance differences (>10×) are
   dominated by morphology and surface chemistry that DFT on a bulk
   graphite unit cell cannot see.
3. Graphite band_gap_eV = 0, is_metal = true is accurate for the basal
   plane. Edge-site chemistry, which dominates real electrode behavior,
   is not represented.

**Consumer UI guidance:** For carbon-family slugs, display MP values
with a visible "DFT-proxy (graphite)" badge. Defer ranking to the
MESS-Parameters surface-treatment parameters.

## Pourbaix stability — thermodynamic, not kinetic

Pourbaix diagrams encode **equilibrium** thermodynamic stability. A
material labelled `state: corroding` at a given (E, pH) is
thermodynamically unstable toward the listed `stable_phase`, but:

- **Kinetic barriers can make a "corroding" material practically
  stable.** Graphite at MFC conditions is the canonical example:
  thermodynamically C → CH4(aq) is favored, but the reaction rate at
  MES temperatures is effectively zero without a catalyst. We apply a
  **kinetic-stability override** that rewrites `corroding` →
  `passivated` for elements with known passivation (Ti, Al, Cr, Ni, Ta,
  Zr via aqueous oxide layers) or known kinetic inertness (C).
- **A "stable" label for an alloy component does not certify the
  alloy.** `stainless_steel → mp-13 (Fe)` maps to Fe metal, which
  corrodes thermodynamically at MFC anode. The passivator override
  (Cr, Ni in the alloy composition) is not applied here because we
  only carry Fe in the components array. Real stainless-steel
  performance depends on Cr content — a v0.2 refinement will require
  explicit SS-304/SS-316 composition records.
- **MnO2, Fe3O4, Co3O4 showing `corroding` is thermodynamically
  accurate but kinetically misleading over short timescales.** These
  oxides are used as MFC cathode catalysts in practice; their
  Pourbaix-indicated dissolution toward ionic products is slow at room
  temperature and is why long-term MES cathode stability is an open
  research question. Consumers should present this as "thermodynamic
  corrosion risk" rather than "will fail."

## Composite-material handling

Records with multiple components (e.g. v0.2 `mno2_on_carbon`):

- Scalar Tier 1 fields (band_gap, formation_energy, etc.) are weighted
  by `loading` when specified, equal-weight otherwise.
- `is_metal` is conservative: true only when every component is metallic.
- Pourbaix stability uses the primary (bulk_structure role) component.
  This can produce misleading verdicts for catalyst-on-support
  materials where the catalyst dissolves but the support is stable.
  Consumer UI should surface per-component Pourbaix results when
  available (v0.2+).
- `structure_cif` is the primary component's CIF. CIF-based features
  (future MLIP embeddings) will not capture the composite's real
  interfacial structure.

## Passivator / kinetic-inertness override list

The following elements receive a `corroding → passivated` state
override when Pourbaix predicts thermodynamic instability, because of
well-established kinetic phenomena:

| Element | Mechanism |
|---|---|
| Ti | aqueous TiO₂ passivation layer |
| Al | aqueous Al₂O₃ passivation layer |
| Cr | aqueous Cr₂O₃ passivation layer |
| Ni | aqueous NiO passivation layer |
| Ta | aqueous Ta₂O₅ passivation layer |
| Zr | aqueous ZrO₂ passivation layer |
| C  | kinetic inertness (graphite redox reactions require a catalyst) |

The override is binary (on/off). It does not quantify the
passivation-layer robustness, nor does it account for mechanical damage,
halide ions, or other mechanisms that can break passivation in practice.

## DFT functional

Summary-API values use the default MP dataset, which is **PBE GGA**
(with +U corrections for select transition-metal oxides). PBE
systematically underestimates band gaps — in particular, for some
semiconducting cathode oxides, it can incorrectly predict metallic
behavior. **r2SCAN** data is available in MP for a growing subset of
materials and gives more accurate electronic structure for transition-
metal oxides. v0.2 will prefer r2SCAN where available and record the
functional per field.

## Reproducibility

- `data/mp-cache/<mp_id>.json` contains the raw MP API response for
  every fetched material. Checked in so `mp-materials-rich.json` can be
  regenerated without re-hitting the API.
- `data/mess-parameters-lock.json` records the MESS-Parameters tag this
  dataset was generated against. Downstream consumers should compare
  against their own MESS-Parameters pin and flag drift.
- `data/pourbaix-results.json` contains per-mp_id raw Pourbaix verdicts
  before the kinetic-stability override is applied. Re-computation from
  these raw values is deterministic.
- `data/slug-to-mp.yaml` is the human-authored join file. All
  curation decisions (proxy assignments, composite compositions) live
  here.

## What MESS-Materials explicitly does NOT claim

1. That a "stable" Pourbaix verdict guarantees the material will work
   in a real MES reactor. Only that it is thermodynamically stable at
   the stated (E, pH) point.
2. That amorphous / proxy-tier values are accurate to within DFT error.
   Treat them as bulk-chemistry floors only.
3. That composite scores (EVS, BCS, LSS — shipped in v0.2) are
   calibrated against experimental MES performance. The composite
   weights are a first-principles Bayesian prior; refinement against
   the MESS-Parameters extraction corpus is planned.
4. That synthesizability is implied by thermodynamic stability. MP
   structures with `theoretical: true` have never been experimentally
   reported. None of the v0.1.0-pilot mappings use theoretical-only
   MP entries.

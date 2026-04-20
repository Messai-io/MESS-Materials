# MESS-Materials — Scientific Integrity

_Version: v0.2.0-pilot. Sibling to
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
   reported. The v0.1.0-pilot mappings used no theoretical-only
   entries; v0.2 adds one (`ti3c2tx_mxene → mp-1094034`, theoretical
   Ti3C2) with confidence_tier forced to `low` and the caveat
   surfaced in the record's `notes`.

---

## v0.2 additions (2026-04-20)

### Coverage expansion: 15 → 18 mapped slugs

v0.2 resolves the three TEMP-unmapped MXenes by mapping them to real
MP carbide structures as proxies:

- `ti3c2tx_mxene → mp-1094034` (Ti3C2 hexagonal, **theoretical**,
  above_hull=0.051 eV/atom). Real Ti3C2Tx MXene has disordered surface
  terminations (-OH, -F, -O) that crystalline DFT cannot capture.
  Flagged `confidence_tier: low`.
- `nb2ctx_mxene → mp-569989` (Nb2C orthorhombic, experimental ground
  state). Bulk carbide as proxy; etched MXene has layered morphology
  + Tx termination not represented.
- `v2ctx_mxene → mp-20648` (V2C orthorhombic, experimental). Same
  Tx caveat as Nb2C.

Remaining 8 unmapped slugs are polymer electrolytes, composite
descriptors, and one ceramic with composition ambiguity — all covered
in `data/unmapped-materials.json` with reasons.

### Pourbaix coverage for carbides

MP's Pourbaix diagram infrastructure throws
`ValueError: Composition of stability entry does not match Pourbaix
Diagram` for Ti3C2, Nb2C, V2C. The error reflects MP's coverage gap
for these chemsyses in the aqueous ion reference database, not a bug
in the pipeline. Records for all three MXenes carry
`state: "unknown"` at every MES operating point with an explicit
`notes` field stating the computation failed. Experimental MES
literature on MXene electrode stability is mixed — an "unknown" label
is the most honest representation of what the DFT pipeline can
conclude, absent independent experimental validation.

### Stainless-steel composite refinement

v0.1 mapped `stainless_steel` to mp-13 (Fe) alone with
`proxy: true`. That gave a defensible chemistry floor but
false-flagged "corroding" at every MES condition, because the
compute-pourbaix step's passivator override only sees the primary
component's elements (Fe) and not the alloy's Cr + Ni content.

v0.2 upgrades the mapping to a multi-component composite:
- `mp-13` (Fe, bulk_structure, proxy)
- `mp-90` (Cr, dopant, loading="18 wt%")
- `mp-23` (Ni, dopant, loading="10 wt%")

Plus a **composite passivator override** in the assembler that
re-checks `state == "corroding"` against the full component-element
set. The override upgrades to `passivated` with an explicit note
naming which passivators (Cr + Ni in this case) justify the
upgrade. See `scripts/assemble-rich-json.py:apply_composite_passivator_override`.

This is still a proxy, not a proper alloy DFT calculation. MP has no
canonical SS-304 or SS-316 structure at exact composition. Real
stainless also has trace C, Mn, Si, Mo (for SS-316) — not
represented. Consumers should still show "proxy" and "low-to-medium
confidence" treatment for stainless-steel entries.

### Tier 2 DFT fields (new)

**Elasticity** (from MP `elasticity` collection):
- `bulk_modulus_GPa`, `shear_modulus_GPa`, `youngs_modulus_GPa`,
  `poissons_ratio`, `universal_anisotropy`, `debye_temperature_K`.
- MP coverage: ~13k of 150k materials. For our 10 unique primary
  mp_ids, 7 have elasticity data; 3 miss (Co3O4, Fe3O4, MnO2 —
  transition-metal oxides are a known coverage gap).
- Downstream utility: bulk modulus < 50 GPa is a fragility flag for
  high-flow MES reactors. Pt (K=248), Fe (K=207), Ni (K=174), Nb2C
  (K=227), V2C (K=244) all qualify as "high durability"; graphite
  (K=116) is borderline.
- `youngs_modulus_GPa` is derived via E = 9KG/(3K+G) when MP doesn't
  surface it directly (common for the v0.2 dataset).
- All values from PBE GGA functional unless noted; r2SCAN migration
  for transition metal oxides is v0.3+ scope.

**Surface properties** (from MP `surface_properties` collection):
- `weighted_surface_energy_J_per_m2`, `work_function_eV`,
  `surface_anisotropy`, `shape_factor`, `has_reconstructed`.
- MP coverage: ~1k materials — same 3/10 oxide gap as elasticity,
  plus both MXenes (MP surface_properties does not cover the carbide
  phases). Net: 6/10 primary mp_ids have surface data.
- Pt work function = 5.54 eV matches the ~5.5-5.7 eV experimental
  ORR benchmark — confirms the data source is aligned with literature.
- Graphite surface energy = 0.019 J/m² reflects the basal plane; edge
  sites (which actually dominate real biofilm electrode chemistry)
  are not represented in a bulk crystal calculation. Amorphous-carbon
  proxy caveat compounds here.
- Surface energies from MP are facet-area-weighted averages. Per-facet
  detail is available in the raw cache under
  `data/mp-cache-surfaces/<mp_id>.json` (`surfaces` array) for
  consumers that need it; v0.2 schema exposes the weighted scalar only.

### Material ↔ paper cross-reference (novel MES capability)

The single most important v0.2 addition and the one no other
materials database can offer. For each mapped slug, joins the
MESS-Parameters corpus (`paper-metadata.csv`, ~23k papers) via the
`anode_materials` and `cathode_materials` columns.

**Coverage result:** 13 of 15 original v0.1 slugs have ≥1 paper; 11
of 15 have ≥3 papers. Exceeds the v0.2 plan's ≥70% exit threshold
(actual: 87%). Top coverage: `nickel_foam` (728), `iron_oxide` (556),
`copper_cathode` (390), `platinum_cathode` (303). Zero-paper slugs:
`cobalt_oxide` and `gas_diffusion_layer` — upstream extraction gap,
not an alias gap.

**Alias table caveats** (full table in
`scripts/build-paper-crossref.py`):
- The MESS-Parameters corpus has inconsistent raw strings ("Pt",
  "platinum", "['Pt']", "Pt/C"). Aliases are hand-curated; every
  non-trivial mapping decision is documented inline in the script.
- Ambiguous strings are intentionally **not** mapped. "carbon" (222
  occurrences) is the largest omission — could be carbon cloth,
  felt, paper, brush, or other. Mapping it to any single slug would
  silently inflate that slug's paper count. Better to leave it
  counted as unmapped and surface the gap to upstream curators.
- "graphite" (43) is mapped to `graphite_brush` as the only
  crystalline-graphite-based slug; reviewers can correct later if
  this proves wrong.

**Performance distributions** (power_output, efficiency) are emitted
only when ≥3 papers report the metric. Smaller samples return raw
values without a median (too few for a stable central-tendency
estimate; this mirrors the CoV discipline from MESS-Parameters'
own integrity doc).

**What this does and does not prove:** the cross-reference surfaces
which materials the MES literature has actually tested, and the
distribution of reported performance. It does **not** validate the
DFT predictions — a material with high paper count and good median
power does not retroactively justify its MESS-Materials scores.
Those are orthogonal signals. Consumers that want to validate DFT
predictions against experiment need a proper held-out comparison
study, not the corpus averages.

### Schema bump (0.1.0 → 0.2.0)

Additive only. Every v0.1.0 field remains unchanged. New optional
fields per material record: `elasticity`, `surface`,
`paper_cross_reference`. All nullable. Consumers pinned to v0.1.0
continue to work against older data; consumers bumping to v0.2.0
opt into the new fields with no required migration.

#!/usr/bin/env python3
"""
Step 3 of the Phase 1a pipeline.

For every unique mp_id referenced by `data/slug-to-mp.yaml`, compute
Pourbaix stability at the three canonical MES operating points:

    - MFC anode:    (-0.3 V vs SHE, pH 7)
    - MFC cathode:  (+0.2 V vs SHE, pH 7)
    - MEC cathode:  (-0.7 V vs SHE, pH 7)

Output: `data/pourbaix-results.json`, keyed by mp_id, with per-condition
{state, stable_phase, decomposition_energy_eV, notes}.

Passivator override: pymatgen's bare thermodynamic verdict for Ti, Al,
Cr, Ni is "corroding" at MES conditions, but these elements form
kinetically protective oxide layers. We rewrite `state=corroding` →
`state=passivated` for those elements and record the override in `notes`.
See SCIENTIFIC_INTEGRITY.md.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import yaml

from _common import (
    DATA_DIR,
    REPO_ROOT,
    load_env,
    require_mp_api_key,
)

SLUG_MAP_PATH = DATA_DIR / "slug-to-mp.yaml"
OUTPUT_PATH = DATA_DIR / "pourbaix-results.json"

MES_CONDITIONS = {
    "mfc_anode": {"potential_V_vs_SHE": -0.3, "pH": 7.0},
    "mfc_cathode": {"potential_V_vs_SHE": 0.2, "pH": 7.0},
    "mec_cathode": {"potential_V_vs_SHE": -0.7, "pH": 7.0},
}

# Elements whose pure / alloy forms are kinetically stable at MES
# conditions despite Pourbaix predicting thermodynamic corrosion. Two
# mechanisms share the same "passivated" label in output:
#   * Oxide passivation (Ti, Al, Cr, Ni, Ta, Zr): aqueous oxide layer
#     kinetically blocks further corrosion.
#   * Kinetic inertness (C): decomposition to CH4/HCO3- is thermodynamically
#     favored but prohibited without a catalyst at MES temperatures, so
#     graphite electrodes do not measurably corrode in practice.
# See SCIENTIFIC_INTEGRITY.md for the mechanism difference.
PASSIVATORS: set[str] = {"Ti", "Al", "Cr", "Ni", "Ta", "Zr", "C"}

PASSIVATION_MECHANISM: dict[str, str] = {
    "Ti": "aqueous TiO2 passivation layer",
    "Al": "aqueous Al2O3 passivation layer",
    "Cr": "aqueous Cr2O3 passivation layer",
    "Ni": "aqueous NiO passivation layer",
    "Ta": "aqueous Ta2O5 passivation layer",
    "Zr": "aqueous ZrO2 passivation layer",
    "C": "kinetic inertness (CH4/HCO3- reaction rate ≈ 0 at MES temperatures)",
}


def stability_for(pbx: Any, entry: Any, potential: float, ph: float) -> dict:
    """
    Evaluate a single (E, pH) point. Returns a dict matching the
    `pourbaixResult` schema definition.
    """
    decomp_energy = pbx.get_decomposition_energy(entry, pH=ph, V=potential)
    stable_entry = pbx.get_stable_entry(pH=ph, V=potential)
    stable_phase = str(stable_entry.entry.name) if stable_entry else None

    if decomp_energy < 1e-6:
        state = "stable"
        notes = None
    else:
        state = "corroding"
        notes = f"decomposes toward {stable_phase}"

    return {
        "state": state,
        "stable_phase": stable_phase,
        "decomposition_energy_eV": float(decomp_energy),
        "notes": notes,
    }


def apply_passivator_override(result: dict, elements: list[str]) -> dict:
    """
    If any element in the material is in PASSIVATORS and the raw verdict
    is corroding, upgrade to 'passivated' and record why.
    """
    if result["state"] != "corroding":
        return result
    passivating = [e for e in elements if e in PASSIVATORS]
    if not passivating:
        return result
    mechanisms = [
        f"{e}: {PASSIVATION_MECHANISM.get(e, 'known kinetic stability')}"
        for e in passivating
    ]
    return {
        **result,
        "state": "passivated",
        "notes": (
            f"kinetic-stability override ({', '.join(mechanisms)}); "
            f"thermodynamic Pourbaix says corroding toward "
            f"{result['stable_phase']}"
        ),
    }


def compute_for_material(mpr: Any, mp_id: str) -> dict:
    """Fetch Pourbaix entries for the material's chemsys and evaluate each condition."""
    from pymatgen.analysis.pourbaix_diagram import PourbaixDiagram

    summary = mpr.materials.summary.search(
        material_ids=[mp_id], fields=["material_id", "elements", "formula_pretty"]
    )
    if not summary:
        raise RuntimeError(f"No summary for {mp_id}")
    elements = [str(e) for e in summary[0].elements]

    # Skip rare/exotic chemsyses that MP doesn't have Pourbaix coverage for.
    # The API returns empty entries rather than erroring, so handle gracefully.
    entries = mpr.get_pourbaix_entries(elements)
    if not entries:
        return {
            mp_id: {
                "elements": elements,
                "pourbaix": {
                    cond: {"state": "unknown", "stable_phase": None, "decomposition_energy_eV": None, "notes": "MP has no Pourbaix coverage for this chemsys"}
                    for cond in MES_CONDITIONS
                },
            }
        }

    pbx = PourbaixDiagram(entries)

    # Resolve the SOLID PourbaixEntry for our material. Pourbaix diagrams
    # include both solid and ion phases; matching on entry_id alone picks
    # whichever comes first (often an ion), which gives misleading "stable"
    # verdicts when the stable species is actually a dissolved ion.
    target_formula = summary[0].formula_pretty
    solid_entries = [e for e in entries if getattr(e, "phase_type", None) == "Solid"]

    # Prefer exact mp_id match against the underlying ComputedEntry.
    target = next(
        (
            e
            for e in solid_entries
            if getattr(e.entry, "entry_id", None) == mp_id
            or mp_id in str(getattr(e, "entry_id", ""))
        ),
        None,
    )
    # Fall back to formula match among solids (handles cases where the
    # entry_id isn't surfaced on the wrapped ComputedEntry).
    if target is None:
        target = next(
            (
                e
                for e in solid_entries
                if e.composition.reduced_formula == target_formula
            ),
            None,
        )
    if target is None:
        return {
            mp_id: {
                "elements": elements,
                "pourbaix": {
                    cond: {"state": "unknown", "stable_phase": None, "decomposition_energy_eV": None, "notes": "target solid entry not present in Pourbaix diagram"}
                    for cond in MES_CONDITIONS
                },
            }
        }

    pourbaix = {}
    for cond_name, cond in MES_CONDITIONS.items():
        raw = stability_for(pbx, target, cond["potential_V_vs_SHE"], cond["pH"])
        pourbaix[cond_name] = apply_passivator_override(raw, elements)

    return {
        mp_id: {
            "elements": elements,
            "pourbaix": pourbaix,
        }
    }


def collect_mp_ids(slug_map: dict) -> set[str]:
    ids: set[str] = set()
    for entry in slug_map.get("materials", []):
        for component in entry.get("components", []):
            mp_id = component.get("mp_id")
            if mp_id:
                ids.add(mp_id)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Pourbaix stability at MES conditions for every mp_id in slug-to-mp.yaml"
    )
    parser.parse_args()

    load_env()
    api_key = require_mp_api_key()

    if not SLUG_MAP_PATH.exists():
        raise SystemExit(f"{SLUG_MAP_PATH.relative_to(REPO_ROOT)} not found")

    slug_map = yaml.safe_load(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    mp_ids = sorted(collect_mp_ids(slug_map))
    if not mp_ids:
        print("[compute-pourbaix] no mp_ids in slug-to-mp.yaml; nothing to do.")
        return

    from mp_api.client import MPRester

    results: dict = {
        "conditions": MES_CONDITIONS,
        "passivator_override_elements": sorted(PASSIVATORS),
        "materials": {},
    }

    with MPRester(api_key) as mpr:
        for mp_id in mp_ids:
            print(f"[compute-pourbaix] {mp_id}  ...")
            material_result = compute_for_material(mpr, mp_id)
            results["materials"].update(material_result)

    OUTPUT_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(
        f"[compute-pourbaix] wrote results for {len(mp_ids)} materials to "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT)}"
    )


if __name__ == "__main__":
    main()

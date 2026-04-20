#!/usr/bin/env python3
"""
Step 4 of the Phase 1a pipeline.

Joins:
  - data/slug-to-mp.yaml           (manual curation; slug → components)
  - data/mp-cache/<mp_id>.json     (fetch-mp.py output; per-mp_id Tier 1 DFT)
  - data/pourbaix-results.json     (compute-pourbaix.py output; per-mp_id stability)

Produces:
  - data/mp-materials-rich.json    (canonical sidecar payload, keyed by slug)
  - data/mess-parameters-lock.json (records MESS-Parameters tag + coverage stats)
  - data/unmapped-materials.json   (slugs not in slug-to-mp.yaml with reasons)

For composites (e.g. MnO2-on-carbon), Tier 1 scalar fields are
aggregated across components weighted by explicit `loading` when present,
else by equal weight. The primary component (role=bulk_structure or
role=catalyst for pure-catalyst slugs) supplies the CIF.

Validates the output against schemas/mp-material.schema.json.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator

from _common import (
    DATA_DIR,
    MP_CACHE_DIR,
    MESS_PARAMETERS_ROOT,
    REPO_ROOT,
    is_material_parameter,
    load_rich_parameters,
    slugify,
)

SLUG_MAP_PATH = DATA_DIR / "slug-to-mp.yaml"
POURBAIX_PATH = DATA_DIR / "pourbaix-results.json"
RICH_OUTPUT = DATA_DIR / "mp-materials-rich.json"
LOCK_OUTPUT = DATA_DIR / "mess-parameters-lock.json"
UNMAPPED_OUTPUT = DATA_DIR / "unmapped-materials.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "mp-material.schema.json"
ELASTICITY_CACHE = DATA_DIR / "mp-cache-elasticity"
SURFACES_CACHE = DATA_DIR / "mp-cache-surfaces"

SCHEMA_VERSION = "0.2.0"


def get_mess_parameters_tag() -> str | None:
    """Read the pinned tag from the sibling MESS-Parameters checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(MESS_PARAMETERS_ROOT), "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # fall back to short SHA
        sha = subprocess.run(
            ["git", "-C", str(MESS_PARAMETERS_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if sha.returncode == 0:
            return f"sha:{sha.stdout.strip()}"
    except FileNotFoundError:
        pass
    return None


def load_mp_cache(mp_id: str) -> dict:
    path = MP_CACHE_DIR / f"{mp_id}.json"
    if not path.exists():
        raise RuntimeError(
            f"MP cache miss for {mp_id}. Run `python scripts/fetch-mp.py` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_cache(cache_dir: Path, mp_id: str) -> dict | None:
    """Return cached doc or None if missing (sentinel or absent file)."""
    path = cache_dir / f"{mp_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("missing"):
        return None
    return data


def build_elasticity_block(mp_id: str) -> dict | None:
    """Translate raw MP elasticity doc → schema-shaped elasticity block."""
    raw = load_optional_cache(ELASTICITY_CACHE, mp_id)
    if raw is None:
        return None

    def vrh_scalar(field: str) -> float | None:
        val = raw.get(field)
        if isinstance(val, dict):
            return val.get("vrh")
        return val

    bulk = vrh_scalar("bulk_modulus")
    shear = vrh_scalar("shear_modulus")
    youngs = raw.get("youngs_modulus")
    if youngs is None and bulk is not None and shear is not None and (3 * bulk + shear) > 0:
        # Derived relation E = 9KG / (3K + G)
        youngs = (9 * bulk * shear) / (3 * bulk + shear)

    return {
        "bulk_modulus_GPa": bulk,
        "shear_modulus_GPa": shear,
        "youngs_modulus_GPa": youngs,
        "poissons_ratio": raw.get("homogeneous_poisson"),
        "universal_anisotropy": raw.get("universal_anisotropy"),
        "debye_temperature_K": raw.get("debye_temperature"),
        "source_functional": "PBE",
    }


def build_surface_block(mp_id: str) -> dict | None:
    """Translate raw MP surface-properties doc → schema-shaped surface block."""
    raw = load_optional_cache(SURFACES_CACHE, mp_id)
    if raw is None:
        return None
    return {
        "weighted_surface_energy_J_per_m2": raw.get("weighted_surface_energy"),
        "work_function_eV": raw.get("weighted_work_function"),
        "surface_anisotropy": raw.get("surface_anisotropy"),
        "shape_factor": raw.get("shape_factor"),
        "has_reconstructed": raw.get("has_reconstructed"),
        "source_functional": "PBE",
    }


def weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    """
    values: list of (value, weight). Drops entries with value=None.
    Returns None if no valid values.
    """
    pairs = [(v, w) for v, w in values if v is not None and w > 0]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w == 0:
        return None
    return sum(v * w for v, w in pairs) / total_w


def parse_loading(loading: str | None) -> float:
    """
    Parse strings like '10 wt%', '0.5', '50' → fraction weight. Unknown
    inputs return 1.0 (equal weight).
    """
    if not loading:
        return 1.0
    s = loading.strip().lower().replace("%", "").replace("wt", "").strip()
    try:
        v = float(s)
        return v / 100.0 if v > 1.0 else v
    except ValueError:
        return 1.0


def assemble_material(entry: dict, pourbaix_all: dict) -> dict:
    slug = entry["slug"]
    components_yaml = entry.get("components") or []
    if not components_yaml:
        raise RuntimeError(f"slug '{slug}' has no components")

    # Resolve each component against the MP cache
    resolved_components = []
    weighted_fields: dict[str, list[tuple[float | None, float]]] = {
        "band_gap_eV": [],
        "formation_energy_eV_per_atom": [],
        "energy_above_hull_eV_per_atom": [],
        "density_g_per_cm3": [],
        "total_magnetization_uB": [],
    }
    any_metal = False
    all_metal = True
    primary_cif: str | None = None

    for comp_yaml in components_yaml:
        mp_id = comp_yaml["mp_id"]
        role = comp_yaml["role"]
        loading_str = comp_yaml.get("loading")
        proxy = bool(comp_yaml.get("proxy", False))
        weight = parse_loading(loading_str)

        mp_doc = load_mp_cache(mp_id)
        formula = mp_doc.get("formula_pretty")

        is_metal = mp_doc.get("is_metal")
        if is_metal is True:
            any_metal = True
        elif is_metal is False:
            all_metal = False
        else:
            all_metal = False  # unknown treated as non-metal for conservative 'is_metal'

        weighted_fields["band_gap_eV"].append((mp_doc.get("band_gap"), weight))
        weighted_fields["formation_energy_eV_per_atom"].append(
            (mp_doc.get("formation_energy_per_atom"), weight)
        )
        weighted_fields["energy_above_hull_eV_per_atom"].append(
            (mp_doc.get("energy_above_hull"), weight)
        )
        weighted_fields["density_g_per_cm3"].append((mp_doc.get("density"), weight))
        weighted_fields["total_magnetization_uB"].append(
            (mp_doc.get("total_magnetization"), weight)
        )

        if role == "bulk_structure" and primary_cif is None:
            primary_cif = mp_doc.get("structure_cif")

        resolved_components.append(
            {
                "mp_id": mp_id,
                "role": role,
                "loading": loading_str,
                "proxy": proxy,
                "formula": formula,
            }
        )

    # Use first component's CIF as fallback if no bulk_structure role declared
    if primary_cif is None and resolved_components:
        primary_cif = load_mp_cache(resolved_components[0]["mp_id"]).get("structure_cif")

    # Pourbaix: use the primary component's (first bulk_structure, else first listed)
    primary_mp_id = next(
        (c["mp_id"] for c in resolved_components if c["role"] == "bulk_structure"),
        resolved_components[0]["mp_id"],
    )
    pourbaix_entry = pourbaix_all.get("materials", {}).get(primary_mp_id, {}).get("pourbaix")
    if pourbaix_entry is None:
        pourbaix_entry = {
            "mfc_anode": {"state": "unknown", "stable_phase": None, "decomposition_energy_eV": None, "notes": "Pourbaix not yet computed for primary component"},
            "mfc_cathode": {"state": "unknown", "stable_phase": None, "decomposition_energy_eV": None, "notes": "Pourbaix not yet computed for primary component"},
            "mec_cathode": {"state": "unknown", "stable_phase": None, "decomposition_energy_eV": None, "notes": "Pourbaix not yet computed for primary component"},
        }

    # Assign confidence tier
    tier = entry.get("confidence_tier_override")
    if tier is None:
        any_proxy = any(c.get("proxy") for c in resolved_components)
        if any_proxy:
            tier = "low"
        elif len(resolved_components) > 1:
            tier = "medium"
        else:
            tier = "high"

    return {
        "slug": slug,
        "components": resolved_components,
        "confidence_tier": tier,
        "mp_snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "mp_functional_default": "PBE",
        "band_gap_eV": weighted_average(weighted_fields["band_gap_eV"]),
        "is_metal": (all_metal and any_metal) if resolved_components else None,
        "formation_energy_eV_per_atom": weighted_average(weighted_fields["formation_energy_eV_per_atom"]),
        "energy_above_hull_eV_per_atom": weighted_average(weighted_fields["energy_above_hull_eV_per_atom"]),
        "density_g_per_cm3": weighted_average(weighted_fields["density_g_per_cm3"]),
        "total_magnetization_uB": weighted_average(weighted_fields["total_magnetization_uB"]),
        "pourbaix": pourbaix_entry,
        "structure_cif": primary_cif,
        "elasticity": build_elasticity_block(primary_mp_id),
        "surface": build_surface_block(primary_mp_id),
        "notes": entry.get("notes"),
    }


def main() -> None:
    if not SLUG_MAP_PATH.exists():
        raise SystemExit(f"{SLUG_MAP_PATH.relative_to(REPO_ROOT)} not found")

    slug_map = yaml.safe_load(SLUG_MAP_PATH.read_text(encoding="utf-8")) or {}
    pourbaix_all = (
        json.loads(POURBAIX_PATH.read_text(encoding="utf-8")) if POURBAIX_PATH.exists() else {"materials": {}}
    )

    mapped_materials = []
    mapped_slugs: set[str] = set()
    for entry in slug_map.get("materials", []):
        record = assemble_material(entry, pourbaix_all)
        mapped_materials.append(record)
        mapped_slugs.add(record["slug"])

    # Unmapped MESS-Parameters material slugs
    rich = load_rich_parameters()
    all_material_slugs = {slugify(p["name"]) for p in rich if is_material_parameter(p)}
    unmapped_slugs = all_material_slugs - mapped_slugs

    # Unmapped entries from slug-to-mp.yaml's explicit list
    unmapped_declared = slug_map.get("unmapped", [])
    declared_slugs = {u["slug"] for u in unmapped_declared}
    undeclared_gap = unmapped_slugs - declared_slugs
    if undeclared_gap:
        raise SystemExit(
            f"Undeclared slugs (not in slug-to-mp.yaml and not in its `unmapped` list): "
            f"{sorted(undeclared_gap)}. "
            "Every MESS-Parameters material slug must be mapped or explicitly unmapped."
        )

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mess_parameters_tag": get_mess_parameters_tag(),
        "materials": mapped_materials,
    }

    validator = Draft7Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = sorted(validator.iter_errors(envelope), key=lambda e: e.path)
    if errors:
        for err in errors:
            print(f"[assemble] schema error: {list(err.path)} → {err.message}")
        raise SystemExit("rich.json failed schema validation; aborting.")

    RICH_OUTPUT.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    lock = {
        "mess_parameters_tag": envelope["mess_parameters_tag"],
        "mapped_slugs": len(mapped_slugs),
        "unmapped_slugs": len(unmapped_declared),
        "total_material_slugs": len(all_material_slugs),
        "generated_at": envelope["generated_at"],
    }
    LOCK_OUTPUT.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    UNMAPPED_OUTPUT.write_text(json.dumps({"unmapped": unmapped_declared}, indent=2) + "\n", encoding="utf-8")

    print(
        f"[assemble] ok — mapped={len(mapped_slugs)} unmapped={len(unmapped_declared)} "
        f"total_slugs={len(all_material_slugs)} tag={envelope['mess_parameters_tag']}"
    )


if __name__ == "__main__":
    main()

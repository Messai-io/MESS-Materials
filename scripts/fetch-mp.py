#!/usr/bin/env python3
"""
Step 2 of the Phase 1a pipeline.

Reads `data/slug-to-mp.yaml` (manual curation) and fetches Tier 1
properties from the Materials Project for each referenced mp_id:

    band_gap, is_metal, formation_energy_per_atom, energy_above_hull,
    density, total_magnetization, symmetry, volume, formula, structure (CIF)

Raw responses are cached under `data/mp-cache/<mp_id>.json` and checked
in for reproducibility. Re-runs hit the cache unless --refresh is passed.

Requires MP_API_KEY in .env (or environment). Rate limit on the free
tier: ~1000 requests/day; this step touches at most 26 unique mp_ids
for v0.1.0-pilot so it's well under the ceiling.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from _common import (
    DATA_DIR,
    MP_CACHE_DIR,
    REPO_ROOT,
    load_env,
    require_mp_api_key,
)

SLUG_MAP_PATH = DATA_DIR / "slug-to-mp.yaml"

TIER1_FIELDS = [
    "material_id",
    "formula_pretty",
    "elements",
    "band_gap",
    "is_metal",
    "formation_energy_per_atom",
    "energy_above_hull",
    "density",
    "total_magnetization",
    "symmetry",
    "volume",
    "nsites",
    "theoretical",
    "structure",
]


def collect_mp_ids(slug_map: dict) -> set[str]:
    ids: set[str] = set()
    for entry in slug_map.get("materials", []):
        for component in entry.get("components", []):
            mp_id = component.get("mp_id")
            if mp_id:
                ids.add(mp_id)
    return ids


def cache_path(mp_id: str) -> Path:
    return MP_CACHE_DIR / f"{mp_id}.json"


def serialize_mp_doc(doc: Any) -> dict:
    """Convert an MP summary doc to a JSON-safe dict.

    emmet-core documents are Pydantic models; structures contain numpy
    arrays and Element objects. We convert structure → CIF string and
    rely on pymatgen's MontyEncoder-compatible dict for the rest.
    """
    from monty.json import MontyEncoder  # bundled with pymatgen

    raw = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)

    # Structure → CIF text (durable, human-readable, smaller than MSON)
    structure = raw.pop("structure", None)
    cif_text = None
    if structure is not None:
        from pymatgen.io.cif import CifWriter

        # doc.structure is still the live object; use it before serialization
        try:
            cif_text = str(CifWriter(doc.structure))
        except Exception:
            cif_text = None

    # symmetry / composition etc. may still contain Element objects — encode via Monty
    raw_json = json.dumps(raw, cls=MontyEncoder)
    normalized = json.loads(raw_json)
    normalized["structure_cif"] = cif_text
    return normalized


def fetch_one(mpr: Any, mp_id: str) -> dict:
    docs = mpr.materials.summary.search(material_ids=[mp_id], fields=TIER1_FIELDS)
    if not docs:
        raise RuntimeError(f"No MP summary returned for {mp_id}")
    return serialize_mp_doc(docs[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Tier 1 MP properties for all mp_ids in slug-to-mp.yaml")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cache and re-fetch every mp_id.",
    )
    args = parser.parse_args()

    load_env()
    api_key = require_mp_api_key()

    if not SLUG_MAP_PATH.exists():
        raise SystemExit(
            f"{SLUG_MAP_PATH.relative_to(REPO_ROOT)} not found. "
            "Create it from the template — this is the manual curation file "
            "mapping MESS-Parameters slugs to MP material_ids."
        )

    slug_map = yaml.safe_load(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    mp_ids = collect_mp_ids(slug_map)
    if not mp_ids:
        print("[fetch-mp] slug-to-mp.yaml has no components with mp_id; nothing to do.")
        return

    MP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Import mp-api lazily so the rest of the pipeline can run without the
    # Materials Project SDK installed (e.g. in CI that only does schema checks).
    from mp_api.client import MPRester

    fetched = 0
    cached = 0
    with MPRester(api_key) as mpr:
        for mp_id in sorted(mp_ids):
            cp = cache_path(mp_id)
            if cp.exists() and not args.refresh:
                cached += 1
                continue
            try:
                doc = fetch_one(mpr, mp_id)
                cp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
                fetched += 1
                print(f"[fetch-mp] {mp_id}  ok  ({doc.get('formula_pretty')})")
            except Exception as exc:  # noqa: BLE001
                print(f"[fetch-mp] {mp_id}  FAIL  {exc}")
                raise

    print(
        f"[fetch-mp] done — fetched={fetched} cached={cached} total={len(mp_ids)} "
        f"cache_dir={MP_CACHE_DIR.relative_to(REPO_ROOT)}/"
    )


if __name__ == "__main__":
    main()

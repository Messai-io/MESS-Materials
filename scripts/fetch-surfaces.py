#!/usr/bin/env python3
"""
v0.2 — Tier 2 surface-properties fetcher.

For every unique mp_id referenced by `data/slug-to-mp.yaml`, pull the
MP surface-properties fields relevant to MES:

    weighted_surface_energy (J/m²) — biofilm adhesion proxy
    weighted_work_function (eV)    — ORR/OER catalyst activity proxy
    surface_anisotropy, shape_factor, has_reconstructed
    per-facet surfaces array (for materials that warrant facet-level detail)

Raw responses cached under `data/mp-cache-surfaces/<mp_id>.json` for
reproducibility. Re-runs hit the cache unless --refresh is passed.

Coverage: MP surface properties are available for ~1k materials. Expect
holes — in particular for transition-metal-oxide phases. Missing = null
fields downstream, no substitution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from _common import (
    DATA_DIR,
    REPO_ROOT,
    load_env,
    require_mp_api_key,
)

SLUG_MAP_PATH = DATA_DIR / "slug-to-mp.yaml"
CACHE_DIR = DATA_DIR / "mp-cache-surfaces"

SURFACE_FIELDS = [
    "material_id",
    "pretty_formula",
    "has_reconstructed",
    "weighted_surface_energy",
    "weighted_surface_energy_EV_PER_ANG2",
    "weighted_work_function",
    "surface_anisotropy",
    "shape_factor",
    "surfaces",
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
    return CACHE_DIR / f"{mp_id}.json"


def serialize_doc(doc: Any) -> dict:
    from monty.json import MontyEncoder

    raw = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
    # Drop anything that isn't a scalar or nested primitive via MontyEncoder
    return json.loads(json.dumps(raw, cls=MontyEncoder, default=str))


def fetch_one(mpr: Any, mp_id: str) -> dict | None:
    docs = mpr.materials.surface_properties.search(
        material_ids=[mp_id], fields=SURFACE_FIELDS
    )
    if not docs:
        return None
    return serialize_doc(docs[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch MP surface properties for every mp_id in slug-to-mp.yaml"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cache and re-fetch every mp_id.",
    )
    args = parser.parse_args()

    load_env()
    api_key = require_mp_api_key()

    if not SLUG_MAP_PATH.exists():
        raise SystemExit(f"{SLUG_MAP_PATH.relative_to(REPO_ROOT)} not found")

    slug_map = yaml.safe_load(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    mp_ids = sorted(collect_mp_ids(slug_map))
    if not mp_ids:
        print("[fetch-surfaces] no mp_ids in slug-to-mp.yaml; nothing to do.")
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    from mp_api.client import MPRester

    fetched = 0
    cached = 0
    missing = 0
    with MPRester(api_key) as mpr:
        for mp_id in mp_ids:
            cp = cache_path(mp_id)
            if cp.exists() and not args.refresh:
                cached += 1
                continue
            try:
                doc = fetch_one(mpr, mp_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[fetch-surfaces] {mp_id}  FAIL  {exc}")
                raise
            if doc is None:
                cp.write_text(json.dumps({"material_id": mp_id, "missing": True}) + "\n", encoding="utf-8")
                missing += 1
                print(f"[fetch-surfaces] {mp_id}  MISS  (no MP surface entry)")
                continue
            cp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            fetched += 1
            w_surf = doc.get("weighted_surface_energy")
            w_wf = doc.get("weighted_work_function")
            print(
                f"[fetch-surfaces] {mp_id}  ok  "
                f"(w_surf={w_surf:.3f} J/m²  w_wf={w_wf:.3f} eV)"
                if w_surf is not None and w_wf is not None
                else f"[fetch-surfaces] {mp_id}  ok  (partial)"
            )

    print(
        f"[fetch-surfaces] done — fetched={fetched} cached={cached} "
        f"missing={missing} total={len(mp_ids)} "
        f"cache_dir={CACHE_DIR.relative_to(REPO_ROOT)}/"
    )


if __name__ == "__main__":
    main()

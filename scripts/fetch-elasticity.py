#!/usr/bin/env python3
"""
v0.2 — Tier 2 elasticity fetcher.

For every unique mp_id referenced by `data/slug-to-mp.yaml`, pull the
MP elasticity tensor fields relevant to MES mechanical durability:

    bulk_modulus (K_VRH), shear_modulus (G_VRH), youngs_modulus (derived),
    homogeneous_poisson, universal_anisotropy, debye_temperature.

Raw responses cached under `data/mp-cache-elasticity/<mp_id>.json` for
reproducibility. Re-runs hit the cache unless --refresh is passed.

Coverage note: MP elasticity is ~13k materials out of 150k. Expect
some misses — in particular for theoretical-only entries and some
oxide phases. Missing = null fields in the downstream rich.json, no
fallback or substitution.
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
CACHE_DIR = DATA_DIR / "mp-cache-elasticity"

# Fields we actually surface. MP's elasticity doc has many more, but
# these are the ones we turn into schema fields in the v0.2 bump.
ELASTICITY_FIELDS = [
    "material_id",
    "bulk_modulus",
    "shear_modulus",
    "youngs_modulus",
    "homogeneous_poisson",
    "universal_anisotropy",
    "debye_temperature",
    "state",
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


def extract_scalar(doc: Any, key: str) -> float | dict | None:
    """
    MP elasticity sometimes returns a dict with VRH/Voigt/Reuss entries
    (bulk_modulus, shear_modulus), sometimes a plain float (youngs_modulus),
    sometimes None. Normalize to a single average scalar while also
    preserving the full breakdown for audit.
    """
    val = getattr(doc, key, None)
    if val is None:
        return None
    # Pydantic model → plain dict
    if hasattr(val, "model_dump"):
        val = val.model_dump()
    return val


def serialize_doc(doc: Any) -> dict:
    """Reduce the elasticity doc to the fields we care about, JSON-safe."""
    from monty.json import MontyEncoder

    result: dict = {}
    for key in ELASTICITY_FIELDS:
        raw = extract_scalar(doc, key)
        # Enums (TaskState), nested Pydantic leftovers → round-trip
        # through MontyEncoder to get plain JSON types.
        if raw is not None and not isinstance(raw, (int, float, str, bool, list, dict)):
            raw = json.loads(json.dumps(raw, cls=MontyEncoder))
        result[key] = raw
    return result


def fetch_one(mpr: Any, mp_id: str) -> dict | None:
    """Return the serialized elasticity doc, or None if MP has no entry."""
    docs = mpr.materials.elasticity.search(
        material_ids=[mp_id], fields=ELASTICITY_FIELDS
    )
    if not docs:
        return None
    return serialize_doc(docs[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch MP elasticity tensors for every mp_id in slug-to-mp.yaml"
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
        raise SystemExit(
            f"{SLUG_MAP_PATH.relative_to(REPO_ROOT)} not found"
        )

    slug_map = yaml.safe_load(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    mp_ids = sorted(collect_mp_ids(slug_map))
    if not mp_ids:
        print("[fetch-elasticity] no mp_ids in slug-to-mp.yaml; nothing to do.")
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
                print(f"[fetch-elasticity] {mp_id}  FAIL  {exc}")
                raise
            if doc is None:
                # Write a sentinel so re-runs don't re-query materials
                # we already know MP has no data for.
                cp.write_text(json.dumps({"material_id": mp_id, "missing": True}) + "\n", encoding="utf-8")
                missing += 1
                print(f"[fetch-elasticity] {mp_id}  MISS  (no MP elasticity entry)")
                continue
            cp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            fetched += 1
            k = doc.get("bulk_modulus")
            k_label = k.get("vrh") if isinstance(k, dict) else k
            print(f"[fetch-elasticity] {mp_id}  ok  (K_VRH={k_label})")

    print(
        f"[fetch-elasticity] done — fetched={fetched} cached={cached} "
        f"missing={missing} total={len(mp_ids)} "
        f"cache_dir={CACHE_DIR.relative_to(REPO_ROOT)}/"
    )


if __name__ == "__main__":
    main()

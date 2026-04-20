#!/usr/bin/env python3
"""
Step 1 of the Phase 1a pipeline.

Reads MESS-Parameters' canonical rich.json (pinned submodule) and emits
`data/mess-material-slugs.json` — the list of parameter slugs that
represent material-like entities (MATERIALS category, OBJECT data_type).

This is the vocabulary MESS-Materials commits to covering. Every slug
here must appear in either `data/slug-to-mp.yaml` (mapped to MP) or
`data/unmapped-materials.json` (explicitly unmapped with a reason) —
CI enforces the invariant.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from _common import (
    DATA_DIR,
    is_material_parameter,
    load_rich_parameters,
    slugify,
)


def main() -> None:
    rich = load_rich_parameters()
    materials = [p for p in rich if is_material_parameter(p)]

    slugs = []
    for p in sorted(materials, key=lambda x: -(x.get("usage_count") or 0)):
        slugs.append(
            {
                "slug": slugify(p["name"]),
                "name": p["name"],
                "subcategory": p.get("subcategory"),
                "usage_count": p.get("usage_count") or 0,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mess_parameters_source": "open-source/MESS-Parameters/data/parameter-definitions-rich.json",
        "filter": "category==MATERIALS and data_type==OBJECT",
        "count": len(slugs),
        "slugs": slugs,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "mess-material-slugs.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[extract-mes-material-slugs] wrote {len(slugs)} slugs to {out.relative_to(out.parent.parent)}")


if __name__ == "__main__":
    main()

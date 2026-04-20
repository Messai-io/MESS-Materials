#!/usr/bin/env python3
"""
v0.2 — Material ↔ paper cross-reference builder.

This is the MES-specific novel capability: joins each mapped slug in
slug-to-mp.yaml to every paper in the MESS-Parameters corpus that
reports using the material. For papers that also carry performance
metrics (power_output, efficiency), aggregate distributions per slug.

Inputs (all from the pinned MESS-Parameters submodule):
- data/paper-metadata.csv              paper DOI, title, year, system_type,
                                       anode_materials, cathode_materials,
                                       power_output, efficiency, citation_count
- data/paper-parameter-values.csv      per-paper parameter rows, used for
                                       performance distributions

Outputs:
- data/material-paper-crossref.json    per-slug paper list + perf summary
- stdout: coverage report

Alias handling: raw material strings in MESS-Parameters paper metadata
are inconsistent ("Pt", "platinum", '["Pt"]'). We normalize via a
hand-curated alias table (§ALIASES) and document every non-trivial
mapping decision in the output file so downstream consumers can audit.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import (
    DATA_DIR,
    MESS_PARAMETERS_ROOT,
    REPO_ROOT,
    slugify,
)

PAPER_META_CSV = MESS_PARAMETERS_ROOT / "data" / "paper-metadata.csv"
PAPER_VALUES_CSV = MESS_PARAMETERS_ROOT / "data" / "paper-parameter-values.csv"
OUTPUT_PATH = DATA_DIR / "material-paper-crossref.json"


# Hand-curated aliases: raw paper-metadata string → MESS-Materials slug.
# Multiple raw forms may map to the same slug. Unknown strings are
# skipped (and reported in coverage stats).
ALIASES: dict[str, str] = {
    # Platinum family → platinum_cathode
    "pt": "platinum_cathode",
    "platinum": "platinum_cathode",
    "pt/c": "platinum_cathode",
    "platinum on carbon": "platinum_cathode",
    # Copper family → copper_cathode
    "cu": "copper_cathode",
    "copper": "copper_cathode",
    # Nickel family → nickel_foam (our only Ni slug; crude proxy when
    # the paper doesn't specify foam morphology)
    "ni": "nickel_foam",
    "nickel": "nickel_foam",
    "nickel foam": "nickel_foam",
    # Stainless steel
    "stainless steel": "stainless_steel",
    "stainless": "stainless_steel",
    "ss": "stainless_steel",
    # Iron / iron oxide → iron_oxide (proxying pure Fe rarely occurs
    # outside electrochemistry; most Fe mentions refer to oxide phases)
    "fe": "iron_oxide",
    "iron": "iron_oxide",
    "iron oxide": "iron_oxide",
    "fe3o4": "iron_oxide",
    "fe2o3": "iron_oxide",
    "magnetite": "iron_oxide",
    "hematite": "iron_oxide",
    # Manganese oxide
    "mno2": "manganese_oxide",
    "manganese dioxide": "manganese_oxide",
    "manganese oxide": "manganese_oxide",
    "mn": "manganese_oxide",
    # Cobalt oxide
    "co": "cobalt_oxide",
    "co3o4": "cobalt_oxide",
    "cobalt oxide": "cobalt_oxide",
    "cobalt": "cobalt_oxide",
    # Carbon family — exact-slug matches
    "carbon cloth": "carbon_cloth",
    "carbon felt": "carbon_felt",
    "carbon paper": "carbon_paper",
    "activated carbon": "activated_carbon",
    "gas diffusion layer": "gas_diffusion_layer",
    "gdl": "gas_diffusion_layer",
    # Carbon-brush family → graphite_brush
    "graphite brush": "graphite_brush",
    "carbon brush": "graphite_brush",
    "graphite rod": "graphite_brush",
    "graphite felt": "carbon_felt",  # gray area; graphite felt is close to carbon felt
    "graphite plate": "graphite_brush",
    "graphite": "graphite_brush",  # ambiguous; defaulting to graphite_brush as
                                    # the only crystalline-graphite-based slug
    # Carbon nanotubes
    "carbon nanotube": "carbon_nanotubes",
    "carbon nanotubes": "carbon_nanotubes",
    "cnt": "carbon_nanotubes",
    "mwnt": "carbon_nanotubes",
    "mwcnt": "carbon_nanotubes",
    "swnt": "carbon_nanotubes",
    # Graphene / graphene oxide → graphene_oxide
    "graphene": "graphene_oxide",
    "rgo": "graphene_oxide",
    "reduced graphene oxide": "graphene_oxide",
    "go": "graphene_oxide",
    "graphene oxide": "graphene_oxide",
    # Gold, Ti, biochar, polypyrrole, carbon rod, carbon fiber,
    # carbon black intentionally NOT mapped — either they have no
    # matching slug or conflating them with an existing slug would
    # be misleading. They show up in the "unmapped raw materials"
    # tally so upstream curators can decide whether to add slugs.
}


# System_type → canonical label (strip noise)
SYSTEM_TYPE_CANONICAL = {
    "MFC": "MFC",
    "MEC": "MEC",
    "MDC": "MDC",
    "MES": "MES",
    "BES": "BES",
}


def parse_material_field(raw: str) -> list[str]:
    """
    The anode_materials / cathode_materials fields come in three shapes:
        - empty string
        - single raw value ("carbon felt")
        - JSON array string ('["Pt","Cu"]')
    Normalize to a list of lowercased trimmed strings.
    """
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip().lower() for x in items if x]
        except json.JSONDecodeError:
            pass
    # Plain string, possibly comma-separated
    return [p.strip().lower() for p in re.split(r",\s*", raw) if p.strip()]


def normalize_numeric(value: str) -> float | None:
    """Extract a numeric value from a CSV cell; returns None for blanks."""
    if not value or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def summarize_performance(values: list[float]) -> dict | None:
    if len(values) < 3:
        return {
            "n": len(values),
            "values": values,  # keep raw for small samples
        }
    values_sorted = sorted(values)
    return {
        "n": len(values),
        "min": min(values_sorted),
        "max": max(values_sorted),
        "median": statistics.median(values_sorted),
        "mean": statistics.mean(values_sorted),
        "stdev": statistics.stdev(values_sorted) if len(values_sorted) > 1 else 0.0,
        "p10": values_sorted[int(0.1 * (len(values_sorted) - 1))],
        "p90": values_sorted[int(0.9 * (len(values_sorted) - 1))],
    }


def main() -> None:
    if not PAPER_META_CSV.exists() or not PAPER_VALUES_CSV.exists():
        raise SystemExit(
            "MESS-Parameters corpus CSVs not found. Ensure the submodule "
            "is checked out at open-source/MESS-Parameters/"
        )

    # Collect slug → list of paper records (DOI + metadata)
    papers_by_slug: dict[str, list[dict]] = defaultdict(list)
    raw_string_counts: dict[str, int] = defaultdict(int)
    raw_unmapped_counts: dict[str, int] = defaultdict(int)
    papers_seen_per_slug: dict[str, set[str]] = defaultdict(set)

    total_papers = 0
    papers_with_materials = 0

    with open(PAPER_META_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            total_papers += 1
            doi = (row.get("doi") or "").strip()
            if not doi:
                continue
            anodes = parse_material_field(row.get("anode_materials", ""))
            cathodes = parse_material_field(row.get("cathode_materials", ""))
            all_materials = {m for m in anodes + cathodes if m}
            if not all_materials:
                continue
            papers_with_materials += 1

            power = normalize_numeric(row.get("power_output", ""))
            efficiency = normalize_numeric(row.get("efficiency", ""))
            citation = normalize_numeric(row.get("citation_count", ""))
            year = row.get("year", "").strip()

            for raw in all_materials:
                raw_string_counts[raw] += 1
                slug = ALIASES.get(raw)
                if slug is None:
                    raw_unmapped_counts[raw] += 1
                    continue
                # Deduplicate paper-per-slug (a paper that lists Pt on
                # both anode and cathode shouldn't double-count).
                if doi in papers_seen_per_slug[slug]:
                    continue
                papers_seen_per_slug[slug].add(doi)
                papers_by_slug[slug].append(
                    {
                        "doi": doi,
                        "title": (row.get("title") or "").strip(),
                        "year": year,
                        "journal": (row.get("journal") or "").strip(),
                        "system_type": SYSTEM_TYPE_CANONICAL.get(
                            row.get("system_type", ""), row.get("system_type", "")
                        ),
                        "anode_materials": anodes,
                        "cathode_materials": cathodes,
                        "power_output": power,
                        "efficiency": efficiency,
                        "citation_count": citation,
                    }
                )

    # Build per-slug summaries
    per_slug_summary: dict[str, dict] = {}
    for slug, papers in papers_by_slug.items():
        powers = [p["power_output"] for p in papers if p["power_output"] is not None]
        efficiencies = [p["efficiency"] for p in papers if p["efficiency"] is not None]
        years = [int(p["year"]) for p in papers if p["year"].isdigit()]
        system_types: dict[str, int] = defaultdict(int)
        for p in papers:
            if p["system_type"]:
                system_types[p["system_type"]] += 1

        per_slug_summary[slug] = {
            "paper_count": len(papers),
            "year_range": [min(years), max(years)] if years else None,
            "system_type_distribution": dict(system_types),
            "power_output_summary": summarize_performance(powers),
            "efficiency_summary": summarize_performance(efficiencies),
            # Keep full paper list (DOIs + title + year) for downstream
            # UI "see all papers" links; cap at 100 per slug to keep
            # fixture sizes reasonable.
            "papers": sorted(
                papers,
                key=lambda p: (p.get("citation_count") or 0),
                reverse=True,
            )[:100],
        }

    # Coverage report for SCIENTIFIC_INTEGRITY
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mess_parameters_source": {
            "paper_metadata_csv": str(PAPER_META_CSV.relative_to(MESS_PARAMETERS_ROOT.parent)),
            "total_papers_in_corpus": total_papers,
            "papers_with_material_fields": papers_with_materials,
        },
        "alias_table_summary": {
            "aliases_defined": len(ALIASES),
            "top_unmapped_raw_strings": sorted(
                raw_unmapped_counts.items(), key=lambda x: -x[1]
            )[:20],
        },
        "per_slug": per_slug_summary,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"[build-paper-crossref] wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  corpus papers = {total_papers}")
    print(f"  papers with material metadata = {papers_with_materials}")
    print("  per-slug paper counts:")
    for slug in sorted(per_slug_summary.keys()):
        s = per_slug_summary[slug]
        pc = s["paper_count"]
        pwr = s["power_output_summary"]
        pwr_n = pwr.get("n", 0) if pwr else 0
        print(f"    {slug:25s} papers={pc:5d}  with_power={pwr_n}")
    print("  top unmapped raw strings (consider adding to ALIASES):")
    for raw, n in out["alias_table_summary"]["top_unmapped_raw_strings"][:8]:
        print(f"    {n:5d}  {raw}")


if __name__ == "__main__":
    main()

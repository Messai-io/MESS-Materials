"""
Shared helpers for the MESS-Materials Phase 1a pipeline.

Responsibilities:
- Locate the pinned MESS-Parameters submodule (sibling clone under
  ../MESS-Parameters) relative to this repo.
- Slug derivation that matches messai-ai's
  `apps/web/src/utils/parameter-slug.ts` exactly.
- .env loading for MP_API_KEY.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
MESS_PARAMETERS_ROOT = REPO_ROOT.parent / "MESS-Parameters"
MESS_PARAMETERS_RICH_JSON = (
    MESS_PARAMETERS_ROOT / "data" / "parameter-definitions-rich.json"
)
DATA_DIR = REPO_ROOT / "data"
MP_CACHE_DIR = DATA_DIR / "mp-cache"


def load_env() -> None:
    """Load .env from the repo root. Call once at script entry."""
    load_dotenv(REPO_ROOT / ".env")


def require_mp_api_key() -> str:
    """Return MP_API_KEY or raise a helpful error. Call after load_env()."""
    key = os.environ.get("MP_API_KEY")
    if not key or key == "your-materials-project-api-key-here":
        raise RuntimeError(
            "MP_API_KEY not set. Copy .env.example to .env and populate it, "
            "or export MP_API_KEY=... in your shell. Obtain a key at "
            "https://next-gen.materialsproject.org/api"
        )
    return key


def slugify(name: str) -> str:
    """
    Mirror of messai-ai `scripts/generate-parameter-fixtures.ts` slugify:
        name.toLowerCase().replace(/\\s+/g, '_').replace(/[()\\/]/g, '').replace(/:/, '')

    Keep this byte-compatible with the messai-ai version — downstream URL
    routing depends on it.
    """
    s = name.lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[()/]", "", s)
    s = s.replace(":", "", 1)  # only first ':', matching JS .replace semantics
    return s


def ensure_mess_parameters_available() -> None:
    """Raise if the MESS-Parameters submodule isn't initialized."""
    if not MESS_PARAMETERS_RICH_JSON.exists():
        raise RuntimeError(
            f"MESS-Parameters not found at {MESS_PARAMETERS_RICH_JSON}. "
            "This pipeline needs MESS-Parameters cloned at "
            f"{MESS_PARAMETERS_ROOT} (sibling-clone pattern). "
            "Run `git -C .. clone git@github.com:Messai-io/MESS-Parameters.git` "
            "or ensure the messai-ai submodule is checked out."
        )


def load_rich_parameters() -> list[dict[str, Any]]:
    """Load the pinned MESS-Parameters rich.json."""
    import json

    ensure_mess_parameters_available()
    with open(MESS_PARAMETERS_RICH_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise RuntimeError(
            "parameter-definitions-rich.json must be a JSON array"
        )
    return data


def is_material_parameter(param: dict) -> bool:
    """
    A MESS-Parameters entry is a "material slug" iff
        category == MATERIALS  AND  data_type == OBJECT.

    Verified against rich.json v0.2.0 — 26 entries match. Measurement
    parameters inside MATERIALS (Electrode Diameter, Membrane Water
    Uptake) use NUMBER; property containers (Carbon Felt, Platinum
    Cathode, Ti3c2tx Mxene) use OBJECT. Shared by extract-mes-material-
    slugs.py and assemble-rich-json.py.
    """
    return param.get("category") == "MATERIALS" and param.get("data_type") == "OBJECT"

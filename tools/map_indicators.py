"""
tools/map_indicators.py
-----------------------
Resolves SDG 4 indicator numbers to validated UIS indicator IDs
using the authoritative codebook. Never infers or guesses IDs.
"""

import json
import re
from pathlib import Path

# Load codebook once at module import
_CODEBOOK_PATH = Path(__file__).parent.parent / "codebooks" / "indicator_framework.json"

with open(_CODEBOOK_PATH, encoding="utf-8") as _f:
    _FRAMEWORK = json.load(_f)

_GLOBAL    = _FRAMEWORK["global_indicators"]
_THEMATIC  = _FRAMEWORK["thematic_indicators"]
_ALL       = {**_GLOBAL, **_THEMATIC}
_VALIDITY  = _FRAMEWORK["validity_rules"]

# Flat lookup: indicator_id -> sdg_number (for reverse lookup)
_ID_TO_SDG: dict[str, str] = {}
for _sdg, _entry in _ALL.items():
    for _iid in _entry["indicator_ids"]:
        _ID_TO_SDG[_iid.upper()] = _sdg


def _normalise_sdg(raw: str) -> str:
    """Strip common prefixes and whitespace from user input."""
    s = raw.strip()
    for prefix in ("SDG ", "SDG4 ", "SDG4.", "Indicator ", "indicator "):
        if s.upper().startswith(prefix.upper()):
            s = s[len(prefix):]
    return s.strip()


def resolve_sdg_indicators(sdg_number: str) -> dict:
    """
    Given an SDG indicator number, return the validated indicator IDs.

    Parameters
    ----------
    sdg_number : str
        e.g. '4.6.1', 'SDG 4.1.4', '1.a.2', 'FFA'

    Returns
    -------
    dict with keys: sdg_number, label, scope, indicator_ids, note (optional), error (if not found)
    """
    key = _normalise_sdg(sdg_number)

    if key in _ALL:
        entry = _ALL[key]
        return {
            "sdg_number":    key,
            "label":         entry["label"],
            "scope":         "global" if key in _GLOBAL else "thematic",
            "indicator_ids": entry["indicator_ids"],
            **({"note": entry["note"]} if "note" in entry else {}),
            "source":        "validated_codebook",
        }

    # Partial / suffix match (e.g. user typed '6.1' meaning '4.6.1')
    matches = [k for k in _ALL if k.endswith(key) or key.endswith(k)]
    if len(matches) == 1:
        k = matches[0]
        entry = _ALL[k]
        return {
            "sdg_number":    k,
            "label":         entry["label"],
            "scope":         "global" if k in _GLOBAL else "thematic",
            "indicator_ids": entry["indicator_ids"],
            "matched_from":  sdg_number,
            **({"note": entry["note"]} if "note" in entry else {}),
            "source":        "validated_codebook",
        }

    return {
        "error":     f"SDG indicator '{sdg_number}' not found in codebook.",
        "hint":      "Use list_sdg4_indicators to see all available indicator numbers.",
        "available": sorted(_ALL.keys()),
    }


def resolve_indicator_id(indicator_id: str) -> dict:
    """
    Reverse lookup: given a UIS indicator ID, return which SDG number it belongs to.
    """
    sdg = _ID_TO_SDG.get(indicator_id.upper())
    if sdg:
        entry = _ALL[sdg]
        return {
            "indicator_id": indicator_id,
            "sdg_number":   sdg,
            "label":        entry["label"],
            "scope":        "global" if sdg in _GLOBAL else "thematic",
        }
    return {
        "error":        f"Indicator ID '{indicator_id}' not found in codebook.",
        "indicator_id": indicator_id,
    }


def list_all_indicators(scope: str = "all") -> dict:
    """
    Return the full indicator catalogue, optionally filtered by scope.

    Parameters
    ----------
    scope : 'all' | 'global' | 'thematic'
    """
    out: dict[str, list] = {}

    if scope in ("all", "global"):
        out["global"] = [
            {
                "sdg_number":    k,
                "label":         v["label"],
                "indicator_ids": v["indicator_ids"],
            }
            for k, v in _GLOBAL.items()
        ]

    if scope in ("all", "thematic"):
        out["thematic"] = [
            {
                "sdg_number":    k,
                "label":         v["label"],
                "indicator_ids": v["indicator_ids"],
            }
            for k, v in _THEMATIC.items()
        ]

    return out


def get_validity_rules() -> dict:
    return _VALIDITY


def is_valid_record(magnitude: str | None, value, indicator_id: str = "") -> bool:
    """
    Apply UIS validity rules to a single data record.
    Returns True if the record counts as observed/reported data.
    """
    mag = str(magnitude).strip().upper() if magnitude is not None else ""
    if mag in {m.upper() for m in _VALIDITY["excluded_magnitudes"]}:
        return False
    if value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    for prefix in _VALIDITY.get("excluded_id_prefixes", []):
        if indicator_id.upper().startswith(prefix.upper()):
            return False
    return True

"""
tools/resolve_country.py
------------------------
Resolves country names (in any common form) to ISO3 codes used by the UIS API,
and provides population-weighted coverage calculations.

Country data is grounded in codebooks/countries.json (214 UIS World countries,
derived from SDG_COUNTRY.csv + SDG_REGION.csv).

Population data is grounded in codebooks/population_2025.json (UN WPP 2024
estimates, or regenerated from UIS bulk download via scripts/generate_population_codebook.py).
"""

from __future__ import annotations
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent

# ── Load codebooks once ───────────────────────────────────────────────────────
with open(_ROOT / "codebooks" / "countries.json", encoding="utf-8") as _f:
    _CTRY_DATA = json.load(_f)

with open(_ROOT / "codebooks" / "population_2025.json", encoding="utf-8") as _f:
    _POP_DATA = json.load(_f)

# Build lookup structures
_COUNTRIES:   list[dict] = _CTRY_DATA["countries"]          # [{iso3, name, region}, ...]
_ALIASES:     dict[str, str] = _CTRY_DATA["aliases"]        # lowercase name → ISO3
_POP_BY_ISO3: dict[str, int] = _POP_DATA["population_by_iso3"]
_TOTAL_POP:   int = _POP_DATA["_total_world_population"]

# ISO3 → country info lookup
_ISO3_MAP: dict[str, dict] = {c["iso3"]: c for c in _COUNTRIES}


def resolve_country(query: str) -> dict:
    """
    Resolve a country name, common alias, or ISO3 code to its UIS entry.

    Parameters
    ----------
    query : str
        Any of: full country name ('United Republic of Tanzania'),
                common alias ('Tanzania', 'UK', 'UAE'),
                ISO3 code ('TZA', 'GBR', 'ARE'),
                ISO3 in any case ('tza', 'gbr')

    Returns
    -------
    dict with: iso3, name, region, population_2025, in_uis_world
               or: error, suggestions (if not found)
    """
    q = query.strip()

    # 1. Direct ISO3 match (case-insensitive)
    iso3_upper = q.upper()
    if iso3_upper in _ISO3_MAP:
        ctry = _ISO3_MAP[iso3_upper]
        return _build_result(ctry)

    # 2. Alias lookup (lowercase)
    iso3 = _ALIASES.get(q.lower())
    if iso3 and iso3 in _ISO3_MAP:
        ctry = _ISO3_MAP[iso3]
        return _build_result(ctry)

    # 3. Partial name match (case-insensitive substring)
    q_lower = q.lower()
    partial = [
        c for c in _COUNTRIES
        if q_lower in c["name"].lower()
    ]
    if len(partial) == 1:
        return _build_result(partial[0])
    if len(partial) > 1:
        return {
            "error":       f"Ambiguous country name '{query}' — matched {len(partial)} countries.",
            "matches":     [{"iso3": c["iso3"], "name": c["name"]} for c in partial],
            "hint":        "Use a more specific name or the ISO3 code.",
        }

    # 4. Not found
    return {
        "error":       f"Country '{query}' not found in UIS World country list.",
        "hint":        "Use full country name, common alias, or ISO3 code.",
        "note":        "Only the 214 UIS World countries are included.",
    }


def resolve_countries(queries: list[str]) -> dict:
    """
    Resolve a list of country names/codes. Returns results for all,
    with a summary of how many were resolved successfully.
    """
    results = {q: resolve_country(q) for q in queries}
    resolved   = [q for q, r in results.items() if "error" not in r]
    unresolved = [q for q, r in results.items() if "error" in r]
    return {
        "results":     results,
        "resolved":    resolved,
        "unresolved":  unresolved,
        "summary": {
            "total":       len(queries),
            "resolved":    len(resolved),
            "unresolved":  len(unresolved),
        },
    }


def get_population(iso3: str) -> int | None:
    """Return 2025 population for a given ISO3 code, or None if not found."""
    return _POP_BY_ISO3.get(iso3.upper())


def compute_population_coverage(covered_iso3s: list[str]) -> dict:
    """
    Given a list of ISO3 codes that have data for an indicator,
    compute what share of global population they represent.

    Parameters
    ----------
    covered_iso3s : list of ISO3 codes of countries with data

    Returns
    -------
    dict with:
      - n_countries_covered       : count of countries with data
      - n_countries_total         : 214 (UIS World)
      - pct_countries             : % of 214 countries with data
      - population_covered        : sum of 2025 population for covered countries
      - population_total          : total 2025 population for 214 UIS countries
      - pct_population            : % of world population covered
      - countries_without_pop     : ISO3s in covered list with no population data
    """
    n_world = len(_COUNTRIES)
    covered_set = {c.upper() for c in covered_iso3s}

    pop_covered        = 0
    without_pop        = []
    for iso3 in covered_set:
        p = _POP_BY_ISO3.get(iso3)
        if p is not None:
            pop_covered += p
        else:
            without_pop.append(iso3)

    # Total population for the 214 UIS world countries
    uis_total_pop = sum(
        _POP_BY_ISO3.get(c["iso3"], 0) for c in _COUNTRIES
    )

    return {
        "n_countries_covered":   len(covered_set & {c["iso3"] for c in _COUNTRIES}),
        "n_countries_total":     n_world,
        "pct_countries":         round(100 * len(covered_set & {c["iso3"] for c in _COUNTRIES}) / n_world, 1),
        "population_covered":    pop_covered,
        "population_total":      uis_total_pop,
        "pct_population":        round(100 * pop_covered / uis_total_pop, 1) if uis_total_pop > 0 else 0,
        "countries_without_pop": without_pop,
        "population_year":       _POP_DATA.get("_reference_year", 2025),
        "population_source":     _POP_DATA.get("_source", ""),
    }


def list_countries_by_region(region: str | None = None) -> dict:
    """
    List UIS World countries, optionally filtered by sub-region.

    Parameters
    ----------
    region : UIS sub-region name (full or partial match), or None for all.
             Examples: 'Sub-Saharan Africa', 'Arab States', 'Central Asia'
    """
    if region is None:
        return {
            "countries": _COUNTRIES,
            "count":     len(_COUNTRIES),
        }

    q = region.lower()
    matched = [
        c for c in _COUNTRIES
        if q in c["region"].lower()
    ]

    if not matched:
        from codebooks_meta import _REGIONS  # noqa: local import avoids circular
        return {
            "error":    f"No countries matched region '{region}'.",
            "hint":     "Available regions: Sub-Saharan Africa, Arab States, Central Asia, "
                        "East Asia and the Pacific, Latin America and the Caribbean, "
                        "North America and Western Europe, South and West Asia, "
                        "Central and Eastern Europe.",
        }

    return {
        "region":    matched[0]["region"] if matched else region,
        "countries": matched,
        "count":     len(matched),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────
def _build_result(ctry: dict) -> dict:
    iso3 = ctry["iso3"]
    pop  = _POP_BY_ISO3.get(iso3)
    return {
        "iso3":             iso3,
        "name":             ctry["name"],
        "region":           ctry["region"],
        "in_uis_world":     True,
        "population_2025":  pop,
    }


def get_all_iso3s() -> list[str]:
    """Return sorted list of all 214 UIS World country ISO3 codes."""
    return sorted(c["iso3"] for c in _COUNTRIES)

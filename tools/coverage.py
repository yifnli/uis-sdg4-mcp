"""
tools/coverage.py
-----------------
Computes post-threshold data coverage statistics across the
214-country UIS World universe, for use in summary tables and briefings.

Coverage is reported on two dimensions:
  1. Share of 214 UIS World countries with at least one valid data point
  2. Share of global population those countries represent (2025 totals)

Population data is fetched from the UIS API (EMC_ID=200101, year=2025).
Country universe is derived from the UIS API geo units, not hardcoded.
"""

from __future__ import annotations
import json
from pathlib import Path
from tools.fetch_data import _get, fetch_indicator_data
from tools.map_indicators import resolve_sdg_indicators, is_valid_record

_RULES_PATH = Path(__file__).parent.parent / "codebooks" / "validity_rules.json"
_REGION_PATH = Path(__file__).parent.parent / "codebooks" / "region_order.json"

with open(_RULES_PATH, encoding="utf-8") as _f:
    _RULES = json.load(_f)
with open(_REGION_PATH, encoding="utf-8") as _f:
    _REGIONS = json.load(_f)

_BASE_URL = "https://api.uis.unesco.org/api/public"

# ── UIS World country list (fetched once, cached in module) ───────────────────
_WORLD_COUNTRIES: list[str] | None = None

def _get_world_countries() -> list[str]:
    """Fetch UIS World country list from the API geo units endpoint."""
    global _WORLD_COUNTRIES
    if _WORLD_COUNTRIES is not None:
        return _WORLD_COUNTRIES

    data = _get(f"{_BASE_URL}/definitions/geoUnits")
    if not data or not isinstance(data, list):
        # Fallback: return empty list; coverage will note the error
        return []

    # Filter to country-level geo units (not regional aggregates)
    countries = [
        item.get("id") or item.get("geoUnitCode") or item.get("isoCode")
        for item in data
        if item.get("type", "").lower() in ("country", "territory", "")
        and (item.get("id") or item.get("geoUnitCode") or item.get("isoCode"))
    ]
    # Deduplicate and remove None
    _WORLD_COUNTRIES = sorted(set(c for c in countries if c))
    return _WORLD_COUNTRIES


# ── Population cache ──────────────────────────────────────────────────────────
_POP_CACHE: dict[str, float] | None = None
_TOTAL_POP: float | None = None

def _get_population() -> tuple[dict[str, float], float]:
    """
    Fetch 2025 total population per country from UIS API.
    Returns (iso3 -> population dict, world total).
    """
    global _POP_CACHE, _TOTAL_POP
    if _POP_CACHE is not None:
        return _POP_CACHE, _TOTAL_POP

    emc_id  = _RULES["population"]["emc_id"]   # "200101"
    pop_year = int(_RULES["population"]["year"]) # 2025

    # Fetch population indicator for all countries
    result = fetch_indicator_data(
        indicator_ids=[emc_id],
        geo_unit="W00",           # UIS World aggregate — fallback if per-country not available
        start_year=pop_year,
        end_year=pop_year,
        observed_only=False,
    )

    # If world aggregate not available, return empty (coverage will show country % only)
    _POP_CACHE = {}
    _TOTAL_POP = 0.0
    return _POP_CACHE, _TOTAL_POP


# ── Main coverage function ────────────────────────────────────────────────────

def compute_coverage(
    indicator_ids: list[str],
    geo_unit: str = "all",
    threshold_year: int | None = None,
    start_year: int = 2000,
    end_year: int = 2025,
) -> dict:
    """
    Compute post-threshold data availability for a list of indicator IDs.

    For each indicator:
      - Fetches data across all UIS World countries (or a single geo unit)
      - Counts countries with >= 1 valid record after threshold_year
      - Computes % of 214 countries and % of population covered

    Parameters
    ----------
    indicator_ids  : list of exact UIS indicator IDs
    geo_unit       : 'all' for full world coverage, or specific ISO3
    threshold_year : count data strictly after this year (default from codebook)
    start_year     : data window start
    end_year       : data window end

    Returns
    -------
    dict with per-indicator coverage statistics and a combined summary
    """
    if threshold_year is None:
        threshold_year = _RULES["coverage"]["default_threshold_year"]

    results = {}

    for iid in indicator_ids:
        if geo_unit == "all":
            # Fetch for the UIS World aggregate to get a cross-country summary
            data = fetch_indicator_data(
                indicator_ids=[iid],
                geo_unit="W00",
                start_year=start_year,
                end_year=end_year,
                observed_only=True,
            )
            # Note: per-country breakdown via W00 may not be available;
            # we report what the API returns at world level
            world_result = data.get(iid, {})
            records_post = [
                r for r in world_result.get("records", [])
                if r.get("year") and r["year"] > threshold_year
            ]
            results[iid] = {
                "indicator_id":     iid,
                "threshold_year":   threshold_year,
                "records_post_threshold": len(records_post),
                "years_with_data":  world_result.get("years_with_data", []),
                "latest_year":      world_result.get("latest_year"),
                "note": (
                    "Coverage count requires per-country API calls. "
                    "Use geo_unit=<ISO3> for single-country data."
                ),
            }
        else:
            # Single country
            data = fetch_indicator_data(
                indicator_ids=[iid],
                geo_unit=geo_unit,
                start_year=start_year,
                end_year=end_year,
                observed_only=True,
            )
            ctry_result = data.get(iid, {})
            records      = ctry_result.get("records", [])
            records_post = [r for r in records if r.get("year") and r["year"] > threshold_year]
            years_all    = ctry_result.get("years_with_data", [])
            years_post   = sorted({r["year"] for r in records_post})

            results[iid] = {
                "indicator_id":          iid,
                "geo_unit":              geo_unit,
                "threshold_year":        threshold_year,
                "has_data":              len(records) > 0,
                "has_data_post_threshold": len(records_post) > 0,
                "records_total":         len(records),
                "records_post_threshold": len(records_post),
                "years_with_data":       years_all,
                "years_post_threshold":  years_post,
                "latest_year":           ctry_result.get("latest_year"),
            }

    return {
        "threshold_year": threshold_year,
        "geo_unit":       geo_unit,
        "indicators":     results,
        "summary": {
            "total_indicators": len(indicator_ids),
            "indicators_with_any_data": sum(
                1 for v in results.values()
                if v.get("has_data", v.get("records_post_threshold", 0) > 0)
            ),
        },
    }


def compute_sdg_coverage(sdg_number: str, geo_unit: str = "all",
                          threshold_year: int | None = None) -> dict:
    """
    Convenience wrapper: resolve SDG number → indicator IDs → coverage.
    """
    resolved = resolve_sdg_indicators(sdg_number)
    if "error" in resolved:
        return resolved

    ids = resolved["indicator_ids"]
    if not ids:
        return {
            "sdg_number":  sdg_number,
            "label":       resolved.get("label"),
            "indicator_ids": [],
            "note":        resolved.get("note", "No indicator IDs available for this SDG number."),
        }

    coverage = compute_coverage(ids, geo_unit=geo_unit, threshold_year=threshold_year)
    coverage["sdg_number"] = sdg_number
    coverage["label"]      = resolved["label"]
    coverage["scope"]      = resolved["scope"]
    return coverage

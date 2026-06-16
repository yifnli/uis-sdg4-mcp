"""
tools/coverage.py
-----------------
Computes post-threshold data coverage statistics for UIS SDG4 indicators.

Coverage is reported on two dimensions:
  1. Share of 214 UIS World countries with at least one valid data point
  2. Share of global population those countries represent (2025 totals)

Country universe:  codebooks/countries.json   (214 UIS World countries)
Population data:   codebooks/population_2025.json (UN WPP 2024 / UIS bulk download)
"""

from __future__ import annotations
import json
from pathlib import Path
from tools.fetch_data import fetch_indicator_data, fetch_distinct_countries
from tools.map_indicators import resolve_sdg_indicators
from tools.resolve_country import compute_population_coverage, get_all_iso3s

_ROOT = Path(__file__).parent.parent

with open(_ROOT / "codebooks" / "validity_rules.json", encoding="utf-8") as _f:
    _RULES = json.load(_f)


def compute_coverage(
    indicator_ids: list[str],
    geo_unit: str = "all",
    threshold_year: int | None = None,
    start_year: int = 2000,
    end_year: int = 2025,
) -> dict:
    """
    Compute post-threshold data availability for a list of indicator IDs.

    Parameters
    ----------
    indicator_ids  : list of exact UIS indicator IDs
    geo_unit       : ISO3 country code for single-country check, or 'all'
    threshold_year : count data strictly after this year (default from codebook: 2020)
    start_year     : data window start
    end_year       : data window end

    Returns
    -------
    dict with per-indicator results and population coverage statistics
    """
    if threshold_year is None:
        threshold_year = _RULES["coverage"]["default_threshold_year"]

    results = {}

    if geo_unit != "all":
        # ── Single country ────────────────────────────────────────────────────
        data = fetch_indicator_data(
            indicator_ids=indicator_ids,
            geo_unit=geo_unit,
            start_year=start_year,
            end_year=end_year,
            observed_only=True,
        )
        for iid in indicator_ids:
            ctry_result = data.get(iid, {})
            records      = ctry_result.get("records", [])
            records_post = [r for r in records if r.get("year") and r["year"] > threshold_year]
            years_all    = ctry_result.get("years_with_data", [])
            years_post   = sorted({r["year"] for r in records_post})

            results[iid] = {
                "indicator_id":             iid,
                "geo_unit":                 geo_unit,
                "threshold_year":           threshold_year,
                "has_data":                 len(records) > 0,
                "has_data_post_threshold":  len(records_post) > 0,
                "records_total":            len(records),
                "records_post_threshold":   len(records_post),
                "years_with_data":          years_all,
                "years_post_threshold":     years_post,
                "latest_year":              ctry_result.get("latest_year"),
                "error":                    ctry_result.get("error"),
            }
            if not ctry_result.get("error"):
                results[iid].pop("error", None)

        return {
            "threshold_year": threshold_year,
            "geo_unit":       geo_unit,
            "indicators":     results,
            "summary": {
                "total_indicators":          len(indicator_ids),
                "indicators_with_any_data":  sum(1 for v in results.values() if v.get("has_data")),
                "indicators_post_threshold": sum(1 for v in results.values() if v.get("has_data_post_threshold")),
            },
        }

    else:
        # ── World coverage via ODS aggregation ────────────────────────────────
        # One group_by(country_id) sweep per indicator gives the distinct set of
        # countries with data — no per-country fan-out.
        all_iso3s = get_all_iso3s()   # 214 UIS World countries

        for iid in indicator_ids:
            covered_any  = fetch_distinct_countries(iid, after_year=None)
            if isinstance(covered_any, dict) and "_error" in covered_any:
                results[iid] = {"indicator_id": iid, "error": covered_any["_error"]}
                continue
            covered_post = fetch_distinct_countries(iid, after_year=threshold_year)
            if isinstance(covered_post, dict) and "_error" in covered_post:
                covered_post = []

            # Keep only ISO3s in the UIS World universe for population weighting.
            universe = set(all_iso3s)
            covered_any  = [c for c in covered_any  if c in universe]
            covered_post = [c for c in covered_post if c in universe]

            pop_any  = compute_population_coverage(covered_any)
            pop_post = compute_population_coverage(covered_post)

            results[iid] = {
                "indicator_id":    iid,
                "threshold_year":  threshold_year,
                "coverage_any_data": {
                    "n_countries":   pop_any["n_countries_covered"],
                    "pct_countries": pop_any["pct_countries"],
                    "pct_population": pop_any["pct_population"],
                    "covered_iso3s": covered_any,
                },
                "coverage_post_threshold": {
                    "n_countries":   pop_post["n_countries_covered"],
                    "pct_countries": pop_post["pct_countries"],
                    "pct_population": pop_post["pct_population"],
                    "covered_iso3s": covered_post,
                },
                "population_reference_year": pop_any.get("population_year", 2025),
                "population_source":         pop_any.get("population_source", ""),
            }

        return {
            "threshold_year":  threshold_year,
            "geo_unit":        "all",
            "n_uis_countries": len(all_iso3s),
            "indicators":      results,
            "summary": {"total_indicators": len(indicator_ids)},
            "note": (
                "World coverage computed via a single DataHub group_by(country_id) "
                "aggregation per indicator over dataset uis001."
            ),
        }


def compute_sdg_coverage(
    sdg_number: str,
    geo_unit: str = "all",
    threshold_year: int | None = None,
) -> dict:
    """
    Convenience wrapper: resolve SDG number → indicator IDs → coverage.
    """
    resolved = resolve_sdg_indicators(sdg_number)
    if "error" in resolved:
        return resolved

    ids = resolved["indicator_ids"]
    if not ids:
        return {
            "sdg_number":    sdg_number,
            "label":         resolved.get("label"),
            "indicator_ids": [],
            "note":          resolved.get("note", "No indicator IDs available for this SDG number."),
        }

    coverage = compute_coverage(ids, geo_unit=geo_unit, threshold_year=threshold_year)
    coverage["sdg_number"] = sdg_number
    coverage["label"]      = resolved["label"]
    coverage["scope"]      = resolved["scope"]
    return coverage

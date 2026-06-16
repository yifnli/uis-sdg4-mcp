"""
tools/briefing.py
-----------------
Helper functions for formatting structured data into briefing-ready output.

Writing style: neutral, factual. No evaluative adjectives. No attribution
of data gaps to country behaviour or capacity. Describes what the data show.
"""

from __future__ import annotations
from datetime import date


def format_country_briefing(
    country_name: str,
    iso3: str,
    indicator_results: dict,
    threshold_year: int = 2020,
) -> dict:
    """
    Format API results for one country into a structured briefing dict.
    The AI uses this structured output to generate narrative text.

    Parameters
    ----------
    country_name       : full country name (e.g. 'Uzbekistan')
    iso3               : ISO3 code (e.g. 'UZB')
    indicator_results  : output of fetch_indicator_data (keyed by indicator_id)
    threshold_year     : year used as recency threshold

    Returns
    -------
    Structured dict with sections the AI can use to build a briefing
    """
    sections = []

    for iid, result in indicator_results.items():
        if "error" in result:
            sections.append({
                "indicator_id": iid,
                "status":       "api_error",
                "message":      result["error"],
            })
            continue

        records = result.get("records", [])
        years   = result.get("years_with_data", [])
        latest  = result.get("latest_year")

        if not records:
            sections.append({
                "indicator_id":   iid,
                "status":         "no_data",
                "years_available": [],
                "latest_year":    None,
            })
            continue

        post_threshold = [r for r in records if r.get("year") and r["year"] > threshold_year]
        values_by_year = {r["year"]: r["value"] for r in records if r.get("year")}

        # Identify gaps: years in range with no data
        if years:
            full_range = list(range(min(years), max(years) + 1))
            gap_years  = [y for y in full_range if y not in years]
        else:
            full_range = []
            gap_years  = []

        # Year-over-year change for most recent pair
        yoy_change = None
        sorted_years = sorted(values_by_year)
        if len(sorted_years) >= 2:
            y1, y2 = sorted_years[-2], sorted_years[-1]
            v1, v2 = values_by_year[y1], values_by_year[y2]
            if v1 is not None and v2 is not None:
                try:
                    yoy_change = {
                        "from_year": y1,
                        "to_year":   y2,
                        "change":    round(float(v2) - float(v1), 4),
                    }
                except (TypeError, ValueError):
                    pass

        sections.append({
            "indicator_id":              iid,
            "status":                    "data_available",
            "years_available":           years,
            "year_range":                f"{min(years)}–{max(years)}" if years else None,
            "latest_year":               latest,
            "has_data_post_threshold":   len(post_threshold) > 0,
            "records_post_threshold":    len(post_threshold),
            "gap_years_in_range":        gap_years,
            "values_by_year":            values_by_year,
            "latest_value":              values_by_year.get(latest) if latest else None,
            "year_over_year_change":     yoy_change,
        })

    # Missing indicators (those in request but not in results)
    indicators_with_data    = [s["indicator_id"] for s in sections if s["status"] == "data_available"]
    indicators_without_data = [s["indicator_id"] for s in sections if s["status"] == "no_data"]

    return {
        "country":             country_name,
        "iso3":                iso3,
        "threshold_year":      threshold_year,
        "generated_date":      date.today().isoformat(),
        "data_source":         "UNESCO DataHub (dataset uis001) — observed/reported data only",
        "indicators":          sections,
        "summary": {
            "total_requested":       len(sections),
            "with_data":             len(indicators_with_data),
            "without_data":          len(indicators_without_data),
            "with_post_threshold":   sum(
                1 for s in sections if s.get("has_data_post_threshold")
            ),
        },
    }


def format_trend_table(indicator_id: str, records: list[dict]) -> dict:
    """
    Format a list of records into a clean year-value table for briefing use.
    Includes year-over-year change and flags gaps.
    """
    if not records:
        return {"indicator_id": indicator_id, "rows": [], "note": "No data available."}

    sorted_records = sorted(records, key=lambda r: r.get("year") or 0)
    rows = []
    prev_value = None
    prev_year  = None

    for rec in sorted_records:
        yr  = rec.get("year")
        val = rec.get("value")

        gap_since_previous = None
        if prev_year is not None and yr is not None:
            gap = yr - prev_year - 1
            if gap > 0:
                gap_since_previous = gap

        yoy = None
        if prev_value is not None and val is not None:
            try:
                yoy = round(float(val) - float(prev_value), 4)
            except (TypeError, ValueError):
                pass

        rows.append({
            "year":               yr,
            "value":              val,
            "yoy_change":         yoy,
            "gap_years_before":   gap_since_previous,
            "source":             rec.get("source", "N/A"),
        })
        prev_value = val
        prev_year  = yr

    years = [r["year"] for r in rows if r["year"]]
    return {
        "indicator_id": indicator_id,
        "year_range":   f"{min(years)}–{max(years)}" if years else None,
        "record_count": len(rows),
        "rows":         rows,
    }


def format_coverage_summary_table(coverage_result: dict) -> dict:
    """
    Format coverage computation output into a clean summary table structure
    suitable for the AI to present as a briefing table.
    """
    rows = []
    for iid, result in coverage_result.get("indicators", {}).items():
        rows.append({
            "indicator_id":              iid,
            "geo_unit":                  result.get("geo_unit", "all"),
            "has_data":                  result.get("has_data", False),
            "has_data_post_threshold":   result.get("has_data_post_threshold", False),
            "latest_year":               result.get("latest_year"),
            "years_with_data":           result.get("years_with_data", []),
            "years_post_threshold":      result.get("years_post_threshold", []),
        })

    return {
        "threshold_year": coverage_result.get("threshold_year"),
        "geo_unit":       coverage_result.get("geo_unit"),
        "sdg_number":     coverage_result.get("sdg_number"),
        "label":          coverage_result.get("label"),
        "rows":           rows,
        "summary":        coverage_result.get("summary", {}),
    }


def writing_style_note() -> str:
    """Return the UIS writing style reminder for the AI."""
    return (
        "Writing style: neutral, factual. "
        "Do not use evaluative adjectives (e.g. poor, weak, alarming, impressive). "
        "Do not attribute data gaps to country behaviour or capacity. "
        "Describe what the data show. Note years for which data are or are not available. "
        "Use passive constructions when describing gaps."
    )

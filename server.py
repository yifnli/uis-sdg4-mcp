"""
server.py
---------
UIS SDG4 MCP Server (FastMCP v2).

Data source: UNESCO DataHub (data.unesco.org), Opendatasoft Explore API v2.1,
dataset uis001 (SDG 4 Education Indicators — Global & Thematic).

Principle: the server owns the numbers (codebook-resolved IDs, validity-filtered
DataHub records); the AI writes the narrative.

Usage:
  uv run python server.py          (runs as stdio MCP server)
  uv run python server.py --test   (offline self-test, no network)
"""

import sys
from pathlib import Path

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))

from tools.map_indicators import (
    resolve_sdg_indicators as _resolve_sdg,
    resolve_indicator_id,
    list_all_indicators,
    get_validity_rules,
)
from tools.fetch_data import (
    fetch_indicator_data,
    validate_indicator_ids_against_api,
)
from tools.coverage import compute_coverage as _compute_coverage, compute_sdg_coverage as _compute_sdg_coverage
from tools.resolve_country import (
    resolve_country as _resolve_country,
    compute_population_coverage as _compute_pop_coverage,
    list_countries_by_region as _list_countries_by_region,
)
from tools.briefing import format_country_briefing as _format_briefing, writing_style_note

mcp = FastMCP("uis-sdg4")


@mcp.tool
def resolve_sdg_indicators(sdg_number: str) -> dict:
    """Given an SDG 4 indicator number (e.g. '4.6.1', '4.1.4', 'FFA', '1.a.2'),
    return the exact validated UIS indicator IDs from the authoritative codebook.
    Always call this first when working from an SDG number. Never guesses IDs."""
    return _resolve_sdg(sdg_number)


@mcp.tool
def get_indicator_data(
    indicator_ids: list[str],
    geo_unit: str,
    start_year: int = 2000,
    end_year: int = 2025,
    include_metadata: bool = False,
    observed_only: bool = True,
) -> dict:
    """Fetch published education data from the UNESCO DataHub (dataset uis001) for
    one or more indicator IDs and a country (ISO3). Returns only observed/reported
    data — validity rules exclude flagged magnitudes and modelled-estimate ID
    prefixes by default. Use resolve_sdg_indicators first if you have an SDG number."""
    return fetch_indicator_data(
        indicator_ids=indicator_ids,
        geo_unit=geo_unit,
        start_year=start_year,
        end_year=end_year,
        include_metadata=include_metadata,
        observed_only=observed_only,
    )


@mcp.tool
def compute_coverage(
    indicator_ids: list[str],
    geo_unit: str = "all",
    threshold_year: int = 2020,
    start_year: int = 2000,
    end_year: int = 2025,
) -> dict:
    """Compute post-threshold data availability for a list of indicator IDs.
    geo_unit=ISO3 returns per-country years/latest/post-threshold status;
    geo_unit='all' returns world coverage (share of 214 UIS countries and of
    global population) via a DataHub aggregation. Default threshold year is 2020."""
    return _compute_coverage(
        indicator_ids=indicator_ids,
        geo_unit=geo_unit,
        threshold_year=threshold_year,
        start_year=start_year,
        end_year=end_year,
    )


@mcp.tool
def compute_sdg_coverage(sdg_number: str, geo_unit: str = "all", threshold_year: int = 2020) -> dict:
    """Convenience tool: resolve an SDG number to indicator IDs from the codebook,
    then compute coverage in one call. Returns coverage plus resolved IDs and label."""
    return _compute_sdg_coverage(sdg_number=sdg_number, geo_unit=geo_unit, threshold_year=threshold_year)


@mcp.tool
def format_country_briefing(
    country_name: str,
    iso3: str,
    indicator_results: dict,
    threshold_year: int = 2020,
) -> dict:
    """Format raw get_indicator_data results for one country into a structured
    briefing dict (gap years, year-over-year changes, post-threshold availability),
    plus the UIS writing style guide for neutral, factual narrative generation."""
    briefing = _format_briefing(
        country_name=country_name,
        iso3=iso3,
        indicator_results=indicator_results,
        threshold_year=threshold_year,
    )
    briefing["writing_style_guide"] = writing_style_note()
    return briefing


@mcp.tool
def list_sdg4_indicators(scope: str = "all") -> dict:
    """List all validated SDG 4 indicator numbers with labels and component UIS
    indicator IDs. scope is one of 'all', 'global', 'thematic'."""
    return list_all_indicators(scope=scope)


@mcp.tool
def validate_indicator_ids(indicator_ids: list[str]) -> dict:
    """Check whether given indicator IDs exist in the live DataHub dataset (uis001).
    Returns confirmed and not_in_api lists. Use to verify codebook IDs after a
    data release update."""
    return validate_indicator_ids_against_api(indicator_ids)


@mcp.tool
def resolve_country(query: str) -> dict:
    """Resolve a country name (any common form), alias, or ISO3 code to its UIS
    entry: ISO3, official name, UIS sub-region, and 2025 population. Always call
    this first when a user gives a country name rather than an ISO3 code."""
    return _resolve_country(query)


@mcp.tool
def compute_population_coverage(covered_iso3s: list[str]) -> dict:
    """Given ISO3 codes that have data for an indicator, compute the share of global
    population (2025) and of UIS world countries those represent. Population data:
    UN World Population Prospects 2024 (214 UIS countries)."""
    return _compute_pop_coverage(covered_iso3s)


@mcp.tool
def list_countries_by_region(region: str | None = None) -> dict:
    """List UIS World countries, optionally filtered by sub-region. Returns ISO3,
    name, region, and 2025 population for each. Omit region for all 214 countries."""
    return _list_countries_by_region(region)


@mcp.tool
def get_writing_style_guide() -> dict:
    """Return the UIS writing style guide and validity rules for generating
    briefings: neutral, factual language; no evaluative adjectives; no attribution
    of data gaps to country behaviour."""
    return {
        "writing_style": writing_style_note(),
        "validity_rules": get_validity_rules(),
        "source": "UIS SDG4 MCP codebook",
    }


def _run_self_test():
    """Quick offline test — no API calls, no MCP connection needed."""
    print("Running self-test (codebook only, no API calls) …\n")

    r = _resolve_sdg("4.6.1")
    assert "error" not in r, f"resolve failed: {r}"
    assert "LR.AG15T99" in r["indicator_ids"], "Missing LR.AG15T99"
    print(f"✓ resolve_sdg_indicators('4.6.1') → {len(r['indicator_ids'])} IDs")

    r2 = _resolve_sdg("SDG 4.7.1")
    assert "error" not in r2
    assert "SGE.EnvSust" in r2["indicator_ids"], "Missing SGE greening indicators"
    print("✓ resolve_sdg_indicators('SDG 4.7.1') → includes SGE greening IDs")

    r3 = _resolve_sdg("9.9.9")
    assert "error" in r3
    print("✓ resolve_sdg_indicators('9.9.9') → correct error response")

    r4 = resolve_indicator_id("CR.1")
    assert r4["sdg_number"] == "4.1.2"
    print("✓ resolve_indicator_id('CR.1') → SDG 4.1.2")

    cat = list_all_indicators("global")
    assert len(cat["global"]) == 14, f"Expected 14 global, got {len(cat['global'])}"
    cat2 = list_all_indicators("thematic")
    assert len(cat2["thematic"]) == 31, f"Expected 31 thematic, got {len(cat2['thematic'])}"
    print("✓ list_all_indicators → 14 global, 31 thematic")

    from tools.map_indicators import is_valid_record
    assert not is_valid_record("SUPP", 99.5)
    assert not is_valid_record(None, None)
    assert not is_valid_record("", 99.5, "CR.MOD.1")
    assert     is_valid_record("", 99.5, "CR.1")
    print("✓ is_valid_record → all edge cases pass")

    dummy_results = {
        "LR.AG15T99": {
            "records": [
                {"year": 2018, "value": 99.98, "magnitude": "", "source": "N/A"},
                {"year": 2019, "value": 100.0, "magnitude": "", "source": "N/A"},
                {"year": 2021, "value": 100.0, "magnitude": "", "source": "N/A"},
            ],
            "years_with_data": [2018, 2019, 2021],
            "latest_year": 2021,
        },
        "LR.GALP.AG15T99": {"error": "Not found"},
    }
    briefing = _format_briefing("Uzbekistan", "UZB", dummy_results)
    assert briefing["summary"]["with_data"] == 1
    assert briefing["summary"]["without_data"] == 0
    print("✓ format_country_briefing → structured correctly")

    from tools.resolve_country import resolve_country, compute_population_coverage, get_all_iso3s
    assert resolve_country("Tanzania")["iso3"] == "TZA"
    assert resolve_country("South Korea")["iso3"] == "KOR"
    assert resolve_country("UK")["iso3"] == "GBR"
    print("✓ resolve_country('Tanzania') → TZA, ('South Korea') → KOR, ('UK') → GBR")

    pop = compute_population_coverage(["CHN", "IND", "USA"])
    assert pop["n_countries_covered"] == 3
    assert pop["pct_population"] > 35, "CHN+IND+USA should cover >35% of world pop"
    print(f"✓ compute_population_coverage(['CHN','IND','USA']) → {pop['pct_population']}% of world pop")

    assert len(get_all_iso3s()) == 214
    print("✓ get_all_iso3s() → 214 UIS World countries")

    print("\n✓ All self-tests passed (10 checks).\n")


def main():
    if "--test" in sys.argv:
        _run_self_test()
    else:
        mcp.run()


if __name__ == "__main__":
    main()

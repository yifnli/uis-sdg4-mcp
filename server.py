"""
server.py
---------
UIS SDG4 MCP Server

Exposes the following tools to any MCP-compatible AI client:
  1. resolve_sdg_indicators     — SDG number → validated indicator IDs (codebook)
  2. get_indicator_data         — fetch observed data from UIS API for a country
  3. compute_coverage           — post-threshold coverage stats for indicator IDs
  4. compute_sdg_coverage       — convenience: SDG number → coverage in one call
  5. format_country_briefing    — structure API results for narrative generation
  6. list_sdg4_indicators       — full catalogue of SDG4 indicators
  7. validate_indicator_ids     — check indicator IDs against the live UIS API
  8. get_writing_style_guide    — return UIS writing style rules

Usage:
  python server.py              (runs as stdio MCP server)
  python server.py --test       (runs quick self-test without starting server)
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Add project root to path so tools/ imports work
sys.path.insert(0, str(Path(__file__).parent))

from tools.map_indicators import (
    resolve_sdg_indicators,
    resolve_indicator_id,
    list_all_indicators,
    get_validity_rules,
)
from tools.fetch_data import (
    fetch_indicator_data,
    fetch_available_geo_units,
    validate_indicator_ids_against_api,
)
from tools.coverage import compute_coverage, compute_sdg_coverage
from tools.briefing import (
    format_country_briefing,
    format_trend_table,
    format_coverage_summary_table,
    writing_style_note,
)

# ── Server instance ────────────────────────────────────────────────────────────
app = Server("uis-sdg4")


# ── Tool definitions ──────────────────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="resolve_sdg_indicators",
            description=(
                "Given an SDG 4 indicator number (e.g. '4.6.1', '4.1.4', 'FFA', '1.a.2'), "
                "returns the exact validated UIS indicator IDs from the authoritative codebook. "
                "Always call this first when working from an SDG number. "
                "Never guesses or infers indicator IDs — only returns codebook-validated values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sdg_number": {
                        "type":        "string",
                        "description": "SDG indicator number e.g. '4.6.1', 'SDG 4.1.4', 'FFA'",
                    }
                },
                "required": ["sdg_number"],
            },
        ),
        Tool(
            name="get_indicator_data",
            description=(
                "Fetch published UIS data for one or more indicator IDs and a country or region. "
                "Returns only observed/reported data — modelled estimates are excluded by default. "
                "Applies UIS validity rules (excludes MAGNITUDE: SUPP, NA, INCLUDED). "
                "Use resolve_sdg_indicators first if you have an SDG number rather than indicator IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "indicator_ids": {
                        "type":        "array",
                        "items":       {"type": "string"},
                        "description": "List of exact UIS indicator IDs e.g. ['LR.AG15T99', 'LR.AG15T24']",
                    },
                    "geo_unit": {
                        "type":        "string",
                        "description": "ISO3 country code e.g. 'UZB', 'TZA', or region code",
                    },
                    "start_year": {
                        "type":        "integer",
                        "description": "First year to retrieve (default: 2000)",
                        "default":     2000,
                    },
                    "end_year": {
                        "type":        "integer",
                        "description": "Last year to retrieve (default: 2025)",
                        "default":     2025,
                    },
                    "include_metadata": {
                        "type":        "boolean",
                        "description": "Request TYPE_OF_SOURCE metadata (default: false)",
                        "default":     False,
                    },
                    "observed_only": {
                        "type":        "boolean",
                        "description": "Apply validity filter — exclude modelled estimates (default: true)",
                        "default":     True,
                    },
                },
                "required": ["indicator_ids", "geo_unit"],
            },
        ),
        Tool(
            name="compute_coverage",
            description=(
                "Compute post-threshold data availability statistics for a list of indicator IDs. "
                "For a single country (geo_unit=ISO3): returns years with data, latest year, "
                "and whether data exist after the threshold year. "
                "For world coverage (geo_unit='all'): returns aggregate availability. "
                "Default threshold year is 2020 (data strictly after 2020)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "indicator_ids": {
                        "type":  "array",
                        "items": {"type": "string"},
                    },
                    "geo_unit": {
                        "type":        "string",
                        "description": "ISO3 country code or 'all' for world-level (default: 'all')",
                        "default":     "all",
                    },
                    "threshold_year": {
                        "type":        "integer",
                        "description": "Count data strictly after this year (default: 2020)",
                        "default":     2020,
                    },
                    "start_year": {"type": "integer", "default": 2000},
                    "end_year":   {"type": "integer", "default": 2025},
                },
                "required": ["indicator_ids"],
            },
        ),
        Tool(
            name="compute_sdg_coverage",
            description=(
                "Convenience tool: given an SDG number, resolves indicator IDs from the "
                "codebook then computes coverage in one call. "
                "Returns coverage stats plus the resolved indicator IDs and SDG label."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sdg_number": {
                        "type":        "string",
                        "description": "SDG indicator number e.g. '4.1.4'",
                    },
                    "geo_unit": {
                        "type":    "string",
                        "default": "all",
                    },
                    "threshold_year": {
                        "type":    "integer",
                        "default": 2020,
                    },
                },
                "required": ["sdg_number"],
            },
        ),
        Tool(
            name="format_country_briefing",
            description=(
                "Format raw API results for one country into a structured briefing dict. "
                "Use after get_indicator_data to prepare data for narrative generation. "
                "Structures data into sections with gap years, year-over-year changes, "
                "and post-threshold availability. "
                "Also returns the UIS writing style guide for neutral, factual language."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country_name": {
                        "type":        "string",
                        "description": "Full country name e.g. 'Uzbekistan'",
                    },
                    "iso3": {
                        "type":        "string",
                        "description": "ISO3 country code e.g. 'UZB'",
                    },
                    "indicator_results": {
                        "type":        "object",
                        "description": "Output of get_indicator_data (keyed by indicator_id)",
                    },
                    "threshold_year": {
                        "type":    "integer",
                        "default": 2020,
                    },
                },
                "required": ["country_name", "iso3", "indicator_results"],
            },
        ),
        Tool(
            name="list_sdg4_indicators",
            description=(
                "List all validated SDG 4 indicator numbers with their labels and "
                "component UIS indicator IDs. Optionally filter by scope."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type":        "string",
                        "enum":        ["all", "global", "thematic"],
                        "description": "Filter by indicator scope (default: 'all')",
                        "default":     "all",
                    }
                },
            },
        ),
        Tool(
            name="validate_indicator_ids",
            description=(
                "Check whether given indicator IDs exist in the live UIS API. "
                "Returns confirmed (found) and not_in_api (not found) lists. "
                "Use to verify codebook IDs are still current after a data release update."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "indicator_ids": {
                        "type":  "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["indicator_ids"],
            },
        ),
        Tool(
            name="get_writing_style_guide",
            description=(
                "Return the UIS writing style guide for generating briefings and reports. "
                "Call this before generating any narrative text to ensure neutral, "
                "factual language that does not use evaluative adjectives or attribute "
                "data gaps to country behaviour."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:

    def _out(data) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    # ── 1. resolve_sdg_indicators ─────────────────────────────────────────────
    if name == "resolve_sdg_indicators":
        result = resolve_sdg_indicators(arguments["sdg_number"])
        return _out(result)

    # ── 2. get_indicator_data ─────────────────────────────────────────────────
    elif name == "get_indicator_data":
        result = fetch_indicator_data(
            indicator_ids=arguments["indicator_ids"],
            geo_unit=arguments["geo_unit"],
            start_year=arguments.get("start_year", 2000),
            end_year=arguments.get("end_year", 2025),
            include_metadata=arguments.get("include_metadata", False),
            observed_only=arguments.get("observed_only", True),
        )
        return _out(result)

    # ── 3. compute_coverage ───────────────────────────────────────────────────
    elif name == "compute_coverage":
        result = compute_coverage(
            indicator_ids=arguments["indicator_ids"],
            geo_unit=arguments.get("geo_unit", "all"),
            threshold_year=arguments.get("threshold_year", 2020),
            start_year=arguments.get("start_year", 2000),
            end_year=arguments.get("end_year", 2025),
        )
        return _out(result)

    # ── 4. compute_sdg_coverage ───────────────────────────────────────────────
    elif name == "compute_sdg_coverage":
        result = compute_sdg_coverage(
            sdg_number=arguments["sdg_number"],
            geo_unit=arguments.get("geo_unit", "all"),
            threshold_year=arguments.get("threshold_year", 2020),
        )
        return _out(result)

    # ── 5. format_country_briefing ────────────────────────────────────────────
    elif name == "format_country_briefing":
        briefing = format_country_briefing(
            country_name=arguments["country_name"],
            iso3=arguments["iso3"],
            indicator_results=arguments["indicator_results"],
            threshold_year=arguments.get("threshold_year", 2020),
        )
        briefing["writing_style_guide"] = writing_style_note()
        return _out(briefing)

    # ── 6. list_sdg4_indicators ───────────────────────────────────────────────
    elif name == "list_sdg4_indicators":
        result = list_all_indicators(scope=arguments.get("scope", "all"))
        return _out(result)

    # ── 7. validate_indicator_ids ─────────────────────────────────────────────
    elif name == "validate_indicator_ids":
        result = validate_indicator_ids_against_api(arguments["indicator_ids"])
        return _out(result)

    # ── 8. get_writing_style_guide ────────────────────────────────────────────
    elif name == "get_writing_style_guide":
        rules = get_validity_rules()
        return _out({
            "writing_style": writing_style_note(),
            "validity_rules": rules,
            "source": "UIS SDG4 MCP codebook",
        })

    else:
        return _out({"error": f"Unknown tool: '{name}'"})


# ── Entry point ───────────────────────────────────────────────────────────────
async def _run_server():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


def _run_self_test():
    """Quick offline test — no API calls, no MCP connection needed."""
    print("Running self-test (codebook only, no API calls) …\n")

    # Test 1: resolve known SDG number
    r = resolve_sdg_indicators("4.6.1")
    assert "error" not in r, f"resolve failed: {r}"
    assert "LR.AG15T99" in r["indicator_ids"], "Missing LR.AG15T99"
    print(f"✓ resolve_sdg_indicators('4.6.1') → {len(r['indicator_ids'])} IDs")

    # Test 2: resolve with prefix
    r2 = resolve_sdg_indicators("SDG 4.7.1")
    assert "error" not in r2
    assert "SGE.EnvSust" in r2["indicator_ids"], "Missing SGE greening indicators"
    print(f"✓ resolve_sdg_indicators('SDG 4.7.1') → includes SGE greening IDs")

    # Test 3: unknown indicator
    r3 = resolve_sdg_indicators("9.9.9")
    assert "error" in r3
    print(f"✓ resolve_sdg_indicators('9.9.9') → correct error response")

    # Test 4: reverse lookup
    r4 = resolve_indicator_id("CR.1")
    assert r4["sdg_number"] == "4.1.2"
    print(f"✓ resolve_indicator_id('CR.1') → SDG 4.1.2")

    # Test 5: list catalogue
    cat = list_all_indicators("global")
    assert len(cat["global"]) == 14, f"Expected 14 global, got {len(cat['global'])}"
    cat2 = list_all_indicators("thematic")
    assert len(cat2["thematic"]) == 31, f"Expected 31 thematic, got {len(cat2['thematic'])}"
    print(f"✓ list_all_indicators → 14 global, 31 thematic")

    # Test 6: validity rule
    from tools.map_indicators import is_valid_record
    assert not is_valid_record("SUPP", 99.5)
    assert not is_valid_record(None, None)
    assert not is_valid_record("", 99.5, "CR.MOD.1")
    assert     is_valid_record("", 99.5, "CR.1")
    print(f"✓ is_valid_record → all edge cases pass")

    # Test 7: briefing formatter (no API)
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
    briefing = format_country_briefing("Uzbekistan", "UZB", dummy_results)
    assert briefing["summary"]["with_data"] == 1
    assert briefing["summary"]["without_data"] == 0
    print(f"✓ format_country_briefing → structured correctly")

    print("\n✓ All self-tests passed.\n")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_self_test()
    else:
        asyncio.run(_run_server())

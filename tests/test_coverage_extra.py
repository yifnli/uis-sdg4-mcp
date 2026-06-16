"""
tests/test_coverage_extra.py
----------------------------
Targeted unit tests for previously-untested pure functions. Offline; HTTP mocked.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── map_indicators ────────────────────────────────────────────────────────────
def test_resolve_indicator_id_unknown_returns_error():
    from tools.map_indicators import resolve_indicator_id
    out = resolve_indicator_id("NOPE.NOT.REAL")
    assert "error" in out


def test_resolve_indicator_id_case_insensitive():
    from tools.map_indicators import resolve_indicator_id
    assert resolve_indicator_id("cr.1")["sdg_number"] == "4.1.2"


def test_get_validity_rules_has_excluded_prefixes():
    from tools.map_indicators import get_validity_rules
    rules = get_validity_rules()
    assert "CR.MOD." in rules["excluded_id_prefixes"]


# ── resolve_country ───────────────────────────────────────────────────────────
def test_get_population_known_and_unknown():
    from tools.resolve_country import get_population
    assert get_population("CHN") and get_population("CHN") > 1_000_000_000
    assert get_population("ZZZ") is None


def test_list_countries_by_region_happy_path():
    from tools.resolve_country import list_countries_by_region
    out = list_countries_by_region("Sub-Saharan Africa")
    assert "countries" in out
    assert len(out["countries"]) > 10
    assert all("iso3" in c for c in out["countries"])


def test_compute_population_coverage_empty_list():
    from tools.resolve_country import compute_population_coverage
    out = compute_population_coverage([])
    assert out["n_countries_covered"] == 0
    assert out["pct_population"] == 0


def test_compute_population_coverage_ignores_unknown_iso3():
    from tools.resolve_country import compute_population_coverage
    # ZZZ is not in the UIS World country list; the intersection with _COUNTRIES
    # yields only CHN, so n_countries_covered == 1. ZZZ lands in countries_without_pop.
    out = compute_population_coverage(["CHN", "ZZZ"])
    assert out["n_countries_covered"] == 1
    assert "ZZZ" in out["countries_without_pop"]


# ── briefing ──────────────────────────────────────────────────────────────────
def test_format_coverage_summary_table_shape():
    from tools.briefing import format_coverage_summary_table
    # format_coverage_summary_table reads result.get("has_data"), "latest_year",
    # "years_with_data", "years_post_threshold" from each indicator dict — not
    # the nested coverage_any_data / coverage_post_threshold sub-keys.
    coverage_result = {
        "threshold_year": 2020,
        "geo_unit": "all",
        "indicators": {
            "LR.AG15T99": {
                "indicator_id": "LR.AG15T99",
                "has_data": True,
                "has_data_post_threshold": False,
                "latest_year": 2019,
                "years_with_data": [2015, 2017, 2019],
                "years_post_threshold": [],
            }
        },
    }
    out = format_coverage_summary_table(coverage_result)
    # Returns a dict with 'rows' list and metadata keys
    assert isinstance(out, dict)
    assert "rows" in out
    assert len(out["rows"]) == 1
    assert out["rows"][0]["indicator_id"] == "LR.AG15T99"


# ── fetch_data: observed_only=False keeps modelled rows ────────────────────────
def test_fetch_observed_only_false_keeps_all():
    from tools import fetch_data
    page = {"total_count": 2, "results": [
        {"indicator_id": "CR.1", "country_id": "UZB", "year": "2019", "value": 88.0,
         "magnitude": "SUPP", "indicator_label_en": "x"},
        {"indicator_id": "CR.1", "country_id": "UZB", "year": "2020", "value": 90.0,
         "magnitude": None, "indicator_label_en": "x"},
    ]}
    with patch("tools.fetch_data._get", return_value=page):
        out = fetch_data.fetch_indicator_data(["CR.1"], "UZB", 2000, 2025, observed_only=False)
    assert out["CR.1"]["total_valid"] == 2  # SUPP row retained when filter off


# ── fetch_data: _paginate walks multiple pages ────────────────────────────────
def test_paginate_multipage():
    from tools import fetch_data
    pages = [
        {"total_count": 150, "results": [{"country_id": f"C{i}"} for i in range(100)]},
        {"total_count": 150, "results": [{"country_id": f"C{i}"} for i in range(100, 150)]},
    ]
    calls = {"n": 0}
    def fake_get(url, params=None):
        p = pages[calls["n"]]
        calls["n"] += 1
        return p
    with patch("tools.fetch_data._get", side_effect=fake_get):
        rows = fetch_data._paginate('indicator_id="X"', select="country_id")
    assert isinstance(rows, list)
    assert len(rows) == 150


# ── fetch_data: validate against API (mocked aggregation) ──────────────────────
def test_validate_indicator_ids_mocked():
    from tools import fetch_data
    page = {"total_count": 1, "results": [{"indicator_id": "CR.1"}]}
    with patch("tools.fetch_data._get", return_value=page):
        out = fetch_data.validate_indicator_ids_against_api(["CR.1", "FAKE.ID"])
    assert "CR.1" in out["confirmed"]
    assert "FAKE.ID" in out["not_in_api"]

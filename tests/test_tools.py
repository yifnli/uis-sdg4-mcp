"""
tests/test_tools.py
-------------------
Unit tests for UIS SDG4 MCP server tools.
Run with: pytest tests/ -v

Tests are split into:
  - Offline tests (no network): codebook, mapping, formatting
  - Online tests (require UIS API): marked with @pytest.mark.api
    Run online tests with: pytest tests/ -v -m api
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.map_indicators import (
    resolve_sdg_indicators,
    resolve_indicator_id,
    list_all_indicators,
    is_valid_record,
    get_validity_rules,
)
from tools.briefing import (
    format_country_briefing,
    format_trend_table,
    writing_style_note,
)


# ═══════════════════════════════════════════════════════════════
# OFFLINE TESTS — no network required
# ═══════════════════════════════════════════════════════════════

class TestResolveSDGIndicators:

    def test_known_global_indicator(self):
        r = resolve_sdg_indicators("4.6.1")
        assert "error" not in r
        assert r["sdg_number"] == "4.6.1"
        assert r["scope"] == "global"
        assert "LR.AG15T99" in r["indicator_ids"]
        assert "LR.AG15T24" in r["indicator_ids"]
        assert r["source"] == "validated_codebook"

    def test_471_includes_greening_education(self):
        """4.7.1 must include both GCS and SGE (greening education) component."""
        r = resolve_sdg_indicators("4.7.1")
        assert "error" not in r
        for iid in ["GCS.NATLEDUPOL", "GCS.CURRICULA", "SGE.EnvSust", "SGE.ClimCh",
                    "SGE.BioDiv", "SGE.Overall"]:
            assert iid in r["indicator_ids"], f"Missing {iid} in 4.7.1"

    def test_412_completion_rate(self):
        r = resolve_sdg_indicators("4.1.2")
        assert r["scope"] == "global"
        assert set(r["indicator_ids"]) == {"CR.1", "CR.2", "CR.3"}

    def test_414_out_of_school(self):
        r = resolve_sdg_indicators("4.1.4")
        assert r["scope"] == "thematic"
        assert "ROFST.1.CP" in r["indicator_ids"]
        assert "ROFST.AGM1.CP" in r["indicator_ids"]

    def test_sdg_prefix_stripped(self):
        r = resolve_sdg_indicators("SDG 4.6.1")
        assert r["sdg_number"] == "4.6.1"
        assert "error" not in r

    def test_ffa_indicator(self):
        r = resolve_sdg_indicators("FFA")
        assert "error" not in r
        assert "XGDP.FSGOV" in r["indicator_ids"]

    def test_1a2_indicator(self):
        r = resolve_sdg_indicators("1.a.2")
        assert "error" not in r
        assert "XGOVEXP.IMF" in r["indicator_ids"]

    def test_unknown_indicator_returns_error(self):
        r = resolve_sdg_indicators("9.9.9")
        assert "error" in r
        assert "available" in r

    def test_441_full_ict_skill_set(self):
        """4.4.1 should have all 32 ICT skill indicator IDs."""
        r = resolve_sdg_indicators("4.4.1")
        assert len(r["indicator_ids"]) == 32

    def test_4a1_all_school_levels(self):
        """4.a.1 should cover primary, lower-sec, upper-sec, and combined."""
        r = resolve_sdg_indicators("4.a.1")
        ids = r["indicator_ids"]
        assert any("SCHBSP.1." in i for i in ids)   # primary
        assert any("SCHBSP.2." in i for i in ids)   # lower secondary
        assert any("SCHBSP.3." in i for i in ids)   # upper secondary

    def test_4a4_empty(self):
        """4.a.4 (school meals) has no indicator IDs in current dataset."""
        r = resolve_sdg_indicators("4.a.4")
        assert r["indicator_ids"] == []
        assert "note" in r


class TestReverseIndicatorLookup:

    def test_cr1_maps_to_412(self):
        r = resolve_indicator_id("CR.1")
        assert r["sdg_number"] == "4.1.2"

    def test_lr_maps_to_461(self):
        r = resolve_indicator_id("LR.AG15T99")
        assert r["sdg_number"] == "4.6.1"

    def test_unknown_id_returns_error(self):
        r = resolve_indicator_id("FAKE.ID.XYZ")
        assert "error" in r


class TestListAllIndicators:

    def test_global_count(self):
        r = list_all_indicators("global")
        assert len(r["global"]) == 14

    def test_thematic_count(self):
        r = list_all_indicators("thematic")
        assert len(r["thematic"]) == 31

    def test_all_scope(self):
        r = list_all_indicators("all")
        assert "global" in r and "thematic" in r

    def test_each_entry_has_required_keys(self):
        r = list_all_indicators("all")
        for scope in ("global", "thematic"):
            for entry in r[scope]:
                assert "sdg_number"    in entry
                assert "label"         in entry
                assert "indicator_ids" in entry


class TestValidityRules:

    def test_supp_magnitude_invalid(self):
        assert not is_valid_record("SUPP", 99.5)

    def test_na_magnitude_invalid(self):
        assert not is_valid_record("NA", 50.0)

    def test_included_magnitude_invalid(self):
        assert not is_valid_record("INCLUDED", 75.0)

    def test_null_value_invalid(self):
        assert not is_valid_record("", None)

    def test_none_value_invalid(self):
        assert not is_valid_record(None, None)

    def test_modelled_cr_prefix_excluded(self):
        assert not is_valid_record("", 95.0, "CR.MOD.1")

    def test_modelled_lr_galp_excluded(self):
        assert not is_valid_record("", 85.0, "LR.GALP.AG15T99")

    def test_valid_cr_record(self):
        assert is_valid_record("", 82.4, "CR.1")

    def test_valid_lr_record(self):
        assert is_valid_record(None, 99.8, "LR.AG15T99")

    def test_valid_zero_value(self):
        assert is_valid_record("", 0.0, "CR.1")

    def test_case_insensitive_magnitude(self):
        assert not is_valid_record("supp", 99.5)
        assert not is_valid_record("Supp", 99.5)


class TestBriefingFormatter:

    _dummy_results = {
        "LR.AG15T99": {
            "records": [
                {"year": 2014, "value": 99.98, "magnitude": "", "source": "N/A"},
                {"year": 2015, "value": 99.98, "magnitude": "", "source": "N/A"},
                {"year": 2016, "value": 99.99, "magnitude": "", "source": "N/A"},
                {"year": 2019, "value": 100.0, "magnitude": "", "source": "N/A"},
                {"year": 2021, "value": 100.0, "magnitude": "", "source": "N/A"},
                {"year": 2022, "value": 100.0, "magnitude": "", "source": "N/A"},
            ],
            "years_with_data": [2014, 2015, 2016, 2019, 2021, 2022],
            "latest_year": 2022,
        },
        "LR.GALP.AG15T99": {
            "records": [],
            "years_with_data": [],
            "latest_year": None,
        },
    }

    def test_structure(self):
        b = format_country_briefing("Uzbekistan", "UZB", self._dummy_results)
        assert b["country"] == "Uzbekistan"
        assert b["iso3"]    == "UZB"
        assert "indicators" in b
        assert "summary"    in b

    def test_summary_counts(self):
        b = format_country_briefing("Uzbekistan", "UZB", self._dummy_results)
        assert b["summary"]["total_requested"] == 2
        assert b["summary"]["with_data"]       == 1
        assert b["summary"]["without_data"]    == 1  # LR.GALP.AG15T99 has empty records

    def test_gap_years_detected(self):
        b = format_country_briefing("Uzbekistan", "UZB", self._dummy_results)
        lr_section = next(s for s in b["indicators"] if s["indicator_id"] == "LR.AG15T99")
        # Years 2017, 2018, 2020 are gaps in [2014-2022]
        assert 2017 in lr_section["gap_years_in_range"]
        assert 2018 in lr_section["gap_years_in_range"]
        assert 2020 in lr_section["gap_years_in_range"]

    def test_post_threshold(self):
        b = format_country_briefing("Uzbekistan", "UZB", self._dummy_results, threshold_year=2020)
        lr_section = next(s for s in b["indicators"] if s["indicator_id"] == "LR.AG15T99")
        assert lr_section["has_data_post_threshold"] is True

    def test_yoy_change_computed(self):
        b = format_country_briefing("Uzbekistan", "UZB", self._dummy_results)
        lr_section = next(s for s in b["indicators"] if s["indicator_id"] == "LR.AG15T99")
        assert lr_section["year_over_year_change"] is not None

    def test_writing_style_note_present(self):
        note = writing_style_note()
        assert "neutral" in note.lower()
        assert "evaluative" in note.lower()


class TestTrendTableFormatter:

    def test_basic_format(self):
        records = [
            {"year": 2018, "value": 99.5, "magnitude": "", "source": "N/A"},
            {"year": 2019, "value": 99.8, "magnitude": "", "source": "N/A"},
            {"year": 2021, "value": 100.0, "magnitude": "", "source": "N/A"},
        ]
        t = format_trend_table("LR.AG15T99", records)
        assert t["record_count"] == 3
        assert t["year_range"]   == "2018–2021"

    def test_gap_detected(self):
        records = [
            {"year": 2018, "value": 99.5, "magnitude": "", "source": "N/A"},
            {"year": 2021, "value": 100.0, "magnitude": "", "source": "N/A"},
        ]
        t = format_trend_table("LR.AG15T99", records)
        last_row = t["rows"][-1]
        assert last_row["gap_years_before"] == 2  # 2019 and 2020 missing

    def test_empty_records(self):
        t = format_trend_table("LR.AG15T99", [])
        assert t["rows"] == []
        assert "note" in t


# ═══════════════════════════════════════════════════════════════
# ONLINE TESTS — require UIS API access
# Mark: pytest tests/ -v -m api
# ═══════════════════════════════════════════════════════════════

@pytest.mark.api
class TestAPIFetch:

    def test_fetch_uzb_literacy(self):
        from tools.fetch_data import fetch_indicator_data
        result = fetch_indicator_data(["LR.AG15T99"], "UZB", 2014, 2024)
        assert "LR.AG15T99" in result
        r = result["LR.AG15T99"]
        assert "error" not in r
        assert r["total_valid"] > 0
        assert r["latest_year"] is not None

    def test_modelled_excluded_by_default(self):
        from tools.fetch_data import fetch_indicator_data
        # LR.GALP.* are modelled — should return 0 valid records under observed_only=True
        result = fetch_indicator_data(["LR.GALP.AG15T99"], "UZB", 2014, 2024, observed_only=True)
        r = result.get("LR.GALP.AG15T99", {})
        # Either 0 valid records or an API error (indicator may not exist)
        assert r.get("total_valid", 0) == 0 or "error" in r

    def test_invalid_geo_unit(self):
        from tools.fetch_data import fetch_indicator_data
        result = fetch_indicator_data(["LR.AG15T99"], "INVALID", 2020, 2024)
        r = result["LR.AG15T99"]
        # Should either error gracefully or return 0 records — not crash
        assert "error" in r or r.get("total_valid", 0) == 0

    def test_validate_codebook_ids_against_api(self):
        """Spot-check that core codebook IDs exist in the live API."""
        from tools.fetch_data import validate_indicator_ids_against_api
        check_ids = ["LR.AG15T99", "LR.AG15T24", "CR.1", "CR.2", "CR.3"]
        result = validate_indicator_ids_against_api(check_ids)
        if "error" in result:
            pytest.skip(f"API not reachable: {result['error']}")
        assert len(result["confirmed"]) > 0, "None of the core IDs found in API"

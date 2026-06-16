"""
tests/test_datahub.py
---------------------
Unit tests for the Opendatasoft (DataHub) client in tools/fetch_data.py.
HTTP is mocked — these run offline (no `api` marker).
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.fetch_data import _build_where, fetch_indicator_data


def test_build_where_single_indicator_and_country():
    w = _build_where(["LR.AG15T99"], "UZB", 2000, 2025)
    assert 'country_id="UZB"' in w
    assert 'indicator_id in ("LR.AG15T99")' in w
    assert "year>=2000" in w
    assert "year<=2025" in w
    assert " and " in w


def test_build_where_multiple_indicators_quoted():
    w = _build_where(["A.B", "C.D"], "TZA", 2010, 2020)
    assert 'indicator_id in ("A.B","C.D")' in w


def test_build_where_world_omits_country():
    w = _build_where(["A.B"], "all", 2000, 2025)
    assert "country_id" not in w


def _fake_page(results, total):
    return {"total_count": total, "results": results}


def test_fetch_casts_year_to_int_and_groups_by_indicator():
    page = _fake_page(
        [
            {"indicator_id": "LR.AG15T99", "country_id": "UZB", "year": "2018",
             "value": 99.98, "magnitude": None, "indicator_label_en": "Literacy"},
            {"indicator_id": "LR.AG15T99", "country_id": "UZB", "year": "2021",
             "value": 100.0, "magnitude": None, "indicator_label_en": "Literacy"},
        ],
        total=2,
    )
    with patch("tools.fetch_data._get", return_value=page):
        out = fetch_indicator_data(["LR.AG15T99"], "UZB", 2000, 2025)
    rec = out["LR.AG15T99"]
    assert rec["years_with_data"] == [2018, 2021]
    assert rec["latest_year"] == 2021
    assert all(isinstance(r["year"], int) for r in rec["records"])


def test_fetch_excludes_invalid_magnitude():
    page = _fake_page(
        [
            {"indicator_id": "CR.1", "country_id": "UZB", "year": "2019",
             "value": 88.0, "magnitude": "SUPP", "indicator_label_en": "Completion"},
            {"indicator_id": "CR.1", "country_id": "UZB", "year": "2020",
             "value": 90.0, "magnitude": None, "indicator_label_en": "Completion"},
        ],
        total=2,
    )
    with patch("tools.fetch_data._get", return_value=page):
        out = fetch_indicator_data(["CR.1"], "UZB", 2000, 2025)
    rec = out["CR.1"]
    assert rec["total_raw"] == 2
    assert rec["total_valid"] == 1
    assert rec["years_with_data"] == [2020]


def test_fetch_returns_empty_for_unknown_indicator():
    with patch("tools.fetch_data._get", return_value=_fake_page([], total=0)):
        out = fetch_indicator_data(["NOPE.X"], "UZB", 2000, 2025)
    assert out["NOPE.X"]["total_valid"] == 0
    assert out["NOPE.X"]["years_with_data"] == []
    assert out["NOPE.X"]["latest_year"] is None


def test_fetch_propagates_http_error():
    with patch("tools.fetch_data._get", return_value={"_error": "HTTP 500"}):
        out = fetch_indicator_data(["CR.1"], "UZB", 2000, 2025)
    assert "error" in out["CR.1"]

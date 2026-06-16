"""
tests/test_population_backfill.py
---------------------------------
Regression tests for the population codebook after the wdi001 backfill.
Offline — reads the committed codebooks/population_2025.json. No network.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_ROOT = Path(__file__).parent.parent


def _load():
    with open(_ROOT / "codebooks" / "population_2025.json", encoding="utf-8") as f:
        return json.load(f)


def test_korea_population_present_and_reasonable():
    pop = _load()["population_by_iso3"]
    assert "KOR" in pop
    assert 40_000_000 < pop["KOR"] < 60_000_000  # ~51.7M


def test_high_income_countries_present():
    pop = _load()["population_by_iso3"]
    for iso3 in ["DEU", "FRA", "GBR", "BRA", "MEX", "AUS", "ITA", "ESP"]:
        assert iso3 in pop and pop[iso3], f"{iso3} missing population"


def test_total_world_population_recomputed():
    d = _load()
    pop = d["population_by_iso3"]
    assert d["_total_world_population"] == sum(v for v in pop.values() if v)
    assert d["_total_world_population"] > 7_000_000_000


def test_resolve_country_korea_non_null():
    from tools.resolve_country import resolve_country
    assert resolve_country("South Korea")["population_2025"] is not None

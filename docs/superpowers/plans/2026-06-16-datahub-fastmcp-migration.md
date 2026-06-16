# DataHub + FastMCP + uv Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repoint the UIS SDG4 MCP server from the legacy `api.uis.unesco.org` API to the UNESCO DataHub (`data.unesco.org`, Opendatasoft Explore API v2.1, dataset `uis001`), rewrite the server on FastMCP v2, and manage the project with `uv`.

**Architecture:** The codebook-grounding stays intact — `map_indicators`, `resolve_country`, and `briefing` are untouched. Only the network layer changes: `fetch_data.py` becomes a thin Opendatasoft (ODS) client against the single `uis001` dataset, `coverage.py`'s world path switches from 214-calls-per-indicator to one ODS `group_by` aggregation, and `validate_indicator_ids` queries `uis001`. `server.py` is replaced by a FastMCP `@mcp.tool` server, deleting the manual `list_tools()`/`call_tool()` dispatch. Return-dict shapes are preserved so downstream formatters need no changes.

**Tech Stack:** Python 3.10+, `uv` (project + deps + runner), `fastmcp>=2.0`, `requests` (sync), Opendatasoft Explore API v2.1.

---

## Background: the DataHub API (verified facts)

All confirmed against the live API on 2026-06-16:

- **Base:** `https://data.unesco.org/api/explore/v2.1/catalog/datasets/uis001`
- **Records endpoint:** `GET {base}/records?where=...&select=...&limit=...&offset=...`
  - `limit` max **100** per page; `offset + limit` must stay ≤ 10000.
  - Response shape: `{"total_count": int, "results": [ {record}, ... ]}`
- **Record fields:** `indicator_id` (str), `country_id` (ISO3, e.g. `"UZB"`), `year` (str, e.g. `"2002"`), `value` (float), `magnitude` (null or code), `qualifier`, `indicator_label_en`, `country_name_en`, `regional_group`.
- **ODSQL `where` syntax** (URL-encoded automatically by `requests` params):
  - String equality: `country_id="UZB"` (double quotes around literals).
  - IN list: `indicator_id in ("LR.AG15T99","LR.AG15T24")`.
  - Numeric on year (string field, ODS coerces): `year>=2000 and year<=2025`, `year>2020`.
  - Combine with `and`.
- **Aggregation (coverage):** `GET {base}/records?where=indicator_id="X" and year>2020&group_by=country_id&select=country_id&limit=100&offset=0` returns one result row per distinct `country_id`. Paginate with `offset` (≤214 groups → ≤3 pages).
- **magnitude values present in uis001:** only `null` (≈1.44M) and `"NIL"` (≈24.5k). The legacy excluded magnitudes (`SUPP`, `NA`, `INCLUDED`) do not appear here, but the filter is kept for defensiveness / other datasets.
- **uis001 carries BOTH observed and modelled estimates** — modelled IDs `CR.MOD.*` are present (12 variants confirmed 2026-06-16). The codebook `excluded_id_prefixes` filter (`CR.MOD.`, `LR.GALP.`) is therefore **required**, not redundant — it is what keeps modelled estimates out of "observed" results.
- **ODSQL `like`/`%` is unreliable for prefix matching** (token-boundary sensitive: `like "LR.AG15%"` returns 0 while exact `indicator_id="LR.AG15T99"` returns 1,140). Always use exact codebook IN-lists; never `like` prefixes. `group_by` `total_count` is capped to `limit` — use `/facets` to count distinct values.
- Full platform comparison: see `docs/datahub-vs-uis-api.md`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `pyproject.toml` | uv project metadata + deps (`fastmcp`, `requests`); `pandas` moved to `[scripts]` extra | Modify |
| `tools/fetch_data.py` | ODS client for `uis001`: `fetch_indicator_data`, `validate_indicator_ids_against_api`, `fetch_distinct_countries` | Rewrite |
| `tools/coverage.py` | World path uses ODS `group_by` aggregation; single-country path unchanged logic | Modify |
| `server.py` | FastMCP `@mcp.tool` server + preserved `--test` self-test | Rewrite |
| `tools/map_indicators.py` | SDG→ID resolution + validity filter | **Unchanged** |
| `tools/resolve_country.py` | country resolution + population coverage | **Unchanged** |
| `tools/briefing.py` | briefing formatter | **Unchanged** |
| `codebooks/validity_rules.json` | API config block updated to ODS base/dataset | Modify |
| `tests/test_tools.py` | offline tests unchanged; api-marked tests repointed to ODS | Modify |
| `tests/test_datahub.py` | new: ODS client unit tests with mocked HTTP | Create |
| `README.md` / `CLAUDE.md` | uv + DataHub + FastMCP docs | Modify |
| `requirements.txt` | deleted (uv-managed) | Delete |

**Decisions locked in (no need to revisit during execution):**
- Keep `requests` (sync). FastMCP supports sync tools; async is YAGNI here.
- Single dataset `uis001` is the only source. Other UIS datasets (uis006 OPRI etc.) are out of scope.
- `country_id` in `uis001` is already ISO3 → no mapping change; `resolve_country` still used for name→ISO3.
- `year` is cast to `int` in the client so all downstream int comparisons keep working.
- Validity filter (`is_valid_record`) is retained unchanged and still applied in the client.

---

## Task 1: Convert project to uv

**Files:**
- Modify: `pyproject.toml`
- Delete: `requirements.txt`

- [ ] **Step 1: Verify uv is installed**

Run: `uv --version`
Expected: prints a version (e.g. `uv 0.5.x`). If "command not found", install: `curl -LsSf https://astral.sh/uv/install.sh | sh` then re-open shell.

- [ ] **Step 2: Rewrite `pyproject.toml` dependencies**

Replace the `dependencies` list and `[project.optional-dependencies]` / `[project.scripts]` blocks. Full new file content:

```toml
[project]
name = "uis-sdg4-mcp"
version = "0.3.0"
description = "MCP server for querying UNESCO DataHub SDG4 education indicator data via natural language"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
  { name = "UNESCO Institute for Statistics" }
]
keywords = ["unesco", "uis", "sdg4", "education", "mcp", "ai", "datahub", "opendatasoft"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Science/Research",
  "Topic :: Scientific/Engineering :: Information Analysis",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]
dependencies = [
  "fastmcp>=2.0.0",
  "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=7.0",
  "pytest-asyncio>=0.23",
]
scripts = [
  "pandas>=2.0.0",
  "openpyxl>=3.1.0",
]

[project.scripts]
uis-sdg4-mcp = "server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tools", "codebooks"]

[tool.pytest.ini_options]
markers = [
  "api: marks tests that require a live DataHub API connection (deselect with -m 'not api')",
]
asyncio_mode = "auto"
```

- [ ] **Step 3: Generate the lockfile and environment**

Run: `uv sync --extra dev`
Expected: creates `.venv/`, resolves `fastmcp`, `requests`, `pytest`; writes `uv.lock`. No errors.

- [ ] **Step 4: Verify FastMCP imports under uv**

Run: `uv run python -c "import fastmcp, requests; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Delete the old requirements file**

Run: `git rm requirements.txt`
Expected: staged for deletion.

- [ ] **Step 6: Update `.gitignore` for uv (add `.venv/` if not already covered)**

`.gitignore` already lists `venv/` and `.venv/`. Confirm `.venv/` is present; no edit needed if so. Verify: `grep -n '.venv' .gitignore` → expect a match.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "build: migrate project to uv, switch to fastmcp deps"
```

---

## Task 2: Update codebook API config to DataHub

**Files:**
- Modify: `codebooks/validity_rules.json`

- [ ] **Step 1: Replace the `api` block in `codebooks/validity_rules.json`**

Find the existing `"api": { ... }` block and replace it with:

```json
  "api": {
    "platform": "opendatasoft-explore-v2.1",
    "base_url": "https://data.unesco.org/api/explore/v2.1",
    "dataset_id": "uis001",
    "dataset_title": "SDG 4 Education Indicators (Global & Thematic)",
    "endpoints": {
      "records": "/catalog/datasets/uis001/records"
    },
    "max_page_limit": 100,
    "default_timeout_seconds": 20,
    "retry_attempts": 2
  },
```

Leave the `validity`, `coverage`, `population`, and `writing_style` blocks unchanged.

- [ ] **Step 2: Verify JSON still parses**

Run: `uv run python -c "import json; json.load(open('codebooks/validity_rules.json')); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add codebooks/validity_rules.json
git commit -m "config: point validity_rules api block at DataHub uis001"
```

---

## Task 3: Rewrite the ODS client (`tools/fetch_data.py`)

**Files:**
- Rewrite: `tools/fetch_data.py`
- Test: `tests/test_datahub.py`

The client preserves the exact return shape of `fetch_indicator_data` so `coverage.py` and `briefing.py` need no changes:
`{ indicator_id: {"geo_unit","total_raw","total_valid","years_with_data","latest_year","records":[{"year","value","magnitude","source","geo_unit"}]} }`.

- [ ] **Step 1: Write failing tests for the where-clause builder and year casting**

Create `tests/test_datahub.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_datahub.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_where'` (module not yet rewritten).

- [ ] **Step 3: Rewrite `tools/fetch_data.py`**

Replace the entire file with:

```python
"""
tools/fetch_data.py
-------------------
Client for the UNESCO DataHub (Opendatasoft Explore API v2.1), dataset `uis001`
(SDG 4 Education Indicators — Global & Thematic).

Applies UIS validity filtering before returning records. The AI receives only
clean, observed data — never raw API responses. Return shapes are kept identical
to the previous api.uis.unesco.org client so downstream formatters are unaffected.
"""

import json
import time
from pathlib import Path

import requests

from tools.map_indicators import is_valid_record

_ROOT = Path(__file__).parent.parent
with open(_ROOT / "codebooks" / "validity_rules.json", encoding="utf-8") as _f:
    _RULES = json.load(_f)

_API        = _RULES["api"]
_BASE_URL   = _API["base_url"]
_DATASET    = _API["dataset_id"]
_RECORDS_URL = f"{_BASE_URL}/catalog/datasets/{_DATASET}/records"
_MAX_LIMIT  = _API.get("max_page_limit", 100)
_TIMEOUT    = _API.get("default_timeout_seconds", 20)
_RETRIES    = _API.get("retry_attempts", 2)


def _get(url: str, params: dict | None = None) -> dict | None:
    """GET with retry logic. Returns parsed JSON, or {'_error': ...} on failure."""
    for attempt in range(_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            if attempt < _RETRIES:
                time.sleep(2 ** attempt)
                continue
            return {"_error": "Request timed out after retries.", "url": url}
        except requests.exceptions.HTTPError as e:
            return {"_error": f"HTTP {r.status_code}: {str(e)}", "url": url}
        except requests.exceptions.RequestException as e:
            return {"_error": str(e), "url": url}
    return None


def _q(s: str) -> str:
    """Quote an ODSQL string literal (double quotes)."""
    return '"' + str(s).replace('"', '\\"') + '"'


def _build_where(
    indicator_ids: list[str],
    geo_unit: str,
    start_year: int,
    end_year: int,
) -> str:
    """Build an ODSQL `where` clause for uis001."""
    clauses = []
    if geo_unit and geo_unit != "all":
        clauses.append(f"country_id={_q(geo_unit)}")
    if indicator_ids:
        id_list = ",".join(_q(i) for i in indicator_ids)
        clauses.append(f"indicator_id in ({id_list})")
    clauses.append(f"year>={int(start_year)}")
    clauses.append(f"year<={int(end_year)}")
    return " and ".join(clauses)


def _paginate(where: str, select: str | None = None, group_by: str | None = None) -> list[dict] | dict:
    """
    Fetch all pages for a query. Returns the combined results list, or a
    {'_error': ...} dict if any page fails.
    """
    collected: list[dict] = []
    offset = 0
    while True:
        params = {"where": where, "limit": _MAX_LIMIT, "offset": offset}
        if select:
            params["select"] = select
        if group_by:
            params["group_by"] = group_by
        data = _get(_RECORDS_URL, params)
        if data is None or "_error" in (data or {}):
            return data or {"_error": "Unknown error"}
        results = data.get("results", [])
        collected.extend(results)
        total = data.get("total_count", len(collected))
        offset += _MAX_LIMIT
        if offset >= total or not results or offset >= 10000:
            break
    return collected


def fetch_indicator_data(
    indicator_ids: list[str],
    geo_unit: str,
    start_year: int = 2000,
    end_year: int = 2025,
    include_metadata: bool = False,
    observed_only: bool = True,
) -> dict:
    """
    Fetch data from DataHub uis001 for one or more indicator IDs and a geo unit.

    Returns a dict keyed by indicator_id; each value is either
    {"error": ...} or {"geo_unit","total_raw","total_valid",
    "years_with_data","latest_year","records":[...]}.
    All indicators are fetched in a single ODSQL query (IN-list), then grouped
    in Python. `include_metadata` is accepted for signature compatibility.
    """
    where = _build_where(indicator_ids, geo_unit, start_year, end_year)
    rows = _paginate(
        where,
        select="indicator_id,country_id,year,value,magnitude,indicator_label_en",
    )

    results: dict = {}

    if isinstance(rows, dict) and "_error" in rows:
        # Whole query failed — report the error per indicator.
        for iid in indicator_ids:
            results[iid] = {"error": rows["_error"], "geo_unit": geo_unit}
        return results

    # Bucket rows by indicator_id.
    by_id: dict[str, list[dict]] = {iid: [] for iid in indicator_ids}
    for row in rows:
        iid = row.get("indicator_id")
        if iid in by_id:
            by_id[iid].append(row)

    for iid, raw_records in by_id.items():
        valid = []
        for rec in raw_records:
            mag   = rec.get("magnitude") or ""
            value = rec.get("value")
            if (not observed_only) or is_valid_record(mag, value, iid):
                year = rec.get("year")
                valid.append({
                    "year":      int(year) if year not in (None, "") else None,
                    "value":     value,
                    "magnitude": mag,
                    "source":    rec.get("indicator_label_en", "N/A"),
                    "geo_unit":  rec.get("country_id", geo_unit),
                })

        valid.sort(key=lambda r: r["year"] or 0)
        years_with_data = sorted({r["year"] for r in valid if r["year"] is not None})

        results[iid] = {
            "geo_unit":        geo_unit,
            "total_raw":       len(raw_records),
            "total_valid":     len(valid),
            "years_with_data": years_with_data,
            "latest_year":     years_with_data[-1] if years_with_data else None,
            "records":         valid,
        }

    return results


def fetch_distinct_countries(
    indicator_id: str,
    after_year: int | None = None,
) -> list[str] | dict:
    """
    Return the list of distinct ISO3 country_ids that have data for an indicator,
    using a single ODS group_by aggregation (paginated). Optionally restrict to
    records with year strictly greater than `after_year`.

    Returns a list of ISO3 strings, or {'_error': ...} on failure.
    """
    clauses = [f"indicator_id={_q(indicator_id)}"]
    if after_year is not None:
        clauses.append(f"year>{int(after_year)}")
    where = " and ".join(clauses)

    rows = _paginate(where, select="country_id", group_by="country_id")
    if isinstance(rows, dict) and "_error" in rows:
        return rows
    iso3s = sorted({r.get("country_id") for r in rows if r.get("country_id")})
    return iso3s


def validate_indicator_ids_against_api(indicator_ids: list[str]) -> dict:
    """
    Check which of the given indicator IDs exist in uis001, via one group_by
    aggregation over indicator_id filtered to the requested IDs.
    Returns confirmed / not_in_api lists.
    """
    if not indicator_ids:
        return {"confirmed": [], "not_in_api": [], "total_checked": 0}

    id_list = ",".join(_q(i) for i in indicator_ids)
    where = f"indicator_id in ({id_list})"
    rows = _paginate(where, select="indicator_id", group_by="indicator_id")
    if isinstance(rows, dict) and "_error" in rows:
        return {"error": rows["_error"], "checked": False}

    present = {r.get("indicator_id", "").upper() for r in rows if r.get("indicator_id")}
    confirmed = [i for i in indicator_ids if i.upper() in present]
    missing   = [i for i in indicator_ids if i.upper() not in present]

    return {
        "confirmed":     confirmed,
        "not_in_api":    missing,
        "total_checked": len(indicator_ids),
        "dataset":       _DATASET,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_datahub.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_data.py tests/test_datahub.py
git commit -m "feat: rewrite fetch_data as DataHub uis001 ODS client"
```

---

## Task 4: Switch world coverage to ODS aggregation

**Files:**
- Modify: `tools/coverage.py:88-180` (the `else:` world-coverage branch and its trailing `note`)
- Test: `tests/test_datahub.py` (append)

- [ ] **Step 1: Write a failing test for aggregation-based world coverage**

Append to `tests/test_datahub.py`:

```python
from unittest.mock import patch as _patch
from tools.coverage import compute_coverage


def test_world_coverage_uses_distinct_countries():
    def fake_distinct(indicator_id, after_year=None):
        if after_year is None:
            return ["CHN", "IND", "USA", "FRA"]
        return ["CHN", "IND"]  # only these have post-threshold data

    with _patch("tools.coverage.fetch_distinct_countries", side_effect=fake_distinct):
        out = compute_coverage(["LR.AG15T99"], geo_unit="all", threshold_year=2020)

    cov = out["indicators"]["LR.AG15T99"]
    assert cov["coverage_any_data"]["n_countries"] == 4
    assert cov["coverage_post_threshold"]["n_countries"] == 2
    assert set(cov["coverage_post_threshold"]["covered_iso3s"]) == {"CHN", "IND"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_datahub.py::test_world_coverage_uses_distinct_countries -v`
Expected: FAIL — `ImportError`/`AttributeError` for `fetch_distinct_countries` in `tools.coverage` (not imported yet).

- [ ] **Step 3: Update the import line in `tools/coverage.py`**

Change:

```python
from tools.fetch_data import fetch_indicator_data
```

to:

```python
from tools.fetch_data import fetch_indicator_data, fetch_distinct_countries
```

- [ ] **Step 4: Replace the world-coverage `else:` branch**

Replace the entire `else:` block (everything from `else:` through the end of the `compute_coverage` function's final `return` for the world case — currently the per-country fetch loop) with:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_datahub.py::test_world_coverage_uses_distinct_countries -v`
Expected: PASS.

- [ ] **Step 6: Run the full offline suite to confirm no regressions**

Run: `uv run pytest tests/ -v -m "not api"`
Expected: PASS (all offline tests, including the existing `test_tools.py`).

- [ ] **Step 7: Commit**

```bash
git add tools/coverage.py tests/test_datahub.py
git commit -m "perf: world coverage via DataHub group_by aggregation"
```

---

## Task 5: Rewrite `server.py` on FastMCP

**Files:**
- Rewrite: `server.py`

Each of the 11 tools becomes a `@mcp.tool` function. Docstrings carry the descriptions (FastMCP turns them into tool descriptions); type hints generate the input schema. The `--test` self-test is preserved verbatim (it calls pure functions, no network).

- [ ] **Step 1: Rewrite `server.py`**

Replace the entire file with:

```python
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
```

- [ ] **Step 2: Run the offline self-test**

Run: `uv run python server.py --test`
Expected: prints 10 `✓` lines then `✓ All self-tests passed (10 checks).`

- [ ] **Step 3: Verify the server starts and lists 11 tools (stdio handshake)**

Run:
```bash
uv run python -c "import server; print(sorted(t for t in server.mcp._tool_manager._tools))" 2>/dev/null \
  || uv run python -c "import asyncio, server; print(len(asyncio.run(server.mcp.get_tools())))"
```
Expected: prints the tool names or the count `11`. (FastMCP's internal accessor name may vary by version; either form confirms registration. If both fail, run `uv run fastmcp inspect server.py` and confirm 11 tools are listed.)

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: rewrite MCP server on FastMCP v2"
```

---

## Task 6: Repoint the live API tests

**Files:**
- Modify: `tests/test_tools.py` (the `@pytest.mark.api` classes/functions)

- [ ] **Step 1: Inspect the existing api-marked tests**

Run: `uv run grep -n "pytest.mark.api\|api.uis.unesco\|def test" tests/test_tools.py`
Expected: lists the api-marked tests and any hard-coded references to the old host.

- [ ] **Step 2: Add a live DataHub smoke test**

Append to `tests/test_tools.py`:

```python
@pytest.mark.api
class TestDataHubLive:
    def test_fetch_real_country_indicator(self):
        from tools.fetch_data import fetch_indicator_data
        out = fetch_indicator_data(["LR.AG15T99"], "UZB", 2000, 2025)
        rec = out["LR.AG15T99"]
        assert "error" not in rec
        assert rec["total_valid"] >= 1
        assert rec["latest_year"] is not None

    def test_validate_real_ids(self):
        from tools.fetch_data import validate_indicator_ids_against_api
        out = validate_indicator_ids_against_api(["LR.AG15T99", "TOTALLY.FAKE.ID"])
        assert "LR.AG15T99" in out["confirmed"]
        assert "TOTALLY.FAKE.ID" in out["not_in_api"]

    def test_world_coverage_real(self):
        from tools.coverage import compute_coverage
        out = compute_coverage(["LR.AG15T99"], geo_unit="all", threshold_year=2015)
        cov = out["indicators"]["LR.AG15T99"]["coverage_any_data"]
        assert cov["n_countries"] >= 10
```

- [ ] **Step 3: Remove or update any old api-marked tests that reference `api.uis.unesco.org` directly**

For each pre-existing `@pytest.mark.api` test that asserts on the old API's response shape (e.g. raw `records` from `api.uis.unesco.org`), update its assertions to the new `fetch_indicator_data` return shape (`total_valid`, `years_with_data`, `latest_year`) or delete it if `TestDataHubLive` already covers the behaviour. Do not leave a test pointed at the decommissioned host.

- [ ] **Step 4: Run the offline suite (must stay green without network)**

Run: `uv run pytest tests/ -v -m "not api"`
Expected: PASS.

- [ ] **Step 5: Run the live suite (requires internet)**

Run: `uv run pytest tests/ -v -m api`
Expected: PASS — `TestDataHubLive` hits data.unesco.org and returns real records.

- [ ] **Step 6: Commit**

```bash
git add tests/test_tools.py
git commit -m "test: repoint live API tests at DataHub uis001"
```

---

## Task 7: Update docs (README + CLAUDE.md)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `README.md`**

Make these edits:
- Replace the intro line "via the UIS public API" with "via the UNESCO DataHub (data.unesco.org, Opendatasoft) dataset `uis001`".
- Replace the Installation block's `python -m venv` / `pip install -r requirements.txt` steps with:

```bash
# 1. Clone
git clone https://github.com/<your-username>/uis-sdg4-mcp.git
cd uis-sdg4-mcp

# 2. Install uv (https://docs.astral.sh/uv/) if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Sync dependencies (creates .venv, writes uv.lock)
uv sync --extra dev

# 4. Offline self-test
uv run python server.py --test

# 5. Offline test suite
uv run pytest tests/ -v -m "not api"

# 6. Live DataHub tests (requires internet)
uv run pytest tests/ -v -m api
```

- In the Claude Desktop config JSON, replace the `command`/`args` with the uv form:

```json
{
  "mcpServers": {
    "uis-sdg4": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/uis-sdg4-mcp", "run", "python", "server.py"]
    }
  }
}
```

- Update the "Codebook structure" note: `validity_rules.json` now documents the DataHub/ODS `api` block (base_url, dataset_id uis001).
- Update `get_indicator_data` / `validate_indicator_ids` tool descriptions to say "DataHub dataset uis001" instead of "UIS API".

- [ ] **Step 2: Update `CLAUDE.md`**

Apply these edits to `CLAUDE.md`:

- Replace the "What this is" data-source sentence with: "an MCP stdio server (FastMCP v2) exposing UNESCO DataHub (data.unesco.org, Opendatasoft Explore API v2.1, dataset `uis001`) SDG 4 education data to AI clients."
- Replace the entire "Commands" block with:

```bash
uv sync --extra dev                      # Install deps, create .venv, write uv.lock
uv run python server.py --test           # Offline self-test (10 checks, no network)
uv run python server.py                  # Run as stdio MCP server
uv run pytest tests/ -v -m "not api"     # Offline suite (codebook, mapping, ODS client mocked)
uv run pytest tests/ -v -m api           # Live DataHub tests — require data.unesco.org
uv run python server.py --test           # single fastest sanity check
uv run --extra scripts python scripts/generate_population_codebook.py   # regen population (needs pandas)
```

- Replace the "Setup reality" paragraph with: "Managed by `uv` — there is no `requirements.txt` or hand-made venv. `uv sync` creates `.venv` and `uv.lock`. Always invoke via `uv run …`."
- In the Architecture section, replace the `server.py` description with: "`server.py` is a FastMCP v2 server — each tool is an `@mcp.tool`-decorated function delegating to a pure function in `tools/`; type hints + docstrings generate the schema. To add a tool, add one decorated function (no separate schema list)."
- Update the `fetch_data.py` bullet to: "`fetch_data.py` — Opendatasoft client for dataset `uis001`. `_build_where()` builds ODSQL; `_paginate()` pages at limit 100; `fetch_indicator_data()` pulls all requested indicator IDs in one IN-list query and buckets them in Python; `fetch_distinct_countries()` powers world coverage via `group_by(country_id)`."
- In the codebooks bullet for `validity_rules.json`, note the `api` block now holds the ODS base_url + `dataset_id: uis001` + `max_page_limit: 100`.
- Add a line to the validity/gotchas section: "DataHub `year` is a string (`"2002"`) — the client casts to int. `magnitude` in uis001 is only `null`/`NIL`; the SUPP/NA/INCLUDED filter is retained for defensiveness."

- [ ] **Step 3: Verify both docs reference no stale commands**

Run: `uv run grep -rn "requirements.txt\|api.uis.unesco.org\|python -m venv\|python server.py" README.md CLAUDE.md`
Expected: no matches for `requirements.txt`, `api.uis.unesco.org`, or `python -m venv`; any remaining `python server.py` occurrences are prefixed with `uv run`.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: update README and CLAUDE.md for DataHub + FastMCP + uv"
```

---

## Task 8: Final end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Clean offline run**

Run: `uv run python server.py --test && uv run pytest tests/ -v -m "not api"`
Expected: self-test prints "(10 checks)"; offline suite all PASS.

- [ ] **Step 2: Live end-to-end via the public tools**

Run:
```bash
uv run python -c "
from tools.resolve_country import resolve_country
from tools.map_indicators import resolve_sdg_indicators
from tools.fetch_data import fetch_indicator_data
from tools.briefing import format_country_briefing
iso3 = resolve_country('Uzbekistan')['iso3']
ids = resolve_sdg_indicators('4.6.1')['indicator_ids']
data = fetch_indicator_data(ids, iso3, 2010, 2025)
b = format_country_briefing('Uzbekistan', iso3, data)
print('iso3=', iso3, 'n_indicators=', len(ids), 'with_data=', b['summary']['with_data'])
"
```
Expected: prints `iso3= UZB`, a non-zero `n_indicators`, and `with_data` ≥ 1 — proving the full DataHub path works.

- [ ] **Step 3: Live coverage check**

Run:
```bash
uv run python -c "
from tools.coverage import compute_sdg_coverage
out = compute_sdg_coverage('4.6.1', geo_unit='all', threshold_year=2015)
iid = next(iter(out['indicators']))
print('countries_any=', out['indicators'][iid]['coverage_any_data']['n_countries'])
"
```
Expected: prints `countries_any=` with a value ≥ 10.

- [ ] **Step 4: Confirm git state is clean and the branch is ready**

Run: `git status && git log --oneline -8`
Expected: working tree clean; commits from Tasks 1–7 present.

---

## Self-Review

**Spec coverage:**
- "switch current api to datahub" → Tasks 2–6 (config, client, coverage, server, tests all repointed to `uis001`). ✓
- "set the project with uv" → Task 1 (pyproject + uv.lock + remove requirements.txt). ✓
- "use fastmcp for this mcp" → Task 5 (FastMCP v2 server). ✓
- Docs/verification → Tasks 7–8. ✓

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Task 6 Step 3 is a conditional edit (update-or-delete pre-existing api tests) with explicit criteria, not a placeholder. Full code given for every rewritten module.

**Type consistency:**
- `fetch_indicator_data` return shape (`geo_unit/total_raw/total_valid/years_with_data/latest_year/records[{year:int,value,magnitude,source,geo_unit}]`) is identical to the legacy shape consumed by `coverage.py` and `briefing.py` → unchanged downstream. ✓
- `fetch_distinct_countries(indicator_id, after_year=None)` signature matches its mock in Task 4 and its call sites in `coverage.py`. ✓
- `validate_indicator_ids_against_api` keeps `confirmed`/`not_in_api`/`total_checked` keys used by the `validate_indicator_ids` tool. ✓
- `year` is cast to `int` in the client, so `coverage.py`'s `r["year"] > threshold_year` int-comparisons remain valid. ✓

**Confirmed (no longer a risk):** modelled-estimate IDs `CR.MOD.*` DO exist in `uis001` (verified 2026-06-16), so the validity filter's `excluded_id_prefixes` is load-bearing — keep it. **Remaining open question:** whether `uis001` has full indicator coverage for all 45 codebook SDG entries. Verify during execution by running `validate_indicator_ids` over the complete codebook ID set and reporting any `not_in_api` results.
```

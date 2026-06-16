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

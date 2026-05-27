"""
tools/fetch_data.py
-------------------
Fetches data directly from the UIS public API.
Applies validity filtering before returning records to the AI.
The AI receives only clean, observed data — never raw API responses.
"""

import time
import requests
from tools.map_indicators import is_valid_record, get_validity_rules

_RULES    = get_validity_rules()
_BASE_URL = "https://api.uis.unesco.org/api/public"
_TIMEOUT  = 20
_RETRIES  = 2


def _get(url: str, params: dict | None = None) -> dict | None:
    """GET with retry logic."""
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


def fetch_indicator_data(
    indicator_ids: list[str],
    geo_unit: str,
    start_year: int = 2000,
    end_year: int = 2025,
    include_metadata: bool = False,
    observed_only: bool = True,
) -> dict:
    """
    Fetch data from UIS API for one or more indicator IDs and a geo unit.

    Parameters
    ----------
    indicator_ids   : list of exact UIS indicator IDs
    geo_unit        : ISO3 country code (e.g. 'UZB') or UIS region code
    start_year      : first year to retrieve
    end_year        : last year to retrieve
    include_metadata: request TYPE_OF_SOURCE metadata from API
    observed_only   : apply validity filter (exclude SUPP/NA/INCLUDED magnitudes)

    Returns
    -------
    dict keyed by indicator_id, each with:
      - records      : list of valid data points (dicts with year, value, magnitude, source)
      - total_raw    : count of records before filtering
      - total_valid  : count after filtering
      - years_with_data : sorted list of years
      - geo_unit     : echoed back
      - error        : present only if API call failed
    """
    results = {}

    for iid in indicator_ids:
        params = {
            "indicator": iid,
            "geoUnit":   geo_unit,
            "start":     start_year,
            "end":       end_year,
        }
        if include_metadata:
            params["includeMetadata"] = "true"

        url  = f"{_BASE_URL}/data/indicators"
        data = _get(url, params)

        if data is None or "_error" in (data or {}):
            results[iid] = {
                "error":    (data or {}).get("_error", "Unknown error"),
                "geo_unit": geo_unit,
            }
            continue

        raw_records = data.get("records", [])

        # Extract source from metadata if present
        def _source(rec: dict) -> str:
            for meta in rec.get("indicatorMetadata") or []:
                if meta.get("TYPE_OF_SOURCE"):
                    return meta["TYPE_OF_SOURCE"]
                if meta.get("source"):
                    return meta["source"]
            return "N/A"

        # Apply validity filter
        valid = []
        for rec in raw_records:
            mag   = rec.get("magnitude", "")
            value = rec.get("value")
            if (not observed_only) or is_valid_record(mag, value, iid):
                valid.append({
                    "year":      rec.get("year"),
                    "value":     value,
                    "magnitude": mag,
                    "source":    _source(rec),
                    "geo_unit":  rec.get("geoUnit", geo_unit),
                })

        valid.sort(key=lambda r: r["year"] or 0)
        years_with_data = sorted({r["year"] for r in valid if r["year"] is not None})

        results[iid] = {
            "geo_unit":       geo_unit,
            "total_raw":      len(raw_records),
            "total_valid":    len(valid),
            "years_with_data": years_with_data,
            "latest_year":    years_with_data[-1] if years_with_data else None,
            "records":        valid,
        }

    return results


def fetch_available_geo_units() -> dict:
    """Return list of all UIS geo units (countries and regions) from the API."""
    data = _get(f"{_BASE_URL}/definitions/geoUnits")
    if data is None or "_error" in (data or {}):
        return {"error": (data or {}).get("_error", "Failed to fetch geo units")}
    return {"geo_units": data}


def fetch_api_indicator_list() -> dict:
    """
    Return full list of indicators available in the UIS API.
    Used for validation — not for indicator ID resolution (use codebook for that).
    """
    data = _get(f"{_BASE_URL}/definitions/indicators")
    if data is None or "_error" in (data or {}):
        return {"error": (data or {}).get("_error", "Failed to fetch indicator list")}
    return {
        "count":      len(data) if isinstance(data, list) else 0,
        "indicators": data if isinstance(data, list) else [],
    }


def validate_indicator_ids_against_api(indicator_ids: list[str]) -> dict:
    """
    Check which of the given indicator IDs actually exist in the UIS API.
    Returns confirmed, missing, and unchecked lists.
    """
    api_data = fetch_api_indicator_list()
    if "error" in api_data:
        return {"error": api_data["error"], "checked": False}

    api_ids = {
        item.get("indicatorCode", "").upper()
        for item in api_data.get("indicators", [])
        if item.get("indicatorCode")
    }

    confirmed = [i for i in indicator_ids if i.upper() in api_ids]
    missing   = [i for i in indicator_ids if i.upper() not in api_ids]

    return {
        "confirmed":   confirmed,
        "not_in_api":  missing,
        "total_checked": len(indicator_ids),
        "api_indicator_count": len(api_ids),
    }

"""
scripts/generate_population_codebook.py
---------------------------------------
Regenerates codebooks/population_2025.json from the UIS demographic bulk
download file (final_output_YYYY_MM_DD) and the country codebook.

Run this whenever a new UIS data release is available:
    python scripts/generate_population_codebook.py \\
        --pop-file  "C:/path/to/001_Input/final_output_2026_01_22" \\
        --codebook  "C:/path/to/001_Input/DEM_Codebook_xlsx_-_CO_CODE.csv"

The script:
  1. Loads the UIS population file (CSV or XLSX auto-detected)
  2. Filters to EMC_ID=200101 (total, all ages, both sexes) and the target year
  3. Maps numeric CO_CODE → ISO3 via the UIS demographic codebook
  4. Keeps only the 214 UIS World countries
  5. Writes codebooks/population_2025.json

Requirements: pandas, openpyxl
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import requests

try:
    import pandas as pd
except ImportError:
    pd = None  # pandas is optional when using --from-datahub

REPO_ROOT    = Path(__file__).parent.parent
CODEBOOK_OUT = REPO_ROOT / "codebooks" / "population_2025.json"
COUNTRIES_CB = REPO_ROOT / "codebooks" / "countries.json"

EMC_ID       = "200101"   # Total population, all ages, both sexes
DEFAULT_YEAR = 2025


def load_pop_file(path: str) -> pd.DataFrame:
    p = Path(path)
    for ext in ["", ".csv", ".xlsx"]:
        candidate = Path(str(p) + ext) if not p.suffix else p
        if candidate.exists():
            print(f"Loading: {candidate}")
            if str(candidate).endswith(".xlsx"):
                return pd.read_excel(candidate)
            else:
                return pd.read_csv(candidate, low_memory=False)
    raise FileNotFoundError(f"Population file not found: {path}")


def load_codebook(path: str) -> dict:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    df["CO_CODE"] = df["CO_CODE"].astype(str).str.strip()
    df["ISO3"]    = df["ISO3"].astype(str).str.strip()
    return dict(zip(df["CO_CODE"], df["ISO3"]))


WDI_EXPORT_URL = "https://data.unesco.org/api/explore/v2.1/catalog/datasets/wdi001/exports/json"

# Manual name overrides: wdi001 country_title_en (normalized) → UIS iso3
# These are genuine spelling mismatches between wdi001 and countries.json UIS names.
_WDI_NAME_OVERRIDES: dict[str, str] = {
    # wdi001 uses "Macao, China"; UIS uses "China, Macao Special Administrative Region"
    "macao, china": "MAC",
    # wdi001 uses "State of Palestine"; UIS uses "Palestine"
    "state of palestine": "PSE",
    # wdi001 uses "Faroes"; UIS uses "Faeroe Islands"
    "faroes": "FRO",
    # wdi001 uses "Sint Maarten"; UIS uses "Sint Maarten (Dutch part)"
    "sint maarten": "SXM",
}


def _norm(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def build_from_datahub() -> dict:
    """
    Pull wdi001.population_total (World Bank, on the UNESCO DataHub), keep the latest
    year per country, and map to the 214 UIS ISO3 countries by normalized English name.
    Returns the population_2025.json payload dict. Prints any UIS country left unmatched.
    """
    with open(COUNTRIES_CB, encoding="utf-8") as f:
        uis = json.load(f)["countries"]
    name_to_iso3 = {_norm(c["name"]): c["iso3"] for c in uis}
    # Apply manual overrides (wdi001 spelling → iso3)
    name_to_iso3.update(_WDI_NAME_OVERRIDES)

    params = {
        "where": "population_total is not null",
        "select": "country,country_title_en,year,population_total",
    }
    print("Fetching wdi001 from UNESCO DataHub…", file=sys.stderr)
    resp = requests.get(WDI_EXPORT_URL, params=params, timeout=120)
    resp.raise_for_status()
    rows = resp.json()  # exports/json returns a JSON array of records
    print(f"Fetched {len(rows)} rows from wdi001.", file=sys.stderr)

    latest: dict[str, dict] = {}
    for r in rows:
        key = r.get("country")  # ISO2
        if key is None or r.get("population_total") is None:
            continue
        yr = int(r["year"])
        if key not in latest or yr > latest[key]["year"]:
            latest[key] = {"year": yr, "name": r.get("country_title_en", ""),
                           "pop": int(round(r["population_total"]))}

    pop_by_iso3: dict[str, int] = {}
    used_year = 0
    for rec in latest.values():
        iso3 = name_to_iso3.get(_norm(rec["name"]))
        if iso3:
            pop_by_iso3[iso3] = rec["pop"]
            used_year = max(used_year, rec["year"])

    missing = sorted(c["iso3"] for c in uis if c["iso3"] not in pop_by_iso3)
    if missing:
        print(f"WARNING: {len(missing)} UIS countries unmatched in wdi001: {missing}",
              file=sys.stderr)

    return {
        "_comment": "Total population per ISO3 for the 214 UIS World countries.",
        "_source": "UNESCO DataHub dataset wdi001 (World Bank WDI), field population_total",
        "_source_year": used_year,
        "_total_world_population": sum(pop_by_iso3.values()),
        "population_by_iso3": dict(sorted(pop_by_iso3.items())),
    }


def main():
    parser = argparse.ArgumentParser(description="Regenerate population_2025.json from UIS bulk data.")
    parser.add_argument("--pop-file",  help="Path to UIS population file (no extension needed)")
    parser.add_argument("--codebook",  help="Path to DEM_Codebook_xlsx_-_CO_CODE.csv")
    parser.add_argument("--year",      type=int, default=DEFAULT_YEAR, help=f"Population year (default: {DEFAULT_YEAR})")
    parser.add_argument("--out",       default=str(CODEBOOK_OUT), help="Output JSON path")
    parser.add_argument("--from-datahub", action="store_true",
                        help="Backfill populations from DataHub wdi001 (no local files needed).")
    args = parser.parse_args()

    if args.from_datahub:
        payload = build_from_datahub()
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_path} — {len(payload['population_by_iso3'])} countries, "
              f"year {payload['_source_year']}.")
        return

    # Pandas path requires --pop-file and --codebook
    if not args.pop_file or not args.codebook:
        parser.error("--pop-file and --codebook are required unless --from-datahub is set.")

    if pd is None:
        sys.exit("pandas is required for the UIS bulk-file path. Install with: uv sync --extra scripts")

    # Load UIS world countries
    with open(COUNTRIES_CB, encoding="utf-8") as f:
        ctry_data = json.load(f)
    world_iso3 = {c["iso3"] for c in ctry_data["countries"]}
    print(f"UIS World countries: {len(world_iso3)}")

    # Load and map population
    df_pop = load_pop_file(args.pop_file)
    cocode_map = load_codebook(args.codebook)

    df = df_pop[
        (df_pop["EMC_ID"].astype(str).str.strip() == EMC_ID) &
        (df_pop["EMCO_YEAR"].astype(str).str.strip() == str(args.year))
    ].copy()
    print(f"Rows matching EMC_ID={EMC_ID}, YEAR={args.year}: {len(df)}")

    if len(df) == 0:
        print(f"ERROR: No rows found. Check EMC_ID and year.", file=sys.stderr)
        sys.exit(1)

    df["CO_CODE_STR"] = df["CO_CODE"].astype(str).str.strip()
    df["ISO3"]        = df["CO_CODE_STR"].map(cocode_map)
    df                = df[df["ISO3"].notna() & df["ISO3"].isin(world_iso3)]
    df                = df[df["EM_FIG"].notna()]
    # EM_FIG is in thousands — convert to whole persons
    df["EM_FIG"]      = (df["EM_FIG"] * 1000).round()
    # Prefer MQ_ID=NaN (observed) over MQ_ID=2 (estimated); keep one row per country
    df                = df.sort_values("MQ_ID", na_position="first")
    df                = df.rename(columns={"EM_FIG": "POPULATION"})
    df                = df[["ISO3", "POPULATION"]].drop_duplicates("ISO3")

    pop_map  = dict(zip(df["ISO3"], df["POPULATION"].astype(int)))
    missing  = sorted(world_iso3 - set(pop_map))
    matched  = len(pop_map)
    total    = sum(pop_map.values())

    print(f"Matched: {matched}/214 UIS countries")
    if missing:
        print(f"Missing ISO3s (will be absent from output): {missing}")

    output = {
        "_comment":                 "Total population estimates for 214 UIS World countries.",
        "_source":                  f"UIS demographic bulk download file, regenerated {date.today().isoformat()}",
        "_source_emc_id":           EMC_ID,
        "_source_emc_id_note":      "Total population, all ages, both sexes",
        "_reference_year":          args.year,
        "_total_world_population":  total,
        "_matched_countries":       matched,
        "_missing_iso3":            missing,
        "_update_note":             "Regenerated from UIS bulk download. Run this script after each data release.",
        "population_by_iso3":       dict(sorted(pop_map.items())),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")
    print(f"Total population: {total:,.0f}")


if __name__ == "__main__":
    main()

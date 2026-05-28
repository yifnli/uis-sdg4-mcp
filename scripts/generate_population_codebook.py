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

import pandas as pd

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


def main():
    parser = argparse.ArgumentParser(description="Regenerate population_2025.json from UIS bulk data.")
    parser.add_argument("--pop-file",  required=True, help="Path to UIS population file (no extension needed)")
    parser.add_argument("--codebook",  required=True, help="Path to DEM_Codebook_xlsx_-_CO_CODE.csv")
    parser.add_argument("--year",      type=int, default=DEFAULT_YEAR, help=f"Population year (default: {DEFAULT_YEAR})")
    parser.add_argument("--out",       default=str(CODEBOOK_OUT), help="Output JSON path")
    args = parser.parse_args()

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

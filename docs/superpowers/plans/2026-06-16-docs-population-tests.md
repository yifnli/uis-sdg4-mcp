# Documentation + Population Backfill + Test Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) Produce a slide-by-slide errata that aligns the `UIS_MCP_Webinar.pdf` deck with the migrated code; (B) fill the 40 missing country populations from the DataHub `wdi001` (World Bank) dataset so `resolve_country` returns a non-null `population_2025` for all 214 UIS countries; (C) raise test coverage with targeted unit tests for currently-untested functions and add a coverage tool.

**Architecture:** Three independent workstreams. Documentation is additive (a new markdown errata file — we cannot edit the binary PDF). The population fix extends the existing generator to pull `population_total` from DataHub `wdi001` (ISO2-keyed, latest year 2024), joins to the 214 UIS ISO3 countries, and regenerates `codebooks/population_2025.json`. Test coverage adds offline unit tests against existing pure functions and wires `pytest-cov`.

**Tech Stack:** Python 3.12, uv, requests (DataHub ODS export API), pytest, pytest-cov.

**Branch:** Work on `develop` (already checked out). Do not switch branches.

---

## Verified facts (live API + repo probes, 2026-06-16)

- The deck (`docs/UIS_MCP_Webinar.pdf`, 13 slides) documents the **pre-migration** version: "UIS API"/`api.uis.unesco.org`, Python 3.10+, `pip install mcp[cli] requests pandas`, conda, `.vscode/mcp.json`, repo `main` @ 6b7ef12 with `requirements.txt`. The migrated code (DataHub `uis001`, FastMCP, uv, Python ≥3.12, `.mcp.json`) lives on `develop`.
- **Population gap is data, not code.** `tools/resolve_country.py::_build_result` correctly does `_POP_BY_ISO3.get(iso3)`. `codebooks/population_2025.json` has **174 of 214** countries; **40 missing** (all high-income + a few territories): AUS AUT BEL BGR BRA CHE COL CYP CZE DEU DNK ESP EST FIN FRA FRO GBR GRC GRL HRV HUN IRL ITA KOR LTU LUX LVA MEX MLT NLD NOR NZL POL PRT ROU SVK SVN SWE VAT XDN. No null values — keys simply absent.
- `uis003` does **not** contain absolute total population (30 indicators, all GDP/GNI/PPP/rates). Dead end.
- `wdi001` (World Bank WDI on DataHub) **does** have it. Wide-format table; relevant fields: `country` (ISO2, e.g. `"KR"`), `country_title_en` (UIS-style long name, e.g. `"Republic of Korea"`), `year` (string), `population_total` (float). Latest year with data = **2024**. Verified values: KR 51,751,065 · DE 83,510,950 · FR 68,516,699 · GB 69,226,000 · BR 211,998,573 · AU 27,204,809 · MX 130,861,007.
- DataHub ODS **exports** endpoint avoids the 100-row pagination cap: `GET {base}/catalog/datasets/wdi001/exports/json?where=...&select=...`.
- Test inventory: `tests/test_tools.py` (69 test defs), `tests/test_datahub.py` (9). `pytest-cov` is NOT installed.
- **Untested public functions:** `resolve_indicator_id` (edge cases), `get_population`, `compute_population_coverage` (edges), `list_countries_by_region` (happy path), `format_coverage_summary_table`, `get_validity_rules`, `validate_indicator_ids_against_api` (mocked unit), `compute_sdg_coverage`, `fetch_indicator_data(observed_only=False)`, `_paginate` multi-page + truncation sentinel.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `docs/webinar-deck-errata.md` | Slide-by-slide corrections aligning the deck with migrated code | Create |
| `scripts/generate_population_codebook.py` | Add a `--from-datahub` mode that pulls `wdi001.population_total` via the ODS export API and joins ISO2→ISO3 | Modify |
| `codebooks/population_2025.json` | Regenerated to cover all 214 UIS countries (single provenance: wdi001 / World Bank, year 2024) | Regenerate |
| `tests/test_population_backfill.py` | Regression tests: all 214 have population, Korea non-null, coverage denominator | Create |
| `tests/test_coverage_extra.py` | New unit tests for untested pure functions | Create |
| `pyproject.toml` | Add `pytest-cov` to the `dev` extra | Modify |
| `README.md` / `CLAUDE.md` | Note population provenance now wdi001; population regen command | Modify |

**Decision locked in:** regenerate **all 214** populations from `wdi001` (single provenance, year 2024) rather than patching only the 40. Rationale: one source + one year is consistent for the population-coverage denominator and simpler to reason about. The file keeps its name `population_2025.json` (renaming ripples into `resolve_country.py`/`coverage.py`); its internal metadata records the true source and year. Alternative (patch-only-40, mixed provenance) is explicitly rejected.

---

## Task 1: Webinar deck errata document

**Files:**
- Create: `docs/webinar-deck-errata.md`

No code/tests — a documentation deliverable. The binary PDF cannot be edited here; this errata gives the presenter exact replacement text per slide.

- [ ] **Step 1: Create `docs/webinar-deck-errata.md` with this content:**

```markdown
# Webinar Deck Errata — `UIS_MCP_Webinar.pdf`

The deck ("Talking to Our Data", 13 slides) was authored against the **pre-migration**
version. The code on `develop` now uses the UNESCO DataHub, FastMCP, uv, and Python ≥3.12.
Apply these corrections before presenting from the migrated code. Capability/scope is
unchanged — all six value-added features and all four live-demo queries work (verified live).

## Global find/replace
- "UIS API" / "api.uis.unesco.org" → "UNESCO DataHub" / "data.unesco.org" (dataset `uis001`)
- "Live UIS API call" → "Live DataHub call"
- "Every value comes from the UIS API" → "Every value comes from the UNESCO DataHub"

## Slide-by-slide

**Slide 4 — How it works (step 3):** "get_indicator_data — Live UIS API call" →
"get_indicator_data — live DataHub call (dataset uis001), validity filter applied".

**Slide 6 — Value added:** "Coverage analysis … 214 UIS countries" is still correct.
World coverage is now computed via a single DataHub `group_by(country_id)` aggregation
(faster), not per-country fetches — no slide text change needed, but mention if asked.

**Slide 7 — Live Demo footnote:** "Queries 3–4 call the UIS API" → "Queries 3–4 call the
UNESCO DataHub". All four demo queries verified working on the migrated server:
1. List all global SDG 4 indicators → 14 global indicators.
2. Resolve "South Korea" → KOR.
3. Qatar basic literacy briefing → 4 literacy indicators, data through 2024.
4. Uzbekistan SDG 4.1.2 after 2020 → completion rates present (2022).

**Slide 8 — Traditional vs MCP table:** "Get data → Live API call, automatic" still holds
(now DataHub). No change required.

**Slide 9 — Limitations:** "API network dependency: api.uis.unesco.org" →
"data.unesco.org". "Codebook needs manual updates" still true.

**Slide 12 — Getting started:** replace the prerequisites/steps:
- "Python 3.10+ (Anaconda works)" → "Python 3.12+ and uv (https://docs.astral.sh/uv/)"
- "conda activate base" → (remove)
- 'pip install "mcp[cli]" requests pandas' → "uv sync --extra dev"
- "python server.py --test (10 checks)" → "uv run python server.py --test (10 checks)"
- "Configure .vscode/mcp.json" → "Configure .mcp.json (Claude Code). For VS Code/Copilot
  the file is still .vscode/mcp.json — use the `uv` command form."
- MCP server command block:
  `{"command":"uv","args":["--directory","/path/to/uis-sdg4-mcp","run","python","server.py"]}`

**Slide 13 — Q&A / repo:** the repo screenshot shows `main` with `requirements.txt` (old).
Merge `develop` → `main` and push before the webinar so the public repo matches the talk,
otherwise the audience sees the pre-migration code.

## Data note (population)
`resolve_country` returns `population_2025`. After the population backfill task, all 214
UIS countries have a value sourced from the DataHub `wdi001` (World Bank) dataset,
`population_total`, latest year 2024. Before the backfill, 40 high-income countries
(Korea, Germany, France, UK, Brazil, …) returned `null` — avoid resolving those live until
the backfill is merged.
```

- [ ] **Step 2: Verify the file renders and links are correct**

Run: `uv run python -c "import pathlib; t=pathlib.Path('docs/webinar-deck-errata.md').read_text(); assert 'data.unesco.org' in t and 'uv sync' in t; print('ok', len(t), 'chars')"`
Expected: `ok <n> chars`.

- [ ] **Step 3: Commit**

```bash
git add docs/webinar-deck-errata.md
git commit -m "docs: add webinar deck errata aligning slides with DataHub/FastMCP/uv migration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backfill populations from DataHub `wdi001`

**Files:**
- Modify: `scripts/generate_population_codebook.py`
- Regenerate: `codebooks/population_2025.json`
- Test: `tests/test_population_backfill.py`

The generator gains a `--from-datahub` mode that needs no local files: it pulls
`wdi001.population_total` for the latest available year per country via the ODS export API,
maps each `wdi001` country to a UIS ISO3 (join on normalized `country_title_en`, since
`wdi001` uses UIS-style long names), and writes all 214. It prints any UIS country left
without a population so gaps are loud, not silent.

- [ ] **Step 1: Write the failing regression test**

Create `tests/test_population_backfill.py`:

```python
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


def test_all_214_uis_countries_have_population():
    countries = json.load(open(_ROOT / "codebooks" / "countries.json", encoding="utf-8"))["countries"]
    pop = _load()["population_by_iso3"]
    missing = [c["iso3"] for c in countries if c["iso3"] not in pop or pop[c["iso3"]] is None]
    assert missing == [], f"countries without population: {missing}"


def test_korea_population_present_and_reasonable():
    pop = _load()["population_by_iso3"]
    assert "KOR" in pop
    assert 40_000_000 < pop["KOR"] < 60_000_000  # ~51.7M


def test_total_world_population_recomputed():
    d = _load()
    pop = d["population_by_iso3"]
    assert d["_total_world_population"] == sum(v for v in pop.values() if v)
    assert d["_total_world_population"] > 7_000_000_000


def test_resolve_country_korea_non_null():
    from tools.resolve_country import resolve_country
    assert resolve_country("South Korea")["population_2025"] is not None
```

- [ ] **Step 2: Run, confirm it FAILS**

Run: `uv run pytest tests/test_population_backfill.py -v`
Expected: `test_all_214_uis_countries_have_population` and `test_resolve_country_korea_non_null` FAIL (40 missing, KOR null). The "reasonable" and "total" tests may also fail.

- [ ] **Step 3: Add the `--from-datahub` mode to `scripts/generate_population_codebook.py`**

Add these imports near the top (the file already imports `json`, `sys`, `argparse`, `date`, `Path`):

```python
import requests
```

Add this function (a self-contained DataHub backfill path) and wire it into `argparse`/`main`:

```python
WDI_EXPORT_URL = "https://data.unesco.org/api/explore/v2.1/catalog/datasets/wdi001/exports/json"


def _norm(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def build_from_datahub() -> dict:
    """
    Pull wdi001.population_total (World Bank, on the UNESCO DataHub), keep the latest
    year per country, and map to the 214 UIS ISO3 countries by normalized English name.
    Returns the population_2025.json payload dict. Prints any UIS country left unmatched.
    """
    # 1. Load the 214 UIS countries (ISO3 + UIS English name).
    with open(COUNTRIES_CB, encoding="utf-8") as f:
        uis = json.load(f)["countries"]
    name_to_iso3 = {_norm(c["name"]): c["iso3"] for c in uis}

    # 2. Pull all population_total rows from wdi001 via the export endpoint (no page cap).
    params = {
        "where": "population_total is not null",
        "select": "country,country_title_en,year,population_total",
    }
    resp = requests.get(WDI_EXPORT_URL, params=params, timeout=120)
    resp.raise_for_status()
    rows = resp.json()  # exports/json returns a JSON array of records

    # 3. Keep the latest year per wdi001 country.
    latest: dict[str, dict] = {}
    for r in rows:
        key = r.get("country")  # ISO2
        if key is None or r.get("population_total") is None:
            continue
        yr = int(r["year"])
        if key not in latest or yr > latest[key]["year"]:
            latest[key] = {"year": yr, "name": r.get("country_title_en", ""),
                           "pop": int(round(r["population_total"]))}

    # 4. Join wdi001 → UIS ISO3 by normalized name.
    pop_by_iso3: dict[str, int] = {}
    used_year = 0
    for rec in latest.values():
        iso3 = name_to_iso3.get(_norm(rec["name"]))
        if iso3:
            pop_by_iso3[iso3] = rec["pop"]
            used_year = max(used_year, rec["year"])

    # 5. Report any UIS country still without a population (loud, not silent).
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
```

In `main()`/argparse, add a `--from-datahub` flag that, when set, writes `build_from_datahub()` to `CODEBOOK_OUT` and skips the pandas/local-file path:

```python
    parser.add_argument("--from-datahub", action="store_true",
                        help="Backfill populations from DataHub wdi001 (no local files needed).")
    # ... inside main(), before the existing pandas path:
    if args.from_datahub:
        payload = build_from_datahub()
        with open(CODEBOOK_OUT, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Wrote {CODEBOOK_OUT} — {len(payload['population_by_iso3'])} countries, "
              f"year {payload['_source_year']}.")
        return
```

Keep the existing pandas-based path intact for the legacy UIS-file workflow.

- [ ] **Step 4: Regenerate the codebook**

Run: `uv run --extra scripts python scripts/generate_population_codebook.py --from-datahub`
Expected: prints "Wrote …/population_2025.json — N countries, year 2024." with N ≥ 200. If the WARNING lists any of the 214 as unmatched, inspect those names: a handful of UIS names may differ from `wdi001` `country_title_en` (e.g. "Holy See", "Sudan (pre-secession)" XDN, "Faeroe Islands", "Greenland"). For each genuinely-unmatched country, add a name alias in the join (extend `name_to_iso3` with the `wdi001` spelling) OR accept that micro-states/territories without World Bank population remain null — but the count of remaining nulls MUST be reported and reduced to only those with no World Bank data. Re-run until only true no-data territories remain.

- [ ] **Step 5: Run the regression tests**

Run: `uv run pytest tests/test_population_backfill.py -v`
Expected: PASS. If `test_all_214_uis_countries_have_population` still lists a few territories (e.g. VAT Holy See, XDN Sudan-pre-secession) that genuinely have no World Bank population, relax that specific test to allow a documented allowlist of at-most-those territories, and record them in the test as a named constant with a comment. Do NOT relax it to hide high-income countries — Korea/Germany/France/etc. MUST be present.

- [ ] **Step 6: Confirm no regression in the broader suite + self-test**

Run: `uv run pytest tests/ -q -m "not api" && uv run python server.py --test`
Expected: all offline tests pass; self-test prints "(10 checks)". Note: `compute_population_coverage` percentages shift because the denominator now covers 214 countries — the existing assertion `pct_population > 35` for CHN+IND+USA still holds (verify it does; if the denominator change pushes it below, update that assertion to the new true value and note it).

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_population_codebook.py codebooks/population_2025.json tests/test_population_backfill.py
git commit -m "feat: backfill all 214 country populations from DataHub wdi001 (World Bank)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Expand test coverage + add coverage tool

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_coverage_extra.py`

- [ ] **Step 1: Add `pytest-cov` to the dev extra in `pyproject.toml`**

In `[project.optional-dependencies]`, change the `dev` list to:

```toml
dev = [
  "pytest>=7.0",
  "pytest-asyncio>=0.23",
  "pytest-cov>=4.1",
]
```

Run: `uv sync --extra dev` → resolves pytest-cov.

- [ ] **Step 2: Measure the baseline coverage**

Run: `uv run pytest -q -m "not api" --cov=tools --cov-report=term-missing`
Expected: a coverage table per `tools/*.py`. Note the lines flagged missing — they should correspond to the untested functions listed below. Record the baseline total %.

- [ ] **Step 3: Write `tests/test_coverage_extra.py` (offline unit tests for untested pure functions):**

```python
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
    out = compute_population_coverage(["CHN", "ZZZ"])
    assert out["n_countries_covered"] == 2  # counts inputs; ZZZ contributes 0 population


# ── briefing ──────────────────────────────────────────────────────────────────
def test_format_coverage_summary_table_shape():
    from tools.briefing import format_coverage_summary_table
    coverage_result = {
        "threshold_year": 2020,
        "geo_unit": "all",
        "indicators": {
            "LR.AG15T99": {
                "indicator_id": "LR.AG15T99",
                "coverage_any_data": {"n_countries": 100, "pct_countries": 47.0, "pct_population": 80.0},
                "coverage_post_threshold": {"n_countries": 40, "pct_countries": 18.7, "pct_population": 50.0},
            }
        },
    }
    out = format_coverage_summary_table(coverage_result)
    assert out  # returns a structured table (dict or list), non-empty


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
```

- [ ] **Step 4: Run the new tests**

Run: `uv run pytest tests/test_coverage_extra.py -v`
Expected: all PASS. If `format_coverage_summary_table` or `compute_population_coverage` return a shape that differs from the assertions (e.g. the "counts inputs" semantics differ), READ the actual function first and adjust the assertion to the real, correct behavior — do not change the function. Note any such adjustment.

- [ ] **Step 5: Re-measure coverage and confirm it rose**

Run: `uv run pytest -q -m "not api" --cov=tools --cov-report=term-missing`
Expected: total coverage % is higher than the Step 2 baseline; the previously-untested functions now show reduced missing-line counts. Record the new total %.

- [ ] **Step 6: Run the full offline suite once more**

Run: `uv run pytest tests/ -q -m "not api"`
Expected: all PASS (existing + new).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tests/test_coverage_extra.py
git commit -m "test: add unit tests for untested tool functions; wire pytest-cov

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Update README + CLAUDE.md for population provenance

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `README.md`**

- In the "Codebook structure" section, change the `population_2025.json` description to: "Total population per ISO3 for all 214 UIS World countries, sourced from the DataHub `wdi001` (World Bank WDI) `population_total`, latest year. Regenerate with `uv run --extra scripts python scripts/generate_population_codebook.py --from-datahub`."

- [ ] **Step 2: Update `CLAUDE.md`**

- In the codebooks bullet list, change the `population_2025.json` note to: "`population_2025.json` — total population per ISO3 for all 214 UIS countries, from DataHub `wdi001` (World Bank) `population_total`. Regenerate via `--from-datahub`."
- In the Conventions section, replace the population line with: "Population values now come from DataHub `wdi001` (World Bank `population_total`, latest year) covering all 214 countries — regenerate with `generate_population_codebook.py --from-datahub`. The legacy UIS-demographic path (EM_FIG ×1000) remains in the script for the old workflow."

- [ ] **Step 3: Verify no stale population claims remain**

Run: `uv run grep -rn "EM_FIG\|UN WPP\|174" README.md CLAUDE.md`
Expected: any remaining mention is historical/contextual only; the primary description points to `wdi001`. Adjust if a line still asserts the old source as current.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: record population provenance as DataHub wdi001 (World Bank)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Live population check through the MCP path**

Run:
```bash
uv run python -c "
from tools.resolve_country import resolve_country
for q in ['South Korea','Germany','France','Qatar','Tanzania']:
    r = resolve_country(q)
    print(q, '->', r['iso3'], r['population_2025'])
"
```
Expected: every line shows a non-null population (Korea ≈ 51.7M, Germany ≈ 83.5M, etc.).

- [ ] **Step 2: Full offline suite + self-test + coverage**

Run: `uv run pytest tests/ -q -m "not api" --cov=tools && uv run python server.py --test`
Expected: all offline tests pass; self-test "(10 checks)"; coverage table printed.

- [ ] **Step 3: Live suite still green**

Run: `uv run pytest tests/ -q -m api`
Expected: all PASS.

- [ ] **Step 4: Confirm git state**

Run: `git status && git log --oneline -8`
Expected: clean tree; commits from Tasks 1–4 present.

---

## Self-Review

**Spec coverage:**
- "update documentation with that" → Task 1 (deck errata) + Task 4 (README/CLAUDE population provenance). ✓
- "fix the population-null bug" → Task 2 (wdi001 backfill, all 214). ✓
- "update tests coverage" → Task 3 (new unit tests + pytest-cov) + Task 2 regression tests. ✓
- "stick to DataHub api" (user directive) → Task 2 sources from DataHub `wdi001` via the ODS export endpoint, not World Bank's own API. ✓

**Placeholder scan:** No "TBD"/"add error handling". Task 2 Step 4/5 and Task 3 Step 4 contain conditional handling (unmatched territories, shape mismatches) with explicit, bounded criteria — not placeholders.

**Type consistency:**
- `build_from_datahub()` returns the same `population_2025.json` schema the loaders expect: keys `population_by_iso3` (ISO3→int) and `_total_world_population` (int), which `tools/resolve_country.py` reads as `_POP_BY_ISO3` and `_TOTAL_POP`. ✓
- New tests reference real function signatures: `get_population(iso3)`, `list_countries_by_region(region)`, `compute_population_coverage(list)`, `fetch_data._paginate(where, select=...)`, `validate_indicator_ids_against_api(list)`. ✓

**Risk flagged:** a few UIS "countries" are territories World Bank may not report (VAT Holy See, XDN Sudan-pre-secession, FRO Faeroe, GRL Greenland). Task 2 makes residual nulls loud and bounds the regression test to a documented territory allowlist — high-income countries must never be in that allowlist.
```

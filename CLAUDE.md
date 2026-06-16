# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP stdio server (FastMCP) exposing UNESCO DataHub (data.unesco.org, Opendatasoft Explore API v2.1, dataset `uis001`) SDG 4 education data to AI clients. The governing principle: **the server owns the
numbers, the AI writes the narrative.** The server resolves all indicator IDs from a validated
codebook (never inferred), queries the DataHub, applies validity filtering, and returns
only clean observed data. The AI must never produce or estimate data values.

## Commands

```bash
uv sync --extra dev                      # Install deps, create .venv, write uv.lock
uv run python server.py --test           # Offline self-test (10 checks, no network)
uv run python server.py                  # Run as stdio MCP server
uv run pytest tests/ -v -m "not api"     # Offline suite (codebook, mapping, ODS client mocked)
uv run pytest tests/ -v -m api           # Live DataHub tests — require data.unesco.org
uv run --extra scripts python scripts/generate_population_codebook.py   # Regen population (needs pandas)
```

Managed by `uv` — there is no `requirements.txt` or hand-made venv. `uv sync --extra dev` creates `.venv` and `uv.lock`. Python is pinned to 3.12 via `.python-version` (`requires-python = ">=3.12"`). Always invoke via `uv run …`.

## Architecture

`server.py` is a FastMCP server — each tool is an `@mcp.tool`-decorated function delegating to a pure function in `tools/`; type hints + docstrings generate the schema. To add a tool, add one decorated function (no separate schema list to keep in sync). Entry point `main()` calls `mcp.run()`; `--test` runs the offline self-test.

`tools/` modules (each loads its codebook once at import time, pure functions, no MCP coupling):
- `map_indicators.py` — resolves SDG number → indicator IDs from `indicator_framework.json`.
  Owns `is_valid_record()`, the validity filter used everywhere. Builds reverse `_ID_TO_SDG` lookup.
- `fetch_data.py` — Opendatasoft client for dataset `uis001`. `_build_where()` builds ODSQL; `_paginate()` pages at limit 100; `fetch_indicator_data()` pulls all requested indicator IDs in one IN-list query and buckets them by indicator in Python; `fetch_distinct_countries()` powers world coverage via `group_by(country_id)`.
- `coverage.py` — post-threshold availability stats; depends on `fetch_data` + `resolve_country`.
- `resolve_country.py` — country name/alias/ISO3 → UIS entry; population-weighted coverage over
  214 UIS World countries.
- `briefing.py` — formats fetched results into narrative-ready structure (gaps, YoY changes) +
  the UIS writing style guide. No network.

`codebooks/` is the source of truth — code is grounded in these JSON files, edit them rather than
hardcoding values:
- `indicator_framework.json` — 45 SDG 4 indicators (14 global + 31 thematic): SDG number → IG group → validated IDs. Also embeds `validity_rules`.
- `validity_rules.json` — excluded magnitudes & ID prefixes, threshold year, writing style. The `api` block holds the ODS `base_url`, `dataset_id: uis001`, and `max_page_limit: 100`. Mirrors the rules inside `indicator_framework.json`.
- `countries.json` — 214 UIS World countries + alias map. `population_2025.json` — UN WPP 2024 totals.

## Validity filtering (the core invariant)

A record is observed/reported data only if it passes `is_valid_record(magnitude, value, indicator_id)`:
- magnitude NOT in `excluded_magnitudes` (`SUPP`, `NA`, `INCLUDED`)
- indicator_id does NOT start with an `excluded_id_prefixes` entry (`CR.MOD.`, `LR.GALP.` — these are modelled estimates)
- value is not null

`get_indicator_data` applies this by default (`observed_only=True`). Modelled estimates are
excluded so they're never presented as reported data. Don't bypass this filter when surfacing values to the AI.

**DataHub gotchas:**
- `year` is returned as a string (`"2002"`) by the ODS API — the client casts to int before returning.
- `magnitude` in `uis001` is only ever `null` or `"NIL"` — the magnitude-exclusion rules still apply for forward compatibility.
- `uis001` contains **both** observed and modelled estimates (`CR.MOD.*` present) — the `excluded_id_prefixes` filter (`CR.MOD.`, `LR.GALP.`) is load-bearing, not redundant. Do not remove it.

## Conventions

- Codebook counts are asserted in tests (14 global, 31 thematic, 214 countries). If you change a
  codebook, update the corresponding assertions in `server.py::_run_self_test` and `tests/test_tools.py`.
- Population values: the UIS bulk download reports `EM_FIG` in thousands — the generator scales ×1000 (see commit history). Keep population in absolute persons.
- Tool errors are returned as data (`{"error": ...}`), not raised — per-indicator isolation depends on this.

## Reference

`docs/datahub-vs-uis-api.md` — comparison of the legacy UIS API and the current UNESCO DataHub (ODS) approach: endpoint structure, query model, pagination, and migration notes.

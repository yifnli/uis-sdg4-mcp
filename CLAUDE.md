# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP (Model Context Protocol) stdio server exposing UNESCO Institute for Statistics (UIS)
SDG 4 education indicator data to AI clients. The governing principle: **the server owns the
numbers, the AI writes the narrative.** The server resolves all indicator IDs from a validated
codebook (never inferred), calls the UIS public API, applies validity filtering, and returns
only clean observed data. The AI must never produce or estimate data values.

## Commands

```bash
python server.py --test                  # Offline self-test (10 checks, no API, no MCP) — run this first
python server.py                          # Run as stdio MCP server
pytest tests/ -v -m "not api"             # Offline test suite (codebook, mapping, formatting)
pytest tests/ -v -m api                   # Online tests — require live api.uis.unesco.org
pytest tests/test_tools.py::TestResolveSDGIndicators::test_known_global_indicator -v   # Single test
python scripts/generate_population_codebook.py   # Regenerate population_2025.json from UIS bulk download
```

`pip install -r requirements.txt` to set up. Python 3.10+.

**Setup reality:** `mcp` is not installed globally and the `python` alias points at a missing
3.10 — use a venv. From scratch: `python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt`,
then run via `./venv/bin/python server.py --test`. The bare `python ...` commands below assume the venv is active.

## Architecture

`server.py` is the only MCP entry point. It defines every Tool schema in `list_tools()` and
dispatches by name in `call_tool()` — a long if/elif chain that delegates to pure functions in
`tools/`. To add a tool: add the `Tool(...)` schema AND a matching `elif name == ...` branch,
then implement the logic in a `tools/` module. The dispatch and the schema list must stay in sync.

`tools/` modules (each loads its codebook once at import time, pure functions, no MCP coupling):
- `map_indicators.py` — resolves SDG number → indicator IDs from `indicator_framework.json`.
  Owns `is_valid_record()`, the validity filter used everywhere. Builds reverse `_ID_TO_SDG` lookup.
- `fetch_data.py` — only module that touches the network. `_get()` wraps `requests` with retry +
  timeout. `fetch_indicator_data()` fetches **per indicator ID in a loop** so one failure isolates
  to that indicator (`{"error": ...}`) rather than failing the batch. Applies `is_valid_record()`
  before returning.
- `coverage.py` — post-threshold availability stats; depends on `fetch_data` + `resolve_country`.
- `resolve_country.py` — country name/alias/ISO3 → UIS entry; population-weighted coverage over
  214 UIS World countries.
- `briefing.py` — formats fetched results into narrative-ready structure (gaps, YoY changes) +
  the UIS writing style guide. No network.

`codebooks/` is the source of truth — code is grounded in these JSON files, edit them rather than
hardcoding values:
- `indicator_framework.json` — 45 SDG 4 indicators (14 global + 31 thematic): SDG number → IG group → validated IDs. Also embeds `validity_rules`.
- `validity_rules.json` — API base URL, timeout/retries, excluded magnitudes & ID prefixes, threshold year, writing style. Mirrors the rules inside `indicator_framework.json`.
- `countries.json` — 214 UIS World countries + alias map. `population_2025.json` — UN WPP 2024 totals.

## Validity filtering (the core invariant)

A record is observed/reported data only if it passes `is_valid_record(magnitude, value, indicator_id)`:
- magnitude NOT in `excluded_magnitudes` (`SUPP`, `NA`, `INCLUDED`)
- indicator_id does NOT start with an `excluded_id_prefixes` entry (`CR.MOD.`, `LR.GALP.` — these are modelled estimates)
- value is not null

`get_indicator_data` applies this by default (`observed_only=True`). Modelled estimates are
excluded so they're never presented as reported data. Don't bypass this filter when surfacing values to the AI.

## Conventions

- Codebook counts are asserted in tests (14 global, 31 thematic, 214 countries). If you change a
  codebook, update the corresponding assertions in `server.py::_run_self_test` and `tests/test_tools.py`.
- Population values: the UIS bulk download reports `EM_FIG` in thousands — the generator scales ×1000 (see commit history). Keep population in absolute persons.
- Tool errors are returned as data (`{"error": ...}`), not raised — per-indicator isolation depends on this.

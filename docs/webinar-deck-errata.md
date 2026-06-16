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

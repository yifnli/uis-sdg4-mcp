# Legacy UIS API vs UNESCO DataHub — API Comparison

> Context for the migration that repoints this MCP server from `api.uis.unesco.org`
> to the UNESCO DataHub (`data.unesco.org`). All facts verified against the live
> APIs on 2026-06-16. See the migration plan in
> `docs/superpowers/plans/2026-06-16-datahub-fastmcp-migration.md`.

## TL;DR

The two are **different platforms with different data models**, not two URLs for the
same service. Legacy UIS API is **indicator-centric** (one call per indicator, custom
REST). DataHub is **dataset-centric** (one tabular dataset `uis001`, queried with
SQL-like ODSQL). The migration trades a custom per-indicator API for a generic
Opendatasoft catalog query layer: fewer HTTP calls, richer queries, but new
pagination limits and a couple of query-syntax traps.

## Side-by-side

| Dimension | Legacy UIS API | UNESCO DataHub |
|---|---|---|
| Host | `api.uis.unesco.org/api/public` | `data.unesco.org/api/explore/v2.1` |
| Engine | UIS-custom REST | Opendatasoft / Huwise (generic open-data catalog) |
| Data model | Indicator-centric | Dataset-centric: single table `uis001` (~1.46M rows) |
| Unit of query | One indicator per call | Rows of a dataset, any filter |
| Query language | Fixed query params | **ODSQL** — `where` / `select` / `group_by` / `order_by` |
| SDG4 scope | The whole API is SDG4 | One dataset (`uis001`) among many UNESCO datasets |
| Auth | Public, no key | Public, no key |
| Aggregation | None — fetch then count client-side | Server-side `group_by` + `count(*)` |
| Pagination | Full series returned per call | `limit` ≤ 100/page, `offset + limit` ≤ 10000 |

## Endpoint mapping

| Purpose | Legacy UIS API | DataHub equivalent |
|---|---|---|
| Fetch data | `GET /data/indicators?indicator=X&geoUnit=Y&start=&end=` | `GET /catalog/datasets/uis001/records?where=indicator_id in (...) and country_id="Y" and year>=.. and year<=..` |
| Indicator catalogue | `GET /definitions/indicators` | none — use `?group_by=indicator_id` or `/facets?facet=indicator_id` over `uis001` |
| Geo units | `GET /definitions/geoUnits` | none — use `?group_by=country_id` over `uis001` |
| Validate IDs exist | filter `/definitions/indicators` | `?where=indicator_id in (...)&group_by=indicator_id` |
| Coverage (which countries have data) | fetch all 214 countries, count client-side | `?where=indicator_id="X" and year>T&group_by=country_id` (one aggregation) |

## Request shape

**Legacy — one indicator per call** (`fetch_data.py` looped over IDs, isolating
errors per indicator):

```
GET https://api.uis.unesco.org/api/public/data/indicators
    ?indicator=LR.AG15T99&geoUnit=UZB&start=2000&end=2025
```

Four indicators → four HTTP calls.

**DataHub — many indicators per call** (IN-list):

```
GET https://data.unesco.org/api/explore/v2.1/catalog/datasets/uis001/records
    ?where=country_id="UZB" and indicator_id in ("LR.AG15T99","LR.AG15T24")
          and year>=2000 and year<=2025
    &select=indicator_id,country_id,year,value,magnitude,indicator_label_en
    &limit=100
```

Four indicators → **one** HTTP call; bucket rows by `indicator_id` in Python.

## Response shape & fields

**DataHub records response:**

```json
{ "total_count": 1140, "results": [ { "indicator_id": "LR.AG15T99",
  "country_id": "UZB", "year": "2002", "value": 99.96,
  "magnitude": null, "qualifier": null,
  "indicator_label_en": "Literacy rate ...", "country_name_en": "Uzbekistan",
  "regional_group": "..." } ] }
```

Field mapping vs legacy:

| Concept | Legacy field | DataHub field | Note |
|---|---|---|---|
| Country | `geoUnit` | `country_id` | both ISO3 — **no mapping change** |
| Year | `year` (int-usable) | `year` (**string** `"2002"`) | client casts to `int` |
| Value | `value` | `value` (float) | same |
| Flag | `magnitude` | `magnitude` | values differ (see below) |
| Label | from metadata | `indicator_label_en` | inline, no extra call |

## Impacts on this codebase

1. **Fetch — fewer calls.** `fetch_data.py` becomes a single IN-list query +
   Python bucketing instead of a per-indicator loop.
2. **Coverage — ~70× fewer calls.** World coverage was 214 countries × N
   indicators of fetch-then-count. Now one `group_by(country_id)` aggregation per
   indicator (paginated, ≤3 pages for ≤214 countries).
3. **Pagination is new.** Must page at `limit=100`. Filtered single-country /
   single-indicator queries stay small; only coverage country-lists page.
4. **Year is a string** in DataHub — cast to `int` in the client so downstream
   int comparisons (`year > threshold`) keep working.
5. **No catalogue/geo endpoints.** `validate_indicator_ids` and any geo-unit
   listing must be expressed as ODSQL aggregations over `uis001`.
6. **Codebooks unchanged.** ID resolution, country/alias resolution, and
   population weighting still come from the local codebooks — DataHub only
   replaces the data-fetch layer.

## Verified gotchas (DataHub / ODSQL)

- **`magnitude` values in `uis001` are only `null` and `NIL`** (≈1.44M null,
  ≈24.5k NIL). The legacy excluded flags `SUPP` / `NA` / `INCLUDED` do **not**
  appear here. The validity filter is retained anyway (defensive; applies to
  other UIS datasets and future releases).
- **`uis001` contains BOTH observed and modelled estimates.** Modelled
  completion-rate IDs `CR.MOD.*` are present (12 variants confirmed). The
  codebook's `excluded_id_prefixes` filter (`CR.MOD.`, `LR.GALP.`) is therefore
  **required** to keep modelled estimates out of "observed" results — it is not
  redundant. <!-- verified 2026-06-16 -->
- **ODSQL `like` with `%` is unreliable for prefix matching.** It is
  token-boundary sensitive: `like "CR.MOD.%"` matched, but `like "LR.AG15%"`
  returned 0 even though exact `indicator_id="LR.AG15T99"` returns 1,140 records.
  **Use exact codebook IN-lists, never `like` prefixes.**
- **`group_by` `total_count` is capped to `limit`.** A `group_by=indicator_id`
  with `limit=100` reports `total_count=100` regardless of the true number of
  groups — do not use it to count distinct values. Use `/facets` instead.
- **Distinct indicator_ids in `uis001`: ~103** (via `/facets?facet=indicator_id`,
  likely capped near the facet display limit; exact count needs paginated facets).
- **`year` numeric comparison works** on the string field — ODS coerces
  (`year>2020` filters correctly).

## Open question for the migration

Does `uis001` carry the **same indicator coverage** as the legacy API for every
SDG number in the codebook? Confirmed present so far: literacy (`LR.AG15T99`),
modelled completion (`CR.MOD.*`). Not yet exhaustively cross-checked against all
45 codebook SDG entries. Recommended check during execution: run
`validate_indicator_ids` over the full set of codebook IDs and report any
`not_in_api` results.

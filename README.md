# Subway Flooding Event Catalog — pipeline

An open, **provenance-first** catalog of subway/metro flooding events. It ingests
heterogeneous sources (text, images, satellite, video, tabular), uses a model per
modality to extract structured facts, and keeps every fact linked to the **exact
region of its original source** so anyone can verify it. Built to run cheaply and
be open-sourced for researchers worldwide.

> Design details: **[ARCHITECTURE.md](ARCHITECTURE.md)** ·
> Evolving vocabulary: **[schema/ontology.md](schema/ontology.md)**

## Why this design

- **Lifecycle, not snapshots** — every fact is tagged with a PPRR phase
  (Prevention / Preparedness / Response / Recovery = before / during / after).
- **Verifiable** — each fact stores a *locator* (text span, image bbox, video
  timecode…) back to its source asset. Click a fact → see exactly where it came from.
- **Soft schema** — the vocabulary is discovered and grown over time, not fixed
  up front (`Claim` is a flexible triple; `Event.extra` is an escape hatch).
- **Cheap & open** — raw files in low/zero-egress object storage (Cloudflare R2 /
  Backblaze B2); facts in a small graph + Parquet; a static, CDN-friendly website.

## Quickstart

```bash
pip install -e .            # pydantic + duckdb (stub demo needs nothing else)
python examples/ida_2021/run_demo.py
# then open build/site/index.html and click a fact to highlight its source
```

The demo runs **fully offline** (stub extractors, no API keys) on the NYC
Hurricane Ida (Sept 1–2, 2021) event, and writes:

```
build/
  site/        # static website: event pages + provenance viewer (open index.html)
  data/        # events.parquet, assets.parquet, facts.parquet (+ DuckDB dump)
  graph/       # nodes.json, edges.json, load.cypher  (Neo4j/Kuzu-loadable)
```

Query the metrics tier with plain SQL (DuckDB):

```python
import duckdb
duckdb.sql("SELECT phase, count(*) FROM 'build/data/facts.parquet' GROUP BY phase")
```

## How it fits together

```
Asset (raw file)                                   Tier 1: object store (R2/B2)
   │  ExtractionRouter.route(asset)
   ▼
Extractor (text LLM / image VLM / …)  ── stub or real model
   │  emits FactRecord[]  (claim + PPRR phase + source locator + provenance)
   ▼
Catalog.ingest → stores to:
   ├─ GraphStore   (event knowledge graph)         Tier 2
   ├─ MetricsStore (DuckDB / Parquet metrics)       Tier 2
   └─ build_site   (static browse/query + viewer)   Tier 3
```

## Repo layout

| Path | What |
|---|---|
| `src/flood_catalog/models.py` | Event / FactRecord / Locator — the soft schema + provenance |
| `src/flood_catalog/ingest/` | `ExtractionRouter` (modality → extractor) |
| `src/flood_catalog/extract/` | text + image extractors (stub mode), base class |
| `src/flood_catalog/store/` | blobs (Tier 1), graph + tables (Tier 2) |
| `src/flood_catalog/site/` | static-site builder + provenance viewer (Tier 3) |
| `examples/ida_2021/` | worked example + source files |
| `schema/ontology.md` | the controlled vocabulary you grow as you discover it |

## Wiring real models

The extractors run in `stub=True` mode by default. To use real models, implement
`Extractor._infer` (see `extract/base.py`) for your provider — parse the model's
structured output into `FactRecord`s **and keep the locator** (span/bbox/timecode).
Optional backends are declared as extras in `pyproject.toml`
(`extract`, `graph`, `geo`).

## Tests

```bash
pip install pytest && pytest -q
```

The suite enforces the key invariant: **every fact is traceable to a source
region** (text spans match the document; image facts carry a bbox).

## Licenses

Code **MIT** · data **CC-BY-4.0** · schema/vocabulary **CC0**. See `LICENSE` and
`data/LICENSE-DATA.md`. Example source text/images are illustrative placeholders
(paraphrased from public reporting), not original press material.

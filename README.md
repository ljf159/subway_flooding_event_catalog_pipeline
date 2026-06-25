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
  stac/        # catalog.json + items/  (STAC 1.0.0, for satellite scenes)
```

Query the metrics tier with plain SQL (DuckDB):

```python
import duckdb
duckdb.sql("SELECT phase, count(*) FROM 'build/data/facts.parquet' GROUP BY phase")
```

## How it fits together

```
Collectors (X · Weibo · news RSS · GDELT)   ── stub (fixtures) or live API
   │  CollectedItem → item_to_asset (snippet stored, full item linked)
   ▼
Asset (raw file or collected snippet)              Tier 1: object store (R2/B2)
   │  ExtractionRouter.route(asset)
   ▼
Extractor (text LLM / image VLM / satellite / …)  ── stub or real model
   │  emits FactRecord[]  (claim + PPRR phase + source locator + provenance)
   ▼
Catalog.ingest → stores to:
   ├─ GraphStore   (event knowledge graph)         Tier 2
   ├─ MetricsStore (DuckDB / Parquet metrics)       Tier 2
   ├─ StacStore    (satellite scenes)               Tier 2 (geo)
   └─ build_site   (static browse/query + viewer)   Tier 3
```

## Repo layout

| Path | What |
|---|---|
| `src/flood_catalog/models.py` | Event / FactRecord / Locator — the soft schema + provenance |
| `src/flood_catalog/collect/` | source collectors (X · Weibo · RSS · GDELT) + `collect` CLI |
| `src/flood_catalog/ingest/` | `ExtractionRouter` (modality → extractor) |
| `src/flood_catalog/extract/` | text + image + satellite extractors (stub + real), base class |
| `src/flood_catalog/store/` | blobs (Tier 1), graph + tables + STAC (Tier 2) |
| `src/flood_catalog/site/` | static-site builder + provenance viewer (Tier 3) |
| `examples/ida_2021/` | worked example + source files |
| `schema/ontology.md` | the controlled vocabulary you grow as you discover it |

## Real extraction (Claude)

The extractors run offline in `stub=True` mode by default. Real extraction is
**wired** for text and images using Claude (Anthropic SDK):

```bash
pip install -e '.[extract]'        # anthropic + docling + pillow
export ANTHROPIC_API_KEY=sk-...
python examples/ida_2021/run_demo.py --real   # text via Claude; SVG stays stub
```

- **Text** (`extract/text.py` → `extract/llm.py`): documents are parsed to text
  with **Docling** (`extract/parse.py`, tables preserved), then Claude
  (`messages.parse` + Pydantic) returns claims each carrying a **verbatim quote**.
  We locate that quote in the source to compute the character span — the model is
  never trusted for offsets.
- **Images** (`extract/image.py`): a base64 image goes to Claude vision, which
  returns claims each with a **pixel bbox**; we read the image's true dimensions
  (`extract/imageutil.py`) so boxes are in real pixels. Needs a raster format
  (PNG/JPEG/GIF/WebP) — the demo's placeholder is an SVG, so it stays on the stub.
- **Satellite** (`extract/satellite.py`, the `geo` extra): a flood/water raster
  (COG) is opened with rasterio; a water mask (NDWI on optical bands, or a
  thresholded flood product) is vectorized into polygons (`extract/geoutil.py`),
  emitting one `observed_flood_extent` fact per polygon with the lon/lat
  **GeoJSON polygon** as its GEO locator. The imagery is **not re-hosted** — it's
  catalogued via **STAC** (`store/stac.py` → `build/stac/`, the imagery linked by
  the item's `source` href) while the catalog keeps the derived flood extents.
  The static viewer draws geo facts as an offline SVG polygon.

Default model is `claude-opus-4-8`; pass `model=` to `ExtractionRouter` /
extractor to use a cheaper one (e.g. `claude-haiku-4-5`) at scale. To add a
modality, implement `Extractor._infer` (see `extract/base.py`) and **keep the
locator** (span / bbox / timecode). Optional backends are declared as extras in
`pyproject.toml` (`extract`, `graph`, `geo`).

## Collecting source data (X · Weibo · news · GDELT)

The `collect/` layer fetches posts/articles about an event and feeds them into
the same ingest→extract pipeline. Each source has a `Collector`; collected items
become TEXT `Asset`s carrying their provenance (platform, author, posted-at,
link) in `properties`. We store only the **snippet the source provides** (post
text, or an article's title+summary) and link the full item — never a scraped
article body (respects copyright/ToS).

| Source | Access | Status |
|---|---|---|
| News **RSS/Atom** (CNN/BBC/local) | free, no auth | live |
| **GDELT** DOC 2.0 (global news index) | free, no auth | live |
| **X** (Twitter) API v2 recent search | paid key in `$X_BEARER_TOKEN` | live behind token; stub+fixture otherwise |
| **Weibo** API | account/token in `$WEIBO_ACCESS_TOKEN` | live behind token; stub+fixture otherwise |

On-demand CLI (`flood-collect` once installed, or `python -m flood_catalog.collect`):

```bash
# Live, free sources:
python -m flood_catalog.collect --event ida-2021-nyc \
  --term "subway flood" --term "MTA Ida" \
  --rss https://feeds.bbci.co.uk/news/rss.xml --gdelt --out build

# Fully offline demo against bundled fixtures (all four sources, dedup):
python examples/ida_2021/run_collect.py
```

Re-running is safe — items dedup on source URL and content hash. Extraction runs
in stub mode unless `--real-extract` (needs the `extract` extra + key). Add a new
source by subclassing `Collector` and registering it in the CLI.

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

# Architecture — Subway Flooding Event Catalog

A multi-modal, provenance-first pipeline that turns heterogeneous sources
(text, images, satellite, video, tabular) into a **structured, queryable, open**
catalog of subway/metro flooding events — designed to run on a tight budget and
be open-sourced for researchers worldwide.

---

## 1. Goals & constraints

| Goal | Consequence for the design |
|---|---|
| Describe each event across its whole lifecycle | **PPRR** phases (Prevention/Preparedness/Response/Recovery) on every fact |
| Ingest many formats (text, image, satellite, video, JSON…) | A **router → modality extractor** layer with one uniform output |
| Always be able to verify a fact against its source | **Provenance** locator pointing to the *exact region* of the original asset |
| No fixed schema; discover & evolve it | **Soft schema** (flexible `Claim`, `Event.extra`) + a vocabulary doc you grow |
| Large data volume, limited budget | **Separate blobs from facts**; low/zero-egress object storage; static-first site |
| Open to the world | Open licenses, open standards (STAC/PROV/SOSA), reproducible pipeline, DOI releases |

---

## 2. The core principle: three tiers, linked by IDs + provenance

Never store big files and extracted knowledge in the same place. Split the data
into three tiers connected by stable IDs:

```
TIER 1 — RAW ASSETS  (big, cheap, write-once, content-addressed)
  images · satellite COGs · videos · PDFs · JSON · audio
  → object storage (Cloudflare R2 / Backblaze B2). filename = sha256.
            │  every fact carries {asset_id + locator} back to here
TIER 2 — STRUCTURED FACTS  (small, queryable — THE catalog)
  event graph (Kuzu/Neo4j)  +  metrics tables (DuckDB/Parquet)  +  STAC (geo)
            │  indexed / exported for retrieval
TIER 3 — SEARCH / SERVING  (derived, rebuildable)
  full-text + facets (Meilisearch) · vectors · static Parquet (DuckDB-WASM) · website
```

Tier 1 is huge but ~$/TB. Tier 2 is text/JSON, so small and basically free to
query. Tier 3 is disposable — regenerate it any time. This separation is what
lets a global audience be served on a small budget.

---

## 3. Provenance model (the heart of "verify the source")

Every extracted fact is a `FactRecord` that binds a claim to the exact place it
came from. See `src/flood_catalog/models.py`.

```
FactRecord
├── claim        subject · predicate · value · unit · time · geo   (soft schema)
├── phase        prevention | preparedness | response | recovery   (PPRR)
├── source       asset_id  +  Locator
│                  Locator selectors (W3C Web Annotation style):
│                    text_span (start,end,quote) · bbox (image/frame)
│                    time_range (audio/video) · page · geo · row · byte_range
├── extraction   method · model · version · confidence · run_id    (PROV-O lineage)
└── verification human_reviewed · reviewer · status                (human-in-the-loop)
```

Result: in the UI, clicking any fact opens its source asset and highlights the
**exact** text span / image box / video timecode it was drawn from. This is free
if (and only if) the locator is captured at extraction time — so it is a
first-class field, not an afterthought.

Standards reused instead of invented: **W3C Web Annotation** (sub-asset
selectors), **PROV-O** (lineage), **PPRR** (phases), **schema.org Event / SOSA /
STAC** (field names).

---

## 4. Multi-modal extraction: one model *per modality*, one output shape

`ExtractionRouter` dispatches each `Asset` to the right `Extractor` by
`Modality`. Every extractor emits the *same* `FactRecord` shape, which is what
lets one catalog absorb many formats. Add a modality = add an extractor + one
registry line; nothing downstream changes.

| Modality | Production extractor | Locator | Status in repo |
|---|---|---|---|
| text / PDF / news | Docling/Unstructured → LLM (Claude / Qwen3) + Instructor | text_span | ✅ stub implemented |
| image / ground photo | VLM (Claude/GPT-4o, or Qwen2.5-VL / Pixtral) + Grounding DINO | bbox | ✅ stub implemented |
| satellite / SAR | Sentinel-1/2 flood-extent models, GeoLLaVA; catalog via STAC | geo | 🔲 TODO |
| video | yt-dlp → Whisper + keyframe VLM | time_range / bbox | 🔲 TODO |
| audio | Whisper → LLM | time_range | 🔲 TODO |
| tabular / API | schema mapping + LLM for messy fields | row | 🔲 TODO |
| geospatial vector | geopandas / GDAL | geo | 🔲 TODO |

Each extractor ships a **stub mode** returning deterministic facts, so the whole
pipeline runs offline (CI, demos) with no API keys. Real inference goes behind
`Extractor._infer`.

---

## 5. Storage on a budget: store what's yours, *link* what isn't

The budget killer for a **public** dataset is **egress** (download bandwidth),
not storage.

- **Object storage (Tier 1):** Cloudflare **R2** (zero egress) or Backblaze
  **B2 + Cloudflare CDN** (free egress via Bandwidth Alliance) ≈ **15–17× cheaper
  than S3** for a public download site. The `LocalBlobStore` interface is
  S3-shaped, so an `R2BlobStore` drops in unchanged.
- **Store vs. link** (biggest cost lever; also keeps you legal):

  | Data | Store bytes? | Why |
  |---|---|---|
  | Your extracted facts/JSON | ✅ (tiny) | this *is* the catalog |
  | Photos/docs you have rights to | ✅ in R2 | needed for verification |
  | Copyrighted news/video | ❌ link + excerpt/thumbnail + facts | copyright + space |
  | **Satellite imagery** | ❌ **catalog via STAC, link to public archives** | petabytes already free on Planetary Computer / AWS Open Data |

  `Asset.rehosted=False` keeps the metadata + `original_url` only — no bytes.
- **Structured facts (Tier 2)** are text/JSON → small and effectively free:
  property graph (Kuzu → Neo4j) for narrative traversal; DuckDB/Parquet for
  metrics; STAC (static JSON) for geo/satellite assets.

**The variable cost is extraction compute, not storage or serving** — which is
the right place to spend a limited budget (and can be driven near-zero with open
VLMs).

---

## 6. Serving & website: static-first

Most of the catalog can be served as static files on a global CDN **for free**,
with no backend to run:

- **Browse/query UI:** Next.js or SvelteKit on **Cloudflare Pages / GitHub Pages**.
- **Query:** publish Parquet to R2 → **DuckDB-WASM** runs real SQL *in the
  browser*; ~zero server cost.
- **Search:** Meilisearch / Typesense (cheap OSS) for full-text + facets.
- **Maps:** MapLibre/Leaflet + the STAC layer for flood extents.
- **Provenance viewer:** open the source asset, highlight the locator region.
- **API only where needed** (curation writes, semantic search, GraphRAG Q&A):
  FastAPI on a small VPS or Cloudflare Workers.

This repo ships a **self-contained static demo** of the viewer
(`src/flood_catalog/site/`) that inlines each event's data and copies its
rehosted assets — it opens directly from `file://` and deploys to any static
host. It is the seed of the production frontend.

---

## 7. Open & reusable (a design requirement, not an afterthought)

- **Licenses:** data **CC-BY-4.0**, code **MIT**, schema/vocabulary **CC0**.
- **FAIR:** stable IDs, machine-readable schema, standard vocabularies (STAC,
  SOSA, PROV-O, schema.org Event) for interoperability.
- **Reproducible:** ship the pipeline + schema, not just the data; new events
  arrive as PRs.
- **Citable:** tag versioned dataset releases; mint a **DOI via Zenodo**.

---

## 8. What's in this repo today

```
src/flood_catalog/
  models.py            # Event, FactRecord, Locator, provenance — the soft schema
  ingest/router.py     # Modality -> Extractor dispatch
  extract/             # text + image extractors (stub mode), base class
  store/
    blobs.py           # Tier 1: content-addressed object store (S3-shaped)
    tables.py          # Tier 2: DuckDB metrics + Parquet export
    graph.py           # Tier 2: property graph -> nodes/edges JSON + Cypher (+optional Kuzu)
  site/build.py        # Tier 3: static site + provenance viewer
  catalog.py           # orchestration: ingest -> extract -> store -> export
examples/ida_2021/     # NYC Hurricane Ida worked example (runs offline)
schema/ontology.md     # the evolving vocabulary you curate
tests/                 # provenance invariants
```

Run `python examples/ida_2021/run_demo.py`, then open `build/site/index.html`.

---

## 9. Roadmap

1. **Now:** schema + provenance + text/image stubs + static viewer + Ida example. ✅
2. **Wire real models:** implement `_infer` for text (Docling+LLM) and image (VLM).
3. **Add modalities:** satellite (STAC + flood-extent), video (Whisper+VLM), tabular.
4. **Entity resolution:** dedupe stations/agencies; link to Wikidata/GeoNames/GTFS.
5. **Production frontend:** Next.js + MapLibre + DuckDB-WASM + Meilisearch over R2.
6. **Governance:** curation workflow (human verification), CC-BY release + Zenodo DOI.

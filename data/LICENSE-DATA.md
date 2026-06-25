# Data license

Catalog **data** (extracted facts, schema instances, metadata) is released under
**Creative Commons Attribution 4.0 International (CC-BY-4.0)**:
https://creativecommons.org/licenses/by/4.0/

You may share and adapt the data for any purpose, including commercially,
provided you give appropriate credit and indicate changes.

## Source assets — important

Raw source assets (Tier 1: news articles, photos, video, satellite imagery) are
**owned by their respective rights holders** and are **not** relicensed here.

- Where we have redistribution rights, assets are stored and served from object
  storage with their `license` recorded on the `Asset`.
- Where we do **not**, the catalog stores only the extracted facts plus a link
  (`Asset.original_url`, `rehosted = false`) — not the bytes. Follow the link to
  the original source for its terms.

Always check an individual `Asset`'s `license` / `publisher` / `original_url`
before reusing the underlying file.

## Example data in this repo

The files under `examples/` (e.g. `mta_ida_report.txt`, `flooded_station.svg`)
are **illustrative placeholders** created for the demo — paraphrased summaries
and a stylized drawing — not original press material. They exist only to make the
pipeline runnable end-to-end.

## How to cite

A `CITATION.cff` and a Zenodo DOI will accompany tagged dataset releases.

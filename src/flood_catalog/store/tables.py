"""Tier 2 (tabular): DuckDB store for events / assets / facts + metrics.

DuckDB is embedded (no server), reads/writes Parquet, and the same Parquet files
can be queried *in the browser* with DuckDB-WASM -- which is how the public site
serves SQL queries at ~zero compute cost. Use this for cross-event analytics
(rainfall, dollars, downtime); use the graph store for narrative traversal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import duckdb

from flood_catalog.models import Asset, Event, FactRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id        VARCHAR PRIMARY KEY,
    name            VARCHAR,
    hazard_type     VARCHAR,
    city            VARCHAR,
    country         VARCHAR,
    transit_system  VARCHAR,
    started_at      TIMESTAMP,
    ended_at        TIMESTAMP,
    summary         VARCHAR,
    extra           JSON
);
CREATE TABLE IF NOT EXISTS assets (
    asset_id      VARCHAR PRIMARY KEY,
    modality      VARCHAR,
    media_type    VARCHAR,
    uri           VARCHAR,
    original_url  VARCHAR,
    title         VARCHAR,
    publisher     VARCHAR,
    license       VARCHAR,
    rehosted      BOOLEAN,
    bytes         BIGINT
);
CREATE TABLE IF NOT EXISTS facts (
    fact_id        VARCHAR PRIMARY KEY,
    event_id       VARCHAR,
    phase          VARCHAR,
    subject        VARCHAR,
    predicate      VARCHAR,
    value          VARCHAR,
    unit           VARCHAR,
    claim_time     TIMESTAMP,
    asset_id       VARCHAR,
    selector_type  VARCHAR,
    locator        JSON,
    method         VARCHAR,
    model          VARCHAR,
    confidence     DOUBLE,
    human_reviewed BOOLEAN,
    tags           VARCHAR
);
"""


class MetricsStore:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.db_path)
        self.con.execute(_SCHEMA)

    # -- writes ------------------------------------------------------------ #
    def upsert_event(self, e: Event) -> None:
        self.con.execute("DELETE FROM events WHERE event_id = ?", [e.event_id])
        self.con.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                e.event_id, e.name, e.hazard_type, e.city, e.country,
                e.transit_system, e.started_at, e.ended_at, e.summary,
                json.dumps(e.extra),
            ],
        )

    def upsert_asset(self, a: Asset) -> None:
        self.con.execute("DELETE FROM assets WHERE asset_id = ?", [a.asset_id])
        self.con.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                a.asset_id, a.modality.value, a.media_type, a.uri, a.original_url,
                a.title, a.publisher, a.license, a.rehosted, a.bytes,
            ],
        )

    def upsert_facts(self, facts: Iterable[FactRecord]) -> None:
        for f in facts:
            self.con.execute("DELETE FROM facts WHERE fact_id = ?", [f.fact_id])
            self.con.execute(
                "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    f.fact_id, f.event_id, f.phase.value,
                    f.claim.subject, f.claim.predicate, f.claim.value, f.claim.unit,
                    f.claim.time, f.source.asset_id,
                    f.source.locator.selector_type.value,
                    f.source.locator.model_dump_json(exclude_none=True),
                    f.extraction.method.value, f.extraction.model,
                    f.extraction.confidence, f.verification.human_reviewed,
                    ",".join(f.tags),
                ],
            )

    # -- reads / exports --------------------------------------------------- #
    def query(self, sql: str):
        return self.con.execute(sql).fetchall()

    def export_parquet(self, out_dir: Path | str) -> None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for table in ("events", "assets", "facts"):
            self.con.execute(
                f"COPY {table} TO '{out / (table + '.parquet')}' (FORMAT PARQUET)"
            )

    def close(self) -> None:
        self.con.close()

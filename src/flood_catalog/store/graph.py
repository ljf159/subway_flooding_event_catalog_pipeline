"""Tier 2 (graph): the event knowledge graph.

Exports a portable labeled-property-graph (nodes.json + edges.json) plus a
``load.cypher`` script so the same graph loads into Neo4j *or* Kuzu unchanged.
We avoid a hard dependency on any graph engine -- the JSON export is the source
of truth and the Cypher is generated from it.

Graph shape (grows as the schema is discovered):

    (:Event)-[:HAS_FACT]->(:Fact)-[:SOURCED_FROM]->(:Asset)
    (:Fact)-[:ABOUT]->(:Entity)
    (:Fact)-[:IN_PHASE]->(:Phase)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from flood_catalog.models import Asset, Event, FactRecord


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GraphStore:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}   # node_id -> {labels, props}
        self.edges: list[dict] = []        # {src, rel, dst}

    # -- building ---------------------------------------------------------- #
    def _node(self, node_id: str, label: str, **props) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "label": label, "props": {}}
        self.nodes[node_id]["props"].update({k: v for k, v in props.items() if v is not None})
        return node_id

    def _edge(self, src: str, rel: str, dst: str) -> None:
        e = {"src": src, "rel": rel, "dst": dst}
        if e not in self.edges:
            self.edges.append(e)

    def add_event(self, event: Event) -> None:
        self._node(
            event.event_id, "Event",
            name=event.name, city=event.city, country=event.country,
            transit_system=event.transit_system, hazard_type=event.hazard_type,
        )

    def add_asset(self, asset: Asset) -> None:
        self._node(
            asset.asset_id, "Asset",
            modality=asset.modality.value, media_type=asset.media_type,
            uri=asset.uri, original_url=asset.original_url,
            title=asset.title, rehosted=asset.rehosted,
        )

    def add_facts(self, facts: Iterable[FactRecord]) -> None:
        for f in facts:
            self._node(
                f.fact_id, "Fact",
                predicate=f.claim.predicate, value=f.claim.value, unit=f.claim.unit,
                phase=f.phase.value, confidence=f.extraction.confidence,
                method=f.extraction.method.value,
            )
            phase_id = f"phase:{f.phase.value}"
            entity_id = f.claim.subject
            self._node(phase_id, "Phase", name=f.phase.value)
            self._node(entity_id, "Entity", name=entity_id)

            self._edge(f.event_id, "HAS_FACT", f.fact_id)
            self._edge(f.fact_id, "SOURCED_FROM", f.source.asset_id)
            self._edge(f.fact_id, "ABOUT", entity_id)
            self._edge(f.fact_id, "IN_PHASE", phase_id)

    # -- export ------------------------------------------------------------ #
    def export_json(self, out_dir: Path | str) -> None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "nodes.json").write_text(
            json.dumps(list(self.nodes.values()), indent=2, default=str)
        )
        (out / "edges.json").write_text(json.dumps(self.edges, indent=2))
        (out / "load.cypher").write_text(self._to_cypher())

    def _to_cypher(self) -> str:
        lines = ["// Generated graph load script (Neo4j / Kuzu compatible-ish)"]
        for n in self.nodes.values():
            props = ", ".join(
                f"{k}: '{_esc(str(v))}'" for k, v in {"id": n["id"], **n["props"]}.items()
            )
            lines.append(f"MERGE (:{n['label']} {{{props}}});")
        lines.append("")
        for e in self.edges:
            lines.append(
                f"MATCH (a {{id:'{_esc(e['src'])}'}}), (b {{id:'{_esc(e['dst'])}'}}) "
                f"MERGE (a)-[:{e['rel']}]->(b);"
            )
        return "\n".join(lines) + "\n"

    def to_kuzu(self, db_path: Path | str) -> bool:  # pragma: no cover - optional dep
        """Load into an embedded Kuzu database if kuzu is installed.

        Returns True on success, False if kuzu isn't available. The JSON/Cypher
        export is always produced regardless, so this is a convenience only.
        """
        try:
            import kuzu  # type: ignore
        except ImportError:
            return False
        db = kuzu.Database(str(db_path))
        conn = kuzu.Connection(db)
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS Node(id STRING, label STRING, "
            "props STRING, PRIMARY KEY(id))"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS REL(FROM Node TO Node, rel STRING)"
        )
        for n in self.nodes.values():
            conn.execute(
                "MERGE (x:Node {id: $id}) SET x.label=$label, x.props=$props",
                {"id": n["id"], "label": n["label"], "props": json.dumps(n["props"], default=str)},
            )
        for e in self.edges:
            conn.execute(
                "MATCH (a:Node {id:$s}),(b:Node {id:$d}) MERGE (a)-[r:REL]->(b) SET r.rel=$rel",
                {"s": e["src"], "d": e["dst"], "rel": e["rel"]},
            )
        return True

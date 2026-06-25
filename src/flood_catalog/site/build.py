"""Tier 3: static-site builder (the public browse/query layer).

Produces a self-contained, server-less site: each event page inlines its data
and copies its (rehosted) source assets, so it opens directly in a browser and
deploys to any static host (Cloudflare Pages / GitHub Pages -- free + global CDN).

The key feature is the *provenance viewer*: clicking a fact highlights the exact
region of its source asset (bbox over an image, the quote over text). This is the
"look at the source and verify" loop, served for free as static files.

For a richer production site, point a Next.js/MapLibre frontend at the exported
Parquet (query in-browser with DuckDB-WASM) and the STAC catalog for imagery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from flood_catalog.models import Asset, Event, FactRecord
from flood_catalog.store.blobs import LocalBlobStore


def _asset_payload(asset: Asset, site_root: Path, blobs: LocalBlobStore) -> dict:
    payload = {
        "asset_id": asset.asset_id,
        "modality": asset.modality.value,
        "media_type": asset.media_type,
        "original_url": asset.original_url,
        "title": asset.title,
        "rehosted": asset.rehosted,
        "site_path": None,
        "text": None,
    }
    if asset.rehosted:
        src = blobs.local_path(asset)
        if src and src.exists():
            assets_dir = site_root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            dest = assets_dir / src.name
            dest.write_bytes(src.read_bytes())
            payload["site_path"] = f"assets/{src.name}"
            if asset.media_type.startswith("text/"):
                payload["text"] = src.read_text(errors="replace")
    return payload


def _fact_payload(f: FactRecord) -> dict:
    return {
        "fact_id": f.fact_id,
        "phase": f.phase.value,
        "subject": f.claim.subject,
        "predicate": f.claim.predicate,
        "value": f.claim.value,
        "unit": f.claim.unit,
        "confidence": f.extraction.confidence,
        "method": f.extraction.method.value,
        "model": f.extraction.model,
        "human_reviewed": f.verification.human_reviewed,
        "tags": f.tags,
        "asset_id": f.source.asset_id,
        "locator": f.source.locator.model_dump(exclude_none=True),
    }


def build_site(
    site_dir: Path | str,
    *,
    events: Iterable[Event],
    assets: dict[str, Asset],
    facts: Iterable[FactRecord],
    blobs: LocalBlobStore,
) -> Path:
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    events = list(events)
    facts = list(facts)

    index_rows = []
    for event in events:
        ev_facts = [f for f in facts if f.event_id == event.event_id]
        used_asset_ids = {f.source.asset_id for f in ev_facts}
        ev_assets = {
            aid: _asset_payload(assets[aid], site_dir, blobs)
            for aid in used_asset_ids
            if aid in assets
        }
        data = {
            "event": event.model_dump(mode="json"),
            "assets": ev_assets,
            "facts": [_fact_payload(f) for f in ev_facts],
        }
        page = f"event-{event.event_id}.html"
        (site_dir / page).write_text(_event_html(data))
        index_rows.append((event, len(ev_facts), page))

    (site_dir / "index.html").write_text(_index_html(index_rows))
    return site_dir


# --------------------------------------------------------------------------- #
# HTML templates (inline; no build step, no external assets)                   #
# --------------------------------------------------------------------------- #
def _index_html(rows) -> str:
    items = "\n".join(
        f'<li><a href="{page}">{ev.name}</a> '
        f'<span class="muted">— {ev.city or ""}, {ev.country or ""} · {n} facts</span></li>'
        for ev, n, page in rows
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Subway Flooding Event Catalog</title>{_CSS}
<body><div class="wrap">
<h1>Subway Flooding Event Catalog</h1>
<p class="muted">Open, provenance-first catalog of subway/metro flooding events.
Every fact links back to the exact region of its source. Data CC-BY · code MIT.</p>
<ul class="events">{items}</ul>
<p class="muted small">Static demo build. Production: query the exported Parquet in-browser
(DuckDB-WASM) and serve imagery via STAC. See ARCHITECTURE.md.</p>
</div></body></html>"""


def _event_html(data: dict) -> str:
    blob = json.dumps(data).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>{data['event']['name']}</title>{_CSS}
<body><div class="wrap">
<p><a href="index.html">&larr; all events</a></p>
<div id="app"></div>
<script id="data" type="application/json">{blob}</script>
<script>{_JS}</script>
</div></body></html>"""


_CSS = """<style>
:root{--bg:#0f1720;--card:#16212e;--ink:#e7eef6;--muted:#8aa0b4;--accent:#46b3ff;--hi:#ffcc4d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:24px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{margin:.2em 0}.muted{color:var(--muted)}.small{font-size:13px}
ul.events{list-style:none;padding:0}ul.events li{padding:10px 0;border-bottom:1px solid #22303f}
.phase{margin:18px 0 6px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
font-size:12px;color:var(--accent)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.fact{background:var(--card);border:1px solid #22303f;border-radius:10px;padding:10px 12px;
margin:8px 0;cursor:pointer}
.fact:hover{border-color:var(--accent)}.fact.active{border-color:var(--hi)}
.fact .claim{font-weight:600}.fact .meta{color:var(--muted);font-size:12px;margin-top:4px}
.pill{display:inline-block;background:#22303f;border-radius:999px;padding:1px 8px;
font-size:11px;margin-right:4px;color:var(--muted)}
.viewer{position:sticky;top:16px;background:var(--card);border:1px solid #22303f;
border-radius:10px;padding:12px;min-height:200px}
.imgwrap{position:relative;display:inline-block;max-width:100%}
.imgwrap img{max-width:100%;display:block;border-radius:6px}
.box{position:absolute;border:2px solid var(--hi);
box-shadow:0 0 0 9999px rgba(0,0,0,.45);border-radius:2px}
.txt{white-space:pre-wrap;font-size:14px}.txt mark{background:var(--hi);color:#000;padding:0 2px}
.kv{color:var(--muted);font-size:12px}
.geo svg{background:#0c141c;border-radius:6px;max-width:100%;height:auto}
.geo path{fill:rgba(70,179,255,.30);stroke:var(--hi);stroke-width:1.5;vector-effect:non-scaling-stroke}
</style>"""


_JS = r"""
const data = JSON.parse(document.getElementById('data').textContent);
const PHASES = ['prevention','preparedness','response','recovery'];
const app = document.getElementById('app');
const e = data.event;

function metrics(){
  const m = data.facts.filter(f=>f.unit).slice(0,6)
    .map(f=>`<span class="pill">${f.value} ${f.unit}</span>`).join(' ');
  return m ? `<p>${m}</p>` : '';
}

let html = `<h1>${e.name}</h1>
<p class="muted">${[e.city,e.country].filter(Boolean).join(', ')} · ${e.transit_system||''}</p>
<p>${e.summary||''}</p>${metrics()}
<div class="grid"><div id="facts"></div><div><div class="viewer" id="viewer">
<p class="muted">Click any fact to view its source evidence.</p></div></div></div>`;
app.innerHTML = html;

const factsEl = document.getElementById('facts');
for(const ph of PHASES){
  const fs = data.facts.filter(f=>f.phase===ph);
  if(!fs.length) continue;
  factsEl.insertAdjacentHTML('beforeend', `<div class="phase">${ph}</div>`);
  for(const f of fs){
    const conf = Math.round((f.confidence||0)*100);
    const tags = (f.tags||[]).map(t=>`<span class="pill">${t}</span>`).join('');
    const div = document.createElement('div');
    div.className='fact'; div.dataset.id=f.fact_id;
    div.innerHTML = `<div class="claim">${f.subject} · ${f.predicate}
      ${f.value?('= '+f.value+(f.unit?(' '+f.unit):'')):''}</div>
      <div class="meta">${f.method} · ${conf}% confidence ${tags}</div>`;
    div.onclick = ()=>showSource(f, div);
    factsEl.appendChild(div);
  }
}

function showSource(f, div){
  document.querySelectorAll('.fact.active').forEach(x=>x.classList.remove('active'));
  div.classList.add('active');
  const a = data.assets[f.asset_id]||{};
  const v = document.getElementById('viewer');
  const cite = a.original_url
    ? `<p class="kv">Source: <a href="${a.original_url}" target="_blank" rel="noopener">${a.title||a.original_url}</a> · ${a.asset_id.slice(0,18)}…</p>`
    : `<p class="kv">Source asset: ${a.asset_id}</p>`;
  const loc = f.locator||{};
  if(a.modality==='image' && a.site_path && loc.bbox){
    v.innerHTML = cite + `<div class="imgwrap"><img id="srcimg" src="${a.site_path}"></div>`;
    const img = document.getElementById('srcimg');
    const draw = ()=>{
      const sx = img.clientWidth/(img.naturalWidth||img.clientWidth);
      const sy = img.clientHeight/(img.naturalHeight||img.clientHeight);
      const [x,y,w,h] = loc.bbox;
      const b=document.createElement('div'); b.className='box';
      b.style.left=(x*sx)+'px'; b.style.top=(y*sy)+'px';
      b.style.width=(w*sx)+'px'; b.style.height=(h*sy)+'px';
      img.parentElement.appendChild(b);
    };
    if(img.complete) draw(); else img.onload = draw;
  } else if(a.text && (loc.quote||loc.start!=null)){
    const t=a.text; let s=loc.start, en=loc.end;
    if((s==null||s<0) && loc.quote){ s=t.indexOf(loc.quote); en=s+loc.quote.length; }
    const esc = x=>x.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    let body = (s>=0)
      ? esc(t.slice(0,s))+'<mark>'+esc(t.slice(s,en))+'</mark>'+esc(t.slice(en))
      : esc(t);
    v.innerHTML = cite + `<div class="txt">${body}</div>`;
    const mk=v.querySelector('mark'); if(mk) mk.scrollIntoView({block:'center'});
  } else if(loc.selector_type==='geo' && loc.geo){
    renderGeo(v, cite, loc.geo);
  } else {
    v.innerHTML = cite + `<p class="muted">${loc.quote||'(no inline preview for this source type)'}</p>`;
  }
}

// Render a GeoJSON Polygon/MultiPolygon as an offline SVG (no basemap/network).
function renderGeo(v, cite, geom){
  const rings=[];
  (function walk(c){ if(c&&typeof c[0][0]==='number') rings.push(c);
    else c.forEach(walk); })(geom.coordinates);
  let xmin=1e9,ymin=1e9,xmax=-1e9,ymax=-1e9;
  rings.forEach(r=>r.forEach(([x,y])=>{xmin=Math.min(xmin,x);ymin=Math.min(ymin,y);
    xmax=Math.max(xmax,x);ymax=Math.max(ymax,y);}));
  const W=320,H=240,pad=12, sx=(W-2*pad)/((xmax-xmin)||1), sy=(H-2*pad)/((ymax-ymin)||1);
  const s=Math.min(sx,sy);
  const px=x=>pad+(x-xmin)*s, py=y=>H-pad-(y-ymin)*s;  // flip lat (north up)
  const paths=rings.map(r=>'M'+r.map(([x,y])=>px(x).toFixed(1)+','+py(y).toFixed(1)).join('L')+'Z').join(' ');
  v.innerHTML = cite +
    `<div class="geo"><svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`+
    `<path d="${paths}"/></svg></div>`+
    `<p class="kv">flood extent · approx ${xmin.toFixed(3)},${ymin.toFixed(3)} → `+
    `${xmax.toFixed(3)},${ymax.toFixed(3)} (lon/lat) · catalogued via STAC</p>`;
}
"""

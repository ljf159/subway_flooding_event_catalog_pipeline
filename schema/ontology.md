# Catalog vocabulary (v0) — discover, define, improve

This is the **living schema**. The data model (`src/flood_catalog/models.py`) is
deliberately soft: `Claim` is a free `subject · predicate · value` triple and
`Event.extra` holds anything not yet promoted. This file is where the *team*
agrees on the controlled terms so facts stay consistent and queryable.

Workflow: extractors propose new subjects/predicates → review for frequency &
correctness → promote the good ones here → (optionally) tighten validation later.

---

## Phases (PPRR) — fixed

| value | meaning (maps to) |
|---|---|
| `prevention` | long-term mitigation / capital resilience (before) |
| `preparedness` | readiness in the hours/days before impact (before) |
| `response` | actions while the event unfolds (during) |
| `recovery` | restoration & lessons after (after) |

## Modalities — extend with each new extractor

`text` · `image` · `satellite` · `video` · `audio` · `tabular` · `geospatial`

## Locator selectors (W3C Web Annotation style) — fixed

`text_span` (start,end,quote) · `bbox` ([x,y,w,h]) · `time_range` (t_start,t_end) ·
`page` · `geo` (GeoJSON) · `row` (row,column) · `byte_range`

---

## Entity id conventions (subjects)

Use `type:slug`, lowercase, hyphenated. Resolve to external IDs where possible.

| prefix | example | link to |
|---|---|---|
| `system:` | `system:MTA-NYCT` | agency / operator |
| `agency:` | `agency:NWS` | org (Wikidata) |
| `station:` | `station:14th-St` | GTFS stop id |
| `line:` | `line:1` | GTFS route id |
| `asset:` | `asset:turnstiles` | facility/equipment |
| `people:` | `people:passengers` | affected population |
| `hazard:` | `hazard:rainfall` | driving hazard |

## Predicates seen so far (promote/curate here)

Group loosely by phase. Keep names `snake_case`. Record `unit` separately on the
claim (don't bake units into the predicate).

**Preparedness**
- `issued_warning` · `forecast_rainfall` · `pre_positioned_resource` · `closed_preemptively`

**Response**
- `service_status` (suspended / restored / single-tracking…)
- `flooded_locations_count` (unit: `locations`)
- `visible_water_depth` · `submerged` · `present_in_floodwater` (unit: `persons`)
- `rescue_action` · `evacuation`

**Recovery**
- `water_removed` (unit: `million gallons`)
- `infrastructure_damage_cost` (unit: `million USD`)
- `service_fully_restored_at` · `lesson_learned` · `mitigation_recommended`

**Prevention** (often added retrospectively)
- `capital_project` · `flood_barrier_installed` · `design_standard_changed`

## Units in use

`m` · `mm` · `hours` · `days` · `locations` · `persons` · `million gallons` ·
`million USD` · `USD`

---

## Open modeling questions (decide as the catalog grows)

- Promote recurring `extra` keys (e.g. peak hourly rainfall) to first-class `Event` fields?
- Model time as point vs. interval per phase (add `phase_started_at` / `phase_ended_at`)?
- Entity resolution authority: Wikidata + GTFS as canonical? add a `links` table?
- Confidence threshold + reviewer sign-off before a fact is "published"?

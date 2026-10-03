---
name: graph-engine
description: Draw charts, flowcharts, sequence diagrams, architecture maps, database schemas, maps, and math plots as SVG with diagonaldiagrams. One command checks the spec, draws, and audits the layout for collisions. Use for any request to chart, plot, diagram, or visualize data, logic, a codebase, or a schema.
---

# Draw with diagonaldiagrams

`graph.py` is one Python 3 file with no dependencies. Call it by absolute path:
`py -3 <path>/graph.py` on Windows, `python3 <path>/graph.py` elsewhere. If `diagonaldiagrams`
is on PATH, `diagonaldiagrams` is the same program. Not installed: run the `diagonaldiagrams-install` skill.

## One command

```
diagonaldiagrams <type> INPUT -o DIR/NAME.svg [flags]
```

It checks the input, draws, audits the result, and prints one JSON line:

- `"ok": true` with `svg`, `html`, `receipt` paths. Done. Show the SVG. For diagrams, `layout` lists
  each row's boxes left to right and each frame's members: read it to check the structure.
- `"ok": false`, `"stage": "validate"`: nothing drawn. Each error has a `fix`. Change the spec and rerun.
- `"ok": false` with audit errors: files are written, but labels collide, a label spills its box,
  or an arrow crosses a box. Change rank, lane, or the wording and rerun. Never edit the SVG.

`"ok": true` already means no label overlaps another label, no label is wider than its box or off
the canvas, no two boxes overlap, and no arrow crosses a box or a label. Do not screenshot the
figure or parse the SVG to check those again: every extra look costs a full round trip. Write the
spec and render it in one shell call when you can. Look at a PNG only to judge the content itself.

`describe <type>` prints the full contract for any type. You only need it for types not below.

## Diagrams: write Mermaid

Flowcharts, sequence diagrams, and ER diagrams can be plain Mermaid. Save it as `NAME.mmd` and run
`diagonaldiagrams mermaid NAME.mmd -o DIR/NAME.svg`; the same check, layout, and audit apply.

```
flowchart TD
  A([Push]) --> B{Risky?}
  B -->|yes| C[Review]
  B -->|no| D([Ship])
  C --> D
  subgraph ops [Operations]
    C
  end
```
`([x])` start or end, `[x]` step, `{x}` decision, `[(x)]` store. `-.->` dashed, `==>` and `:::focal`
coral. `subgraph` draws a frame. `sequenceDiagram` (`A->>B: call`, `B-->>A: reply`, `A-)B: event`) and
`erDiagram` (`A ||--o{ B : has`) work too. Not drawn: style and classDef colors, notes, loop or alt
blocks. Flows always draw top-down. A parse error names the line and the fix.

## Diagrams: JSON spec

Arrow and message labels draw in capitals in every diagram.

**flow** (decision logic) - `{title, sub, nodes, edges}`
```json
{"title": "Deploy", "nodes": [
  {"id": "push", "name": "Push", "shape": "oval"},
  {"id": "risky", "name": "Risky?", "shape": "diamond"},
  {"id": "review", "name": "Review", "sub": "owner", "lane": 1},
  {"id": "ship", "name": "Ship", "shape": "oval"}],
 "edges": [{"from": "push", "to": "risky"}, {"from": "risky", "to": "review", "label": "yes"},
           {"from": "risky", "to": "ship", "label": "no"}, {"from": "review", "to": "ship"}]}
```
shape: oval start/end, rect step (default), diamond decision with at most 3 labeled exits.
Layout is automatic: loops draw back up the outside, and free nodes move off arrows' paths.
`rank` (row, 0 at top) and `lane` (-1 left, 0 center, 1 right; -2 and 2 sit further out) pin a node.
Names wrap to three lines and boxes grow to fit; put detail in `sub`.
Frames: `"groups": [{"id": "ops", "name": "Operations", "nodes": ["review"]}]` (flow and arch).
Icons: `"icon": "database"` on a flow or arch node; `describe icons` lists them (Mermaid: `fa:fa-database`).

**seq** (messages over time) - `{title, sub, actors: [{id, name, sub, tag}], messages: [{from, to, label, reply, async, proto}]}`.
tag is USER, UI, GATEWAY, SVC, or STORE. `reply` and `async` draw dashed. `"proto": "https"` draws blue
and prefixes the label with [HTTPS].

**arch** (services) - `{title, nodes: [{id, name, sub, tag, layer}], edges: [{from, to, label, proto, async}]}`. `layer` is the row.

**schema** (tables) - `{title, tables: [{id, name, columns: [{name, type, pk, fk}]}], relations: [{from, from_col, to, to_col, label}]}`.

Budgets: flow and arch 9 nodes and 12 edges, seq 6 actors and 16 messages, schema 6 tables.
A bigger diagram reads worse: split it. If it must be one figure, add `"budget": false`.
At most 2 items get `"focal": true` (drawn in coral).

## Data: CSV with a header row

| type | flags |
| --- | --- |
| `bar` | `--cat COL --val COL [--group COL --sort desc --orientation h --unit ms]` |
| `line` | `--x COL --y COL [--group COL]` (x may be dates or labels like 2026-01) |
| `scatter` | `--x COL --y COL [--group COL --yerr COL --facet COL]` |
| `geo` | `--lat COL --lon COL [--label COL --val COL]` (or a GeoJSON file) |

All take `--title`, `--subtitle` (state the finding), `--xlabel`, `--ylabel`, `--source`.
`--highlight VALUE` draws one category or series in coral; highlight at most one.

## Everything else

`diagonaldiagrams chart <type> INPUT -o out/x.html`: sankey, gantt, heatmap, treemap, box, histogram,
pie, radar, state, org, timeline, math (`y = sin(x)`), and about 50 more. `describe` lists them;
`describe <type>` gives the columns or JSON shape. `terrain` is not drawn.

## Files and export

A render writes `NAME.svg`, `NAME.html` (the figure plus copy and download buttons), and
`NAME.graph.json` (the receipt), side by side in DIR, whether `-o` ends in .svg, .html, or nothing.
`export DIR/NAME --to png|pdf|svg` redraws from the receipt.
PNG and PDF need Edge, Chrome, or cairosvg; SVG needs nothing.

## Docs and drift

`doc DOC.md` compiles fenced `graph:<type>` blocks to SVGs. `extract schema|routes SRC` builds a
spec from SQL, Prisma, ORM models, or FastAPI/Flask routes. `monitor` and `sync` flag and fix diagram drift.
Recipes: `SKILL.md` at the diagonaldiagrams root.

## Taste

Shape carries meaning, not color. Blue is HTTP only. Dashed is async or a reply. Coral marks
at most two focal items. Titles state the finding. Details: `references/visual_grammar.md`.

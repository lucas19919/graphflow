# graph — agent skill

CLI that renders journal-grade graphs from data and specs. Pure Python stdlib.
No installs, no servers, deterministic output.

## The loop (always in this order)

```
1. infer    py graph.py infer DATA.csv                    # column roles → starter spec
2. describe py graph.py describe scatter|flow|arch        # minimal schema for the type
3. validate py graph.py validate SPEC.json|DATA.csv       # MUST pass before render (exit 0)
4. render   py graph.py scatter|flow|arch ... -o out/x.html
5. audit    py graph.py audit out/x.svg                   # MUST pass (exit 0); fix, re-render
6. export   py graph.py export out/x --to png --layout wide
```

Every step speaks JSON (except render/export, which write files). Chain on exit
codes. Never hand-edit the SVG — fix the spec or flags and re-render.

## Recipes

```bash
# data → journal scatter (groups + error bars + facets)
py graph.py infer exp.csv
py graph.py scatter exp.csv --x dose --y expr --yerr sd --group tissue --facet cohort \
  --title 'Dose response' --subtitle 'One-sentence finding.' \
  --xlabel Dose --xunit mg --ylabel Expression --yunit 'log2 counts' \
  --source 'lab notebook 2026-10' -o out/exp.html

# data → bar / line
py graph.py bar lat.csv --cat service --val p99 --unit ms --sort desc -o out/bar.html
py graph.py line tput.csv --x ts --y rps --group service -o out/line.html

# logic → decision flowchart (PAP/DIN 66001 shapes; auto-layout default)
py graph.py validate flow.json && py graph.py flow flow.json --corners sharp -o out/f.html
# --auto forces longest-path layering even when ranks are present (barycenter uncrossing)

# runtime → sequence (lifelines, sync/async/reply)
py graph.py validate seq.json && py graph.py seq seq.json -o out/seq.html

# database → schema (tables, PK/FK, relations)
py graph.py validate schema.json && py graph.py schema schema.json -o out/schema.html

# places → point map (CSV lat/lon, or GeoJSON points and polygons) on a built-in coastline. Not map tiles.
py graph.py geo cities.csv --lat lat --lon lon --label city --val people_m -o out/geo.html

# codebase → architecture view (one C4 level per render)
py graph.py arch containers.json -o out/arch.html
```

## Hard budgets (validate enforces, audit double-checks)

| rule | limit | over → |
|---|---|---|
| nodes | 9 | split overview + detail |
| edges | 12 | drop layout-obvious arrows |
| focal (coral) | 2 | demote rest |
| diamond exits | 3 | nest diamonds |
| seq actors / messages | 6 / 16 | split sub-sequences |
| schema tables / cols shown | 6 / 12 warn | split bounded contexts |
| bar bars / categories | 24 / 12 | top-N + Other |
| scatter points | 400 rendered | aggregate / facet |
| geo points | 400 | crop to the region |
| groups / facets | 8 / 4 | top-N + Other |

## Taste (non-negotiable)

- Shape carries type (oval=start/end, rect=step, diamond=decision) — never color.
- Blue `#2e5aa8` = HTTP/API only. Dashed = async. Coral = 1–2 focal max.
- Orthogonal elbows, masked arrow labels with gap. Title and subtitle are drawn on the figure. One system font.
- The HTML page is the diagram plus Copy SVG, Export SVG, and Export PNG. Print hides that bar. `--grid`, `--markers`, `--highlight` live on the chart.
- Ratio data never shows a negative axis. Ticks are nice numbers on the grid.

## MCP

`py graph.py mcp` serves the same loop as tools
(describe/validate/infer/audit/scatter/diagram/bar/line) over stdio for MCP clients.

`py graph.py doc DOC.md --out-dir assets [--check]` compiles fenced
```graph:<type> blocks to SVGs (+ `--check` for CI).
`py graph.py extract schema|routes SRC -o spec.json` reverse-extracts specs from
SQL DDL / Prisma / Python ORM (SQLAlchemy, Django, SQLModel) / FastAPI-Flask routes.
`py graph.py monitor --map graph.monitor.json [--ci]` flags drift;
`py graph.py sync --map graph.monitor.json [--docs ARCH.md] [--commit]` is the
auto-fix bot (extract → validate → doc → audit → local commit, never pushes).

# schemas.md — generated from `py graph.py describe <type>`
Single source of truth: the DESCRIBE dict in graph.py.

## scatter
```json
{
  "input": "CSV with header row. Two numeric columns minimum.",
  "writes": "py graph.py scatter DATA.csv --x X --y Y -o OUT.html  (+ OUT.svg self-contained, OUT.graph.json receipt)",
  "required": [
    "--x",
    "--y"
  ],
  "options": {
    "--title": "finding, not description",
    "--subtitle": "one sentence takeaway",
    "--figure": "Fig. number",
    "--xlabel/--xunit/--ylabel/--yunit": "axis + unit in parens",
    "--group": "categorical col, Okabe-Ito legend",
    "--yerr": "numeric SD/CI col, capped bars",
    "--facet": "categorical col, small multiples A/B (+col layout via export --layout social)",
    "--source": "provenance, n auto-appended",
    "--caption": "what/encoding sentence",
    "--corners": "sharp|rounded|editorial"
  },
  "budgets": {
    "points_rendered": 400,
    "groups": 8,
    "facets": 4,
    "series": "focal rule: 1 accent max"
  },
  "rules": [
    "non-negative data never shows a negative axis",
    "domain includes error bars",
    "ticks are nice numbers aligned to grid",
    "title and subtitle are drawn on the figure; the HTML page and the .svg are the same drawing"
  ],
  "example": "py graph.py scatter examples/scatter_groups.csv --x dose --y expr --yerr expr_err --group tissue --facet cohort --xlabel Dose --xunit mg --ylabel Expression --yunit 'log2 counts' -o out/s.html"
}
```

## flow
```json
{
  "input": "JSON spec {title, sub, nodes[], edges[]}",
  "writes": "py graph.py flow SPEC.json -o OUT.html",
  "node": {
    "id": "unique",
    "shape": "oval=start/end | rect=step | diamond=decision | dot=merge",
    "name": "2-4 words",
    "tag": "STEP|START|END",
    "sub": "mono sublabel",
    "rank": "row (default: order)",
    "lane": "-1 left|0 center|1 right (default 0)",
    "focal": "bool, max 2 per diagram"
  },
  "edge": {
    "from": "id",
    "to": "id",
    "label": "ALWAYS label decision exits",
    "focal": "happy-path bool"
  },
  "rules": [
    "top-down; Yes=right, No=down",
    "diamond \u22643 exits (nest for more)",
    "orthogonal elbows only",
    "labels masked with 6px gap",
    "shape carries type, never color",
    "no ranks needed: longest-path auto-layering + barycenter uncrossing (--auto forces it)"
  ],
  "budgets": {
    "nodes": 9,
    "edges": 12,
    "focal": 2,
    "over": "split overview+detail"
  },
  "example": "{\"title\":\"Deploy approval\",\"nodes\":[{\"id\":\"a\",\"shape\":\"oval\",\"name\":\"Push\"},{\"id\":\"d\",\"shape\":\"diamond\",\"name\":\"Risky?\",\"rank\":1,\"focal\":true}],\"edges\":[{\"from\":\"a\",\"to\":\"d\",\"label\":\"pass\"}]}"
}
```

## arch
```json
{
  "input": "JSON spec {title, sub, nodes[], edges[]}",
  "writes": "py graph.py arch SPEC.json -o OUT.html",
  "node": {
    "id": "unique",
    "layer": "row int (default 0)",
    "name": "service",
    "sub": "Lang:port e.g. Go:8080",
    "tag": "UI|API|SVC|STORE",
    "focal": "bool, max 2"
  },
  "edge": {
    "from": "id",
    "to": "id",
    "label": "VERB",
    "proto": "https=blue arrow",
    "async": "dashed bool",
    "focal": "bool"
  },
  "rules": [
    "blue=HTTP/API, dashed=async, coral=focal",
    "tech sublabels in mono, names in sans"
  ],
  "budgets": {
    "nodes": 9,
    "edges": 12,
    "layers": 6,
    "over": "one view per C4 level"
  }
}
```

## seq
```json
{
  "input": "JSON spec {title, sub, actors[], messages[]}",
  "writes": "py graph.py seq SPEC.json -o OUT.html",
  "actor": {
    "id": "unique",
    "name": "label",
    "sub": "tech/mono sub",
    "tag": "USER|UI|GATEWAY|SVC|STORE",
    "focal": "bool, max 2"
  },
  "message": {
    "from": "id",
    "to": "id",
    "label": "Call name/payload",
    "proto": "https/grpc",
    "reply": "bool dashed",
    "async": "bool dashed",
    "focal": "bool"
  },
  "rules": [
    "solid=sync, dashed=reply/async, blue=http, coral=focal",
    "top-down sequence order",
    "max 6 lifelines"
  ],
  "budgets": {
    "actors": 6,
    "messages": 16,
    "focal": 2,
    "over": "split into sub-sequences"
  },
  "example": "{\"title\":\"Auth handshake\",\"actors\":[{\"id\":\"u\",\"name\":\"User\"},{\"id\":\"api\",\"name\":\"API\",\"focal\":true}],\"messages\":[{\"from\":\"u\",\"to\":\"api\",\"label\":\"login\"}]}"
}
```

## schema
```json
{
  "input": "JSON spec {title, sub, tables[], relations[]}",
  "writes": "py graph.py schema SPEC.json -o OUT.html",
  "table": {
    "id": "unique",
    "name": "table_name",
    "tag": "AUTH|CORE|AUDIT",
    "focal": "bool, max 2",
    "columns": [
      {
        "name": "col",
        "type": "data_type",
        "pk": "bool",
        "fk": "bool",
        "unique": "bool"
      }
    ]
  },
  "relation": {
    "from": "id",
    "from_col": "col",
    "to": "id",
    "to_col": "col",
    "label": "1:N|1:1|M:N",
    "focal": "bool"
  },
  "rules": [
    "PK coral badge, FK blue badge, columns in mono, types muted",
    "orthogonal elbow routing",
    "max 6 tables per view"
  ],
  "budgets": {
    "tables": 6,
    "relations": 10,
    "columns_per_table": 12,
    "over": "split by bounded context"
  },
  "example": "{\"title\":\"Users & Teams\",\"tables\":[{\"id\":\"u\",\"name\":\"users\",\"columns\":[{\"name\":\"id\",\"type\":\"uuid\",\"pk\":true}]}],\"relations\":[]}"
}
```

## bar
```json
{
  "input": "CSV with header row. One categorical column and one numeric column.",
  "writes": "py graph.py bar DATA.csv --cat CAT --val VAL -o OUT.html",
  "options": {
    "--cat": "category column",
    "--val": "numeric value column",
    "--group": "subgroup column",
    "--sort": "none|asc|desc",
    "--orientation": "v|h",
    "--unit": "unit string"
  },
  "budgets": {
    "bars": 24,
    "categories": 12,
    "over": "sort top-N + other"
  },
  "rules": [
    "bar charts must start at zero",
    "direct value labels in mono",
    "subtle grid aligned to ticks"
  ],
  "example": "py graph.py bar examples/bar_latency.csv --cat service --val p99_latency_ms --unit ms -o out/bar.html"
}
```

## line
```json
{
  "input": "CSV with header row. Continuous/temporal X column and numeric Y column.",
  "writes": "py graph.py line DATA.csv --x X --y Y -o OUT.html",
  "options": {
    "--x": "x column (numeric or timestamp)",
    "--y": "y column (numeric)",
    "--group": "series column",
    "--xlabel/--xunit/--ylabel/--yunit": "axis labels"
  },
  "budgets": {
    "series": 6,
    "points_per_series": 200,
    "over": "downsample or facet"
  },
  "rules": [
    "non-negative data floors at 0",
    "Okabe-Ito series colors",
    "subtle area fill under lines"
  ],
  "example": "py graph.py line examples/line_throughput.csv --x timestamp --y rps --group service -o out/line.html"
}
```

## export
```json
{
  "input": "Receipt OUT.graph.json written beside every render.",
  "writes": "py graph.py export OUT --to png|pdf|svg [--layout figure|wide|slide|social] [--width 1600] [-o FILE]",
  "rules": [
    "svg works everywhere, zero deps (re-render from receipt)",
    "layouts figure/wide/slide/social apply to scatter; other types export single layout",
    "png/pdf need a rasterizer: cairosvg + system Cairo (GTK runtime on Windows), else headless Chromium/Edge for PNG"
  ],
  "budgets": {
    "png_width_default": 1600
  },
  "example": "py graph.py export out/scatter --to svg --layout social"
}
```

## doc
```json
{
  "input": "Markdown document containing ```graph:<type> fenced blocks.",
  "writes": "py graph.py doc DOC.md [--out-dir assets] [--check]",
  "behavior": "Parses and compiles embedded diagram specs into standalone SVGs in assets/, updates doc links"
}
```

## monitor
```json
{
  "input": "Repository working tree or git history.",
  "writes": "py graph.py monitor [--base <ref>] [--ci] [--map graph.monitor.json]",
  "behavior": "Scans code changes for data models, routes, and migrations without corresponding diagram updates; outputs JSON drift report. With --map, extracts each changed file and semantically diffs against its spec (no diff = no drift, even if files changed).",
  "map_format": "{\"mappings\": [{\"code\": \"models/*.py\", \"spec\": \"docs/schema.graph.json\", \"kind\": \"schema\", \"domain\": \"database\"}]}"
}
```

## extract
```json
{
  "input": "Code source file (.sql DDL, Python ORM model, FastAPI routes).",
  "writes": "py graph.py extract schema|routes SOURCE_FILE -o SPEC.json",
  "behavior": "Reverse-extracts architecture or database schema diagram specs directly from source code using AST/token parsing"
}
```

## sync
```json
{
  "input": "Same inputs as monitor (--path, --base, --map).",
  "writes": "py graph.py sync --map graph.monitor.json [--docs ARCH.md] [--commit]",
  "behavior": "Auto-fix bot: for each mapping-backed drift entry runs extract -o spec, validates, recompiles --docs, audits emitted SVGs. Default touches only the working tree; --commit creates a LOCAL commit (never pushes). Exit 1 if anything is left undone. Heartbeat: cron `0 6 * * * cd repo && py graph.py sync --map graph.monitor.json --commit`, Windows Task Scheduler, or an Antigravity cron//goal task."
}
```


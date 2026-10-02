# graph-engine skill

Draw figures from data and specs with graphflow (`graph.py`, Python 3 standard library).

If `graph.py` is not on the machine, run the `graphflow-install` skill first.
Invoke the installed file by its absolute path: `py -3 <path>` on Windows, `python3 <path>` elsewhere.

## Trigger

Any request to chart, plot, diagram, map a codebase, visualize a schema,
flowchart logic, or sequences — or files matching `*.graph.json`, `graph:*` fences.

## The loop (in order, chain on exit codes)

```
1. describe  py graph.py describe <scatter|flow|arch|seq|schema|bar|line|geo>  # exact contract
2. draft     write the spec (JSON) or pick CSV columns
3. validate  py graph.py validate SPEC.json|DATA.csv [--type bar|line]     # exit 0 required
4. render    py graph.py <type> ... -o <out>.html                          # + .svg + .graph.json
5. audit     py graph.py audit <out>.svg                                   # exit 0 required
6. export    py graph.py export <out> --to png|pdf|svg [--layout ...]       # svg: no deps
```

Never hand-edit SVG. Fix the spec/flags, re-render. `infer` proposes a scatter
spec from any CSV. Full command recipes: `SKILL.md` at engine root.

## Chart choice (10 seconds)

Numbers → `scatter` (2 continuous), `bar` (categories), `line` (trend), `geo` (lat/lon);
structure → `arch` (services), `schema` (tables), `seq` (messages), `flow` (branches).
Full 75-type taxonomy: `references/taxonomy.md`. Schemas: `references/schemas.md`.

## Taste (hard rules)

Shape carries type (oval=start/end, rect=step, diamond=decision ≤3 exits);
blue `#2e5aa8`=HTTP only; dashed=async; coral `#eb6c36`=max 2 focal;
orthogonal elbows; budgets in `references/visual_grammar.md`.
Title and subtitle are drawn on the SVG. The HTML page is that drawing plus Copy SVG, Export SVG, and Export PNG; print hides the bar. Geo draws a built-in coastline under the points.

## Docs & drift

`graph doc DOC.md` compiles fenced `graph:<type>` blocks (validates first,
idempotent links, `--check` for CI). `graph extract schema|routes SRC` builds
specs from code. `graph monitor --map graph.monitor.json [--ci]` flags drift.
Helpers: `scripts/check_drift.py`, `scripts/extract_schema.py`.

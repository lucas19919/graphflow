# Graph Taxonomy — CLI Graphing Tool
Source: session 2026-10-02. Canonical list for `graph/` CLI.

## A. Statistical / Data Plots — from data files
| # | Type | Shows | Use case | Domain | CLI needs |
|---|------|-------|----------|--------|-----------|
| 1 | Scatter plot | 2 vars correlation | dose vs expression | science, ML | title, x/y labels, ticks, marker shape/color/size, legend, trendline, log scales, error bars |
| 2 | Bubble chart | 3 vars (size=3rd) | pop vs GDP sized by CO2 | economics | size legend, alpha |
| 3 | Beeswarm | 1 var dot per item | test scores per class | stats, bio | jitter, grouping |
| 4 | Line chart | trend over continuous x | latency over time | ops, finance | multi-series, markers, fill, log-y |
| 5 | Step chart | piecewise-constant | feature flag state | infra | sharp/smooth corners |
| 6 | Slopegraph | change between 2 states | before/after coverage | consulting | label both ends |
| 7 | Bump chart | rank movement | framework popularity | tech radar | rank inversion |
| 8 | Ridgeline | distributions per series | latency per service | SRE | overlap, bandwidth |
| 9 | Bar chart (V/H) | categorical comparison | requests per endpoint | general | grouped/stacked, thickness, padding, sort, value labels |
| 10 | Grouped + Stacked bar | sub-categories | errors by service x type | ops | totals, legend |
| 11 | Dumbbell / Lollipop | delta between 2 points | p50 vs p99 | performance | connector line |
| 12 | Waterfall / Bridge | start->end via contributions | budget bridge | finance | subtotals, +/- colors |
| 13 | Histogram | binned distribution | request sizes | stats | bins, KDE overlay |
| 14 | Box plot | quartiles + outliers | build time per runner | QA | grouping, outliers |
| 15 | Violin plot | KDE + box | response shape | stats | split violins |
| 16 | Strip / Jitter | raw points per category | flaky tests | testing | alpha |
| 17 | Pie / Donut | part-of-whole few slices | language share | exec | % labels |
| 18 | Waffle | proportion 10x10 grid | coverage 87% | dashboards | grid icons |
| 19 | Treemap | hierarchical sizes | disk/bundle size | infra | nesting, 2nd metric color |
| 20 | Sunburst / Icicle | hierarchical part-of-whole | dep size tree | packaging | drill-down |
| 21 | Heatmap / Matrix | 2D values by color | correlation matrix | ML | diverging map, annotations |
| 22 | Calendar heatmap | day intensity | deploys per day | devprod | year layout |
| 23 | Contour / Surface / 3D | z(x,y) | loss landscape | ML, geo-science | levels, palette |
| 24 | Radar / Spider | 3-5 criteria | service scores | arch review | 5 axes max, 1 focal |
| 25 | Polar cyclic | cyclic categories | traffic by hour | ops | angle=category |
| 26 | Candlestick / OHLC | open/high/low/close | prices, batch timings | finance | bull/bear colors |
| 27 | Status grid | health cells | host x check | dashboards | key->color map |
| 28 | Errorbar / Forest | estimate + CI | benchmarks | science | CI level |
| 29 | QQ / Residual | model diagnostics | normality check | ML | reference line |
| 30 | Volcano plot | -log10(p) vs log2FC | diff expression | bio | top-N labels |
| 31 | Sankey | flow width=amount | CDN->service->DB | data-eng | 3 stages max |
| 32 | Streamgraph | stacked flows over time | traffic share | analytics | baseline |
| 33 | Funnel / Pyramid | conversion drop-off | signup->paid | product | % remaining |

## B. Network / Relationship — from code or data
| # | Type | Shows | Use case | Domain |
|---|------|-------|----------|--------|
| 34 | Dependency graph (DAG) | depends-on, cycles | imports, terraform graph | software |
| 35 | Force-directed / community | Louvain clusters | microservice coupling | architecture |
| 36 | Radial | center=most-connected | core libs | review |
| 37 | Tree / Dendrogram | parent->children | file/call tree | docs |
| 38 | Nested / Containment | containment hierarchy | monorepo map | architecture |
| 39 | Flow / Execution-order | bootstrap order | startup seq | onboarding |
| 40 | Knowledge / Entity graph | entities+relations | symbols | code intel |

## C. Software Architecture — from codebases (hero)
| # | Type | Shows | Use case | CLI needs |
|---|------|-------|----------|-----------|
| 41 | C4 L0 Context | black box + actors | stakeholder deck | person shapes |
| 42 | C4 L1 Container | services+DBs+queues | onboarding | tech labels, async dashed |
| 43 | C4 L2 Component | classes in container | PR review | ports |
| 44 | C4 L3 Code/Process | runtime lifecycle | debug auth | sequence overlay |
| 45 | UML Class | inheritance/composition | API design | 7 classes max |
| 46 | Deployment | zones/hosts/ports | go-live | 3 zones / 6 nodes |
| 47 | Layer stack | abstractions | OSI, medallion | 6 layers max |
| 48 | DP Integration | sources->core->consumers | data platform | source icons |
| 49 | High-level / IT current-state | legacy by dept | modernization before-shot | dept grouping |
| 50 | Database schema | tables, FKs, indexes | migration | 6 tables / 8 cols shown / 8 rels (engine budgets, DESCRIBE=schema) |
| 51 | ER / Data model | entities+relations | domain modeling | crow's foot |
| 51 | ER / Data model | entities+relations | domain modeling | crow's foot |
| 52 | Wardley map | value vs evolution | build-vs-buy | 9 comps / 2 moves |

## D. Logic / Process / State — from logic specs
| # | Type | Use case | Domain |
|---|------|----------|--------|
| 53a | Flowchart / Programmablaufplan (PAP, DIN 66001 / ISO 5807) | Oval start/end (rx=20), rect action, diamond decision ≤3 exits, dot merge; top-down, Yes=right No=down, every branch labeled | deploy approval, algorithm, support triage | informatik / ops — shape carries type not color, coral only on happy-path or key decision |
| 53b | Flowsheet / Process flowsheet | continuous process steps with inputs/outputs per stage | ETL pipeline, chem/process, stage framework | data-eng / process — same primitives as flowchart, emphasis on handoffs |
| 53c | Decision flowsheet / Entscheidungs-Flussdiagramm | diamond-heavy branching, nested diamonds for 4+ exits | onboarding routing, "Should I…?", access rules | informatik / product — paired policy-evaluation traces, first-divergence highlight |
| 54 | Swimlane | handoffs dev->review->deploy | process |
| 55 | Sequence | User->API->Auth->DB | backend — 6 actors / 16 msgs, solid=sync dashed=reply/async, blue=http |
| 56 | State machine | new->paid->shipped | checkout |
| 57 | BPMN | auditable process | enterprise |
| 58 | Decision tree | ML splits | data science |
| 59 | Fishbone | root-cause grouped | incident — 6x3 |
| 60 | Loop / Flywheel | feeds-first + hub | growth |
| 61 | Kanban | WIP + blocked | delivery |
| 62 | Gantt | tasks on timeline | planning — 12 tasks |
| 63 | Timeline | events in time | roadmap |
| 64 | User journey | stages + feeling | product |
| 65 | Story map | backbone->releases | agile |
| 66 | Org chart | ownership | team — 4 deep / 12 nodes |

## E. Geospatial — from GeoJSON/shapefiles
| # | Type | Use case | Stack |
|---|------|----------|-------|
| 67 | Point / Cluster map | PoPs, incidents lat/lon | kepler.gl, deck.gl |
| 68 | Choropleth | region by metric | geopandas + mapclassify |
| 69 | Heat / Density | request density | deck.gl hexagon |
| 70 | Flow / OD map | zone-to-zone traffic | deck.gl arc |
| 71 | Raster / Terrain | DEM hillshade | GMT, QGIS headless |
| 72 | Print layout | map+legend+scalebar PDF | qgis layout export-pdf |

## F. Comparison
| # | Type | Use case |
|---|------|----------|
| 73 | Quadrant 2x2 | effort vs impact |
| 74 | Venn (max 3) | overlap |
| 75 | Bar+Line combo | revenue + margin |

## Global rules
- If table does it, don't draw. >9 nodes => split overview+detail.
- Stunning arch: orthogonal elbows r=8, no diagonals, 6-10px label gap + mask, >=12px fan, max 1-2 coral focal, Geist sans + Mono ports.

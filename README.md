# diagonaldiagrams

Diagrams and charts your agent can draw, and check before it shows you. One command takes a short spec, Mermaid, or a CSV, lays it out, draws an SVG, and audits the drawing for labels on labels, arrows through boxes, and text that spills. The program is `graph.py`: one file, Python 3 standard library only.

**[Try it in the browser](https://lucas19919.github.io/diagonaldiagrams/)**: the real engine, running locally in your browser, nothing to install.

![A fourteen-service checkout platform, drawn and audited by diagonaldiagrams](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/checkout.svg)

## Install

Claude Code, as a plugin. This adds the drawing skill:

```text
/plugin marketplace add lucas19919/diagonaldiagrams
/plugin install diagonaldiagrams@diagonaldiagrams
```

Any agent, as a command. This puts `diagonaldiagrams` on PATH:

```bash
pip install git+https://github.com/lucas19919/diagonaldiagrams
```

As MCP tools (`render`, `describe`, `validate`, `audit`, `export`, `infer`):

```bash
claude mcp add --scope user diagonaldiagrams -- diagonaldiagrams mcp
```

Or clone it and run `py -3 graph.py describe` (Windows) or `python3 graph.py describe`. Agents can follow [`.agents/skills/diagonaldiagrams-install/SKILL.md`](.agents/skills/diagonaldiagrams-install/SKILL.md) to install, and [`.agents/skills/graph-engine/SKILL.md`](.agents/skills/graph-engine/SKILL.md) to draw.

## One command

```text
diagonaldiagrams mermaid flow.mmd -o out/flow.svg
{"ok": true, "svg": "out/flow.svg", "html": "out/flow.html", "receipt": "out/flow.graph.json", "items": 9,
 "layout": ["row 1: Agent writes a spec", "row 2: Check the spec", "row 3: Valid? (decision)", ...]}
```

It checks the input, draws, audits the drawing, and prints one line of JSON. `ok: false` comes with errors, each with a `fix`; change the input and run it again. `layout` describes the drawn structure, so an agent can confirm it without looking at a picture.

The audit reads the finished SVG: labels on labels, labels too wide for their box or off the canvas, boxes on boxes, arrows through a box or across a label, two arrows on one line, and nodes inside a frame they don't belong to. When it finds a problem it can fix, the layout repairs itself. It reads any SVG, so `diagonaldiagrams audit` also checks a figure an agent wrote by hand.

## Input

| Command | Input | Draws |
| --- | --- | --- |
| `mermaid` | Mermaid `flowchart`, `sequenceDiagram`, or `erDiagram` | Picks `flow`, `seq`, or `schema` |
| `flow` | JSON | A decision flow, with frames (`groups`) and icons |
| `arch` | JSON | Services and the calls between them |
| `seq` | JSON | A sequence of messages |
| `schema` | JSON | Tables and their relations |
| `bar`, `line`, `scatter` | CSV | Comparisons, trends, relationships |
| `geo` | CSV or GeoJSON | Places on a built-in coastline |
| `chart <type>` | CSV or JSON | About 60 more: sankey, gantt, heatmap, treemap, box, radar, math, ... |

`describe <type>` prints the contract for any type. Long names wrap inside their boxes. Loops are drawn back up the outside. Built-in icons (`describe icons`) cover users, databases, servers, queues, and more; in Mermaid, write `fa:fa-database`.

## Output

| File | Contents |
| --- | --- |
| `OUT.svg` | The drawing. Title and subtitle are on the figure; points and bars have hover tooltips. |
| `OUT.html` | The same figure, plus Copy SVG, Export SVG, and Export PNG. |
| `OUT.graph.json` | The receipt. `export` redraws from it. |

`export OUT --to png|pdf|svg|drawio|excalidraw` writes other formats. draw.io and Excalidraw exports keep boxes, frames, and the routed arrows attached to their boxes, so a person can open the figure and drag things around. PNG and PDF use cairosvg if installed, else headless Edge or Chrome.

## Measured

The same three tasks, done by fresh agents with diagonaldiagrams and by writing the SVG directly. Total tokens processed across the agent's calls:

| Task | Hand-written SVG | diagonaldiagrams | Calls |
| --- | --- | --- | --- |
| Flowchart, 11 steps | 902k | **433k** | 13 → 7 |
| Line chart, 3 series | 622k | **295k** | 10 → 5 |
| Sequence, 6 actors | 757k | **427k** | 11 → 7 |

Most of an agent's tokens are its own instructions, re-read on every call. The saving comes from fewer calls: the agent writes a short spec and trusts the verdict instead of screenshotting to check.

## Gallery

Every figure was drawn from a file in [`examples/`](examples) and passed its own audit. Rebuild them with `py -3 scripts/build_site.py`.

![How a figure is made](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/how-it-works.svg)

![Checkout platform with frames](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/checkout-grouped.svg)

![Checkout request, a sequence diagram](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/sequence.svg)

![Shop data model](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/data-model.svg)

![Signups line chart](https://raw.githubusercontent.com/lucas19919/diagonaldiagrams/master/docs/gallery/signups.svg)

## Tests

```bash
py -3 tests_smoke.py
```

Exit 0 means every check passed.

## License

[MIT](LICENSE)

<!-- mcp-name: io.github.lucas19919/diagonaldiagrams -->


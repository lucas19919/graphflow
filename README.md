# graphflow

A command-line tool that draws a figure from a CSV or a JSON spec. The program is `graph.py`: Python 3, standard library only, no install.

```
py -3 graph.py describe flow
py -3 graph.py validate examples/show_canary.json
py -3 graph.py flow examples/show_canary.json -o out/canary.html
py -3 graph.py audit out/canary.svg
py -3 graph.py export out/canary.html --to png -o out/canary.png
```

Each render writes the HTML page, the same drawing as a `.svg`, and a `.graph.json` receipt. `validate` has to pass before the render. `audit` checks the SVG after it. The page has Copy SVG, Export SVG, and Export PNG. Print hides that bar.

Types that draw: `flow`, `arch`, `seq`, `schema`, `bar`, `line`, `scatter`, `geo`.

SVG export needs nothing else. PNG and PDF use cairosvg when it imports, otherwise headless Edge or Chrome.

```
py -3 tests_smoke.py
```

The call counts and latencies in the gallery are made up.

![Canary promotion](gallery/canary.png)

![Retrieval path](gallery/retrieval.png)

![Tool loop](gallery/toolloop.png)

![Training store](gallery/store.png)

![Context cost](gallery/latency.png)

![North Sea calls](gallery/ports.png)

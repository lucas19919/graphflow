#!/usr/bin/env python3
"""Build the GitHub Pages site in docs/: render the gallery from examples/ with graph.py itself,
and copy graph.py next to the page so the in-browser playground runs the same engine.

    py -3 scripts/build_site.py

Every figure must pass the audit, or the build stops: the site never shows a figure the engine
would reject.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = os.path.join(HERE, "graph.py")
DOCS = os.path.join(HERE, "docs")
OUT = os.path.join(DOCS, "gallery")

# (file name, command line after graph.py, caption)
FIGURES = [
    ("how-it-works", ["mermaid", "examples/how_it_works.mmd"], "How a figure is made: written in Mermaid, loops drawn back up the outside."),
    ("checkout", ["arch", "examples/checkout_platform.json"], "Fourteen services, sync and async: every arrow on its own path."),
    ("checkout-grouped", ["arch", "examples/checkout_groups.json"], "The same system with frames: each holds only its members."),
    ("deploy", ["flow", "examples/flow_decision.json"], "A decision flow: yes goes right, retry loops round the outside."),
    ("sequence", ["mermaid", "examples/checkout_sequence.mmd"], "A request over time, from a Mermaid sequenceDiagram."),
    ("data-model", ["mermaid", "examples/shop_er.mmd"], "A data model from a Mermaid erDiagram."),
    ("icons", ["mermaid", "examples/icons.mmd"], "Built-in icons, from Mermaid's fa: names."),
    ("signups", ["line", "examples/signups.csv", "--x", "month", "--y", "signups", "--group", "product",
                 "--title", "Atlas more than doubled while Beacon declined",
                 "--subtitle", "Monthly signups per product, January to June 2026",
                 "--xlabel", "Month", "--ylabel", "Signups per month"], "A line chart labels each series at its end."),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    shown = []
    for name, args, caption in FIGURES:
        target = os.path.join(OUT, name + ".svg")
        p = subprocess.run([sys.executable, GRAPH] + args + ["-o", target], capture_output=True, text=True, cwd=HERE)
        try:
            rep = json.loads(p.stdout)
        except ValueError:
            rep = {"ok": False, "errors": [{"msg": (p.stdout + p.stderr)[-300:]}]}
        if not rep.get("ok"):
            sys.exit(f"{name}: {rep.get('errors')}")
        for extra in (".html", ".graph.json"):
            path = os.path.join(OUT, name + extra)
            if os.path.exists(path):
                os.remove(path)
        shown.append({"file": "gallery/" + name + ".svg", "caption": caption, "source": args[1]})
        print("ok", name)
    with open(os.path.join(DOCS, "gallery.json"), "w", encoding="utf-8") as f:
        json.dump(shown, f, indent=1)
    shutil.copy(GRAPH, os.path.join(DOCS, "graph.py"))
    print(f"{len(shown)} figures, graph.py copied for the playground")


if __name__ == "__main__":
    main()

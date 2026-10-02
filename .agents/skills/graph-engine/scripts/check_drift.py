#!/usr/bin/env python3
"""Standalone drift gate: exits 1 when diagrams are stale. Pure stdlib.
Usage:  py check_drift.py [--map graph.monitor.json] [--path .] [--ci]
Delegates to `graph.py monitor`; fails loudly if the engine is missing.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.normpath(os.path.join(HERE, "..", "..", "..", "graph.py"))


def main(argv):
    if not os.path.exists(GRAPH):
        print(f"check_drift: engine not found at {GRAPH}", file=sys.stderr)
        raise SystemExit(2)
    cmd = [sys.executable, GRAPH, "monitor", *argv]
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(p.stdout, end="")
    if p.stderr:
        print(p.stderr, end="", file=sys.stderr)
    raise SystemExit(p.returncode)


if __name__ == "__main__":
    main(sys.argv[1:])

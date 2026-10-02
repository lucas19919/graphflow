#!/usr/bin/env python3
"""Standalone schema extractor: SQL DDL / Python ORM -> graph schema spec.
Usage:  py extract_schema.py models.sql [-o schema.graph.json]
Delegates to `graph.py extract schema`.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.normpath(os.path.join(HERE, "..", "..", "..", "graph.py"))


def main(argv):
    if not os.path.exists(GRAPH):
        print(f"extract_schema: engine not found at {GRAPH}", file=sys.stderr)
        raise SystemExit(2)
    if not argv:
        print("usage: py extract_schema.py SOURCE.sql [-o SPEC.json]", file=sys.stderr)
        raise SystemExit(2)
    cmd = [sys.executable, GRAPH, "extract", "schema", *argv]
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(p.stdout, end="")
    if p.stderr:
        print(p.stderr, end="", file=sys.stderr)
    raise SystemExit(p.returncode)


if __name__ == "__main__":
    main(sys.argv[1:])

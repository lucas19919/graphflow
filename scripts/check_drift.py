#!/usr/bin/env python3
"""Architecture drift gate for git hooks or CI pipelines.
Usage:
  py scripts/check_drift.py [--ci] [--base HEAD~1]
"""
import subprocess, sys

def main():
    cmd = [sys.executable, "graph.py", "monitor"] + sys.argv[1:]
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()

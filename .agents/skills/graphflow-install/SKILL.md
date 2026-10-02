---
name: graphflow-install
description: >
  Install graphflow, the graphing library for agents. Clones
  https://github.com/lucas19919/graphflow, checks that graph.py runs, and
  copies the graph-engine drawing skill into the user skills folder.
  Use when the user says install graphflow, set up graphflow, add the
  graphing library, or runs /graphflow-install.
license: MIT
compatibility: Requires git and Python 3
metadata:
  short-description: Install the graphflow agent graphing library
---

# Install graphflow

Graphflow is a graphing library for agents. Install is a clone and a check. There is no pip package.

The drawing contract is the `graph-engine` skill in the clone. This skill only puts that library on the machine.

## Steps

1. Find Python 3. On Windows run `py -3 --version`. Elsewhere run `python3 --version`. Stop if Python 3 is missing, and say so. Do not install Python unless the user asks.

2. Pick a stable directory outside the current project.
   - Windows: `$env:USERPROFILE\.graphflow`
   - Elsewhere: `$HOME/.graphflow`
   If `<dir>/graph.py` is already there, keep that checkout. Do not clone a second copy.

3. If the directory is missing, clone it.

   ```bash
   git clone https://github.com/lucas19919/graphflow.git <dir>
   ```

   If the directory exists and has no `graph.py`, stop. Tell the user what is in it.

4. Check the library. Run `<python> <dir>/graph.py describe`. Require exit 0. The JSON must list `flow`, `arch`, `seq`, `schema`, `bar`, `line`, `scatter`, and `geo`.

5. Copy `<dir>/.agents/skills/graph-engine` to the user skills folder so later sessions can draw.
   - Grok: `~/.grok/skills/graph-engine`
   - If a `graph-engine` skill is already there, leave it. Tell the user both paths.

6. Report the absolute path of `<dir>/graph.py`. Later draws use that path: `py -3 <path>` on Windows, `python3 <path>` elsewhere. Point the user at the `graph-engine` skill for the draw loop.

Run `<python> <dir>/tests_smoke.py` only when the user asks for a full check.

## Leave alone

Do not edit `graph.py`. Do not hand-edit an SVG the library wrote. Do not run `sync --commit` as part of install.

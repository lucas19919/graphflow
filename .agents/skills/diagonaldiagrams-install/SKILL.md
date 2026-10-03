---
name: diagonaldiagrams-install
description: >
  Install diagonaldiagrams, the graphing library for agents. Clones
  https://github.com/lucas19919/diagonaldiagrams, checks that graph.py runs, and
  copies the graph-engine drawing skill into the user skills folder.
  Use when the user says install diagonaldiagrams, set up diagonaldiagrams, add the
  graphing library, or runs /diagonaldiagrams-install.
license: MIT
compatibility: Requires git and Python 3
metadata:
  short-description: Install the diagonaldiagrams agent graphing library
---

# Install diagonaldiagrams

diagonaldiagrams is a graphing library for agents. This skill installs it as a clone plus a check, because the clone also carries the drawing skill. `pip install git+https://github.com/lucas19919/diagonaldiagrams` is the other route: it puts a `diagonaldiagrams` command on PATH, but no skill.

The drawing contract is the `graph-engine` skill in the clone. This skill only puts that library on the machine.

## Steps

1. Find Python 3. On Windows run `py -3 --version`. Elsewhere run `python3 --version`. Stop if Python 3 is missing, and say so. Do not install Python unless the user asks.

2. Pick a stable directory outside the current project.
   - Windows: `$env:USERPROFILE\.diagonaldiagrams`
   - Elsewhere: `$HOME/.diagonaldiagrams`
   If `<dir>/graph.py` is already there, keep that checkout. Do not clone a second copy.

3. If the directory is missing, clone it.

   ```bash
   git clone https://github.com/lucas19919/diagonaldiagrams.git <dir>
   ```

   If the directory exists and has no `graph.py`, stop. Tell the user what is in it.

4. Check the library. Run `<python> <dir>/graph.py describe`. Require exit 0. The JSON must list `flow`, `arch`, `seq`, `schema`, `bar`, `line`, `scatter`, `geo`, `heatmap`, and `sankey`.

5. Copy `<dir>/.agents/skills/graph-engine` to the user skills folder of the agent you are, so later sessions can draw.
   - Claude Code: `~/.claude/skills/graph-engine`
   - Grok: `~/.grok/skills/graph-engine`
   - Another agent: its user skills folder, if it has one. Otherwise skip this step and say so.
   - If a `graph-engine` skill is already there, leave it. Tell the user both paths.

6. Optional, only if the user wants diagonaldiagrams as tools instead of shell commands: register the MCP server.
   Claude Code: `claude mcp add --scope user diagonaldiagrams -- <python> <dir>/graph.py mcp`, where `<python>` is `py -3` on Windows and `python3` elsewhere.

7. Report the absolute path of `<dir>/graph.py`. Later draws use that path: `py -3 <path>` on Windows, `python3 <path>` elsewhere. Point the user at the `graph-engine` skill for the draw loop.

To update later: `git -C <dir> pull`.

Run `<python> <dir>/tests_smoke.py` only when the user asks for a full check.

## Leave alone

Do not edit `graph.py`. Do not hand-edit an SVG the library wrote. Do not run `sync --commit` as part of install.

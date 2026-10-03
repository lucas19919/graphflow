# Publishing

Every step here publishes something under your name, so each one is yours to run. The order matters:
the MCP registry checks PyPI, and PyPI needs the version on GitHub first.

## 0. Before any release

```bash
py -3 tests_smoke.py              # exit 0
py -3 scripts/build_site.py       # every gallery figure passes its audit
```

Keep the version the same in `graph.py` (`__version__`), `.claude-plugin/plugin.json`, and `server.json` (twice).
The tests check the first two.

## 1. GitHub: push, and turn on Pages

```bash
git push origin master
gh api repos/lucas19919/diagonaldiagrams/pages -X POST -f "source[branch]=master" -f "source[path]=/docs"
```

The site is then at https://lucas19919.github.io/diagonaldiagrams/ (a minute or two after the first build).
Pages is free for public repositories. After that, the Claude Code plugin and `pip install git+...` work for anyone.

## 2. PyPI

The name `diagonaldiagrams` was free on 2026-10-03. You need a PyPI account and an API token.

```bash
py -3 -m pip install build twine
py -3 -m build
py -3 -m twine upload dist/*
```

Then `pip install diagonaldiagrams` and `uvx diagonaldiagrams mcp` work.

## 3. Official MCP registry

Needs step 2: the registry reads the README on PyPI and looks for the `mcp-name:` line at the bottom of README.md.

```bash
mcp-publisher login github
mcp-publisher validate            # checks server.json against the current schema
mcp-publisher publish
```

Install `mcp-publisher` from https://github.com/modelcontextprotocol/registry/releases. If `validate` complains
about a field, `mcp-publisher init` writes a fresh server.json in the current schema; copy the fields over.

## 4. Directories that read the registry or the repo

- **Smithery** (smithery.ai): add the GitHub repo from its "add server" page.
- **Glama** (glama.ai/mcp/servers): indexes public MCP repos; claim it from the server page.
- **awesome-mcp-servers** (github.com/punkpeye/awesome-mcp-servers): one line in the README under a fitting
  section, as a pull request.
- **Anthropic's plugin directory**: submit the plugin from the Claude Code docs' "publish a plugin" page.

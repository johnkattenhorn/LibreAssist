# Status

## Where this is

A fork of NikolaiRadke/LibreAssist. The upstream extension (`src/`, the `.oxt`) is
unchanged. The fork adds `calc-tools/`: an MCP server that gives an agent outside
LibreOffice tools on the spreadsheet a person has open in Calc, over a named pipe. The
tools and how to install are in `calc-tools/README.md`; the list the server really
offers is `tests/unit/test_server.py`.

Run it with `calc-tools/bin/calc-tools` (stdio). `CALC_TOOLS_PIPE` names the pipe
LibreOffice accepts on, default `calc-tools`. With Claude Code:
`claude mcp add calc -- <checkout>/calc-tools/bin/calc-tools`.

## Gate

From `calc-tools/`:

```sh
uv sync --locked
uv run --locked ruff check && uv run --locked ruff format --check \
  && uv run --locked pyright && uv run --locked pytest \
  && uv run --locked pytest -m integration --force-enable-socket \
  && shfmt -f . | xargs -r shellcheck && shfmt -d .
```

The integration suite needs `soffice` and `pdftoppm` on PATH. The venv must see the
system's `uno` module: create it with
`uv venv --system-site-packages --python /usr/bin/python3` before the first `uv sync`.

## What is open

- Branches not merged: `git branch --no-merged main`
- The root README, which is upstream's, does not mention `calc-tools`.
- Upstream's reload after an edit reads payload keys nothing sets
  (`src/pythonpath/libreassist/ui/events.py`, `frame`, `isWriter`, `backupPath`). Read,
  not run.

## What is next

Use the tools on real work and let what is missing decide the next tool. A sidebar chat that uses the same tools comes after that, and is the only part that
needs the extension.

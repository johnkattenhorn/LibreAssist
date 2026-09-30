# calc-tools

An MCP server that lets an AI agent work in the spreadsheet you have open in
LibreOffice Calc. The agent reads what you see, including edits you have not saved. When
it writes, the change appears in your window as one undo step. It cannot save or close
the spreadsheet.

It runs outside LibreOffice and connects over a named pipe, so only programs running as
you on the same machine can reach it. The LibreAssist extension in this repository is
not needed.

## Requirements

- LibreOffice with its Python bindings (`uno`), and `soffice` on PATH
- Python 3.14 or later, and it has to be the interpreter your LibreOffice's `uno` module
  was built for (on most Linux systems, the system Python)
- [uv](https://docs.astral.sh/uv/)
- `pdftoppm` from poppler, for the `render` tool

## Install

```sh
cd calc-tools
uv venv --system-site-packages --python /usr/bin/python3
uv sync --locked
```

`--system-site-packages` is what lets the environment import `uno`, which ships with
LibreOffice and is not on PyPI.

## Connect an agent

With Claude Code:

```sh
claude mcp add calc -- /path/to/LibreAssist/calc-tools/bin/calc-tools
```

Any MCP client that starts a stdio server works the same way: point it at
`bin/calc-tools`.

Then ask the agent to open a spreadsheet. The `open_document` tool opens the file in a
normal LibreOffice window and tells LibreOffice to accept connections. If you would
rather start LibreOffice yourself:

```sh
soffice --accept='pipe,name=calc-tools;urp;' budget.ods
```

Set `CALC_TOOLS_PIPE` to use a different pipe name.

## Tools

| Tool | What it does |
|---|---|
| `documents` | Lists open spreadsheets with their sheets, the active sheet, the selection and whether there are unsaved changes |
| `open_document` | Opens a file in a LibreOffice window and makes it reachable |
| `read_range` | Returns a range as displayed, with the formula behind each formula cell and the meaning of each error |
| `write_range` | Writes a block of cells as one undo step. Numbers stay numbers, text stays text, `=` starts a formula, `YYYY-MM-DD` becomes a date |
| `undo` | Undoes the last step, but only if it is the write or chart change you name |
| `set_autofilter` | Puts filter buttons on a table's header row |
| `filters` | Lists a sheet's tables with what each filter shows and how many rows it hides |
| `clear_filters` | Drops a sheet's filter criteria and shows every row, as one undo step |
| `named_ranges` | Lists named ranges, with the displayed value of each single named cell |
| `formula_errors` | Lists every formula error with its formula, code and what the code means |
| `charts` | Describes each chart: its range, and which rows LibreOffice read as labels and which as series |
| `set_chart_range` | Points a chart at another range, as one undo step |
| `create_chart` | Adds a column, line, area or pie chart, as one undo step |
| `render` | Returns a sheet or range as PNG pages, with charts and formatting |

Formulas use English function names and `;` between arguments, whatever your locale.

## Limits

- `read_range` reads at most 5,000 cells in one call.
- `render` exports the range as PDF and converts it, so the pages are the ones the sheet
  would print.
- It has only been tested on LibreOffice 26.8 on Linux.

## Development

```sh
uv run --locked ruff check && uv run --locked ruff format --check
uv run --locked pyright
uv run --locked pytest
uv run --locked pytest -m integration --force-enable-socket
```

The integration tests start a private headless LibreOffice with a throwaway profile, so
they cannot touch a spreadsheet you have open.

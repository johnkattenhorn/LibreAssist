"""The MCP server: the entry point, and the only place that reads the environment.

Each tool connects, finds the spreadsheet meant and hands over to `sheets`. A failure the
caller could have avoided comes back as the tool's error with its kind first. There is no
tool to save or close: those stay with the person whose document it is.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from calc_tools import charts as chart_tools
from calc_tools import office, sheets
from calc_tools.errors import CalcError

INSTRUCTIONS = (
    "Tools for the spreadsheet a person has open in LibreOffice Calc. You work in their "
    "live document: reads show unsaved edits, and a write is one undo step they can "
    "reverse with Ctrl+Z. Nothing here saves or closes. Formulas use English function "
    "names and `;` between arguments. After a write that changes layout or a chart, call "
    "render and look at the result."
)


@dataclass(frozen=True)
class Settings:
    pipe: str
    soffice: str
    pdftoppm: str

    @classmethod
    def load(cls, env: Mapping[str, str]) -> Settings:
        return cls(
            pipe=env.get("CALC_TOOLS_PIPE", "calc-tools"),
            soffice=env.get("CALC_TOOLS_SOFFICE", "soffice"),
            pdftoppm=env.get("CALC_TOOLS_PDFTOPPM", "pdftoppm"),
        )


def _reported[**P, R](tool: Callable[P, R]) -> Callable[P, R]:
    """Turn a `CalcError` into the tool's error, kind first, so a caller can branch on it."""

    @wraps(tool)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return tool(*args, **kwargs)
        except CalcError as error:
            raise ToolError(f"{error.kind}: {error}") from None

    return run


def build(settings: Settings) -> MCPServer:
    server = MCPServer("calc-tools", instructions=INSTRUCTIONS)

    def found(document: str | None) -> object:
        return office.find(office.connect(settings.pipe), document)

    @server.tool()
    @_reported
    def documents() -> list[dict[str, object]]:
        """The spreadsheets open in LibreOffice: path, sheets, the active sheet, the
        selection, and whether there are unsaved changes."""
        return [sheets.describe(d) for d in office.spreadsheets(office.connect(settings.pipe))]

    @server.tool()
    @_reported
    def open_document(path: str) -> dict[str, object]:
        """Open a spreadsheet file in LibreOffice, in a window the person can see, and make
        LibreOffice reachable by these tools. Works whether or not it is already running."""
        file = Path(path).expanduser()
        office.launch(file, settings.pipe, soffice=settings.soffice)
        return sheets.describe(office.await_open(file, settings.pipe))

    @server.tool()
    @_reported
    def read_range(sheet: str, cells: str, document: str | None = None) -> dict[str, object]:
        """Read a range such as A1:H40 as the person sees it (displayed text, row by row),
        with the formula behind each formula cell and what each error means. `document` is
        a path, file name or title; leave it out when one spreadsheet is open."""
        return sheets.read(found(document), sheet, cells)

    @server.tool()
    @_reported
    def write_range(
        sheet: str,
        top_left: str,
        rows: list[list[str | float | int | None]],
        document: str | None = None,
        label: str = "Edit by calc-tools",
    ) -> dict[str, object]:
        """Write a block of cells starting at `top_left`, as one undo step named `label`.
        A number is written as a number, text as text, text starting with = as a formula,
        null clears. Returns the range written and any formula errors now in it."""
        return sheets.write(found(document), sheet, top_left, rows, label=label)

    @server.tool()
    @_reported
    def formula_errors(sheet: str | None = None, document: str | None = None) -> dict[str, object]:
        """Every formula error on one sheet, or on all of them: the cell, its formula, the
        code and what the code means."""
        return sheets.formula_errors(found(document), sheet)

    @server.tool()
    @_reported
    def charts(sheet: str, document: str | None = None) -> list[dict[str, object]]:
        """The charts on a sheet: the range each was given and how LibreOffice read it
        (which rows became categories, which became series, of what type)."""
        return chart_tools.charts(found(document), sheet)

    @server.tool()
    @_reported
    def render(
        sheet: str, cells: str | None = None, document: str | None = None, max_pages: int = 2
    ) -> list[Image]:
        """Look at a sheet or a range as images, charts and formatting included: the
        pages it would print as. Use it to check layout, not to read values."""
        pages = sheets.render(
            found(document), sheet, cells, pdftoppm=settings.pdftoppm, max_pages=max_pages
        )
        return [Image(data=page, format="png") for page in pages]

    return server


def main() -> None:
    build(Settings.load(os.environ)).run("stdio")

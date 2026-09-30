"""Read, write, check and look at one open spreadsheet. Part of the UNO boundary.

Reading gives what the person sees (the displayed text) beside what is typed (the
formula). Writing is one undo step and never saves. Nothing here changes the selection,
the active sheet or the modified state except a write.
"""

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import uno  # pyright: ignore[reportMissingImports] - pyuno ships with LibreOffice, not PyPI

from calc_tools.cells import Write, cell_name, classify, trim
from calc_tools.errors import CalcError, Kind, meaning
from calc_tools.office import path_of

FORMULA_ERROR = 4  # com.sun.star.sheet.FormulaResult.ERROR
MAX_CELLS = 5000
MAX_ERRORS = 200
RENDER_DPI = 90
RENDER_TIMEOUT_S = 60


def _prop(name: str, value: Any) -> Any:
    p = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    p.Name = name
    p.Value = value
    return p


def _sheet(document: Any, name: str) -> Any:
    sheets = document.Sheets
    if not sheets.hasByName(name):
        raise CalcError(
            Kind.NOT_FOUND, f"no sheet {name!r}. Sheets: {', '.join(sheets.ElementNames)}"
        )
    return sheets.getByName(name)


def _range(document: Any, sheet: str, cells: str) -> Any:
    illegal = uno.getClass("com.sun.star.uno.RuntimeException")
    try:
        return _sheet(document, sheet).getCellRangeByName(cells)
    except illegal:
        raise CalcError(Kind.INVALID, f"not a range on {sheet}: {cells!r}") from None


def _error_text(cell: Any) -> str:
    code = int(cell.getError())
    return f"{cell.String}: {meaning(code)}"


def _errors_in(cells: Any) -> tuple[dict[str, str], int]:
    """Formula errors in a sheet or range, by cell name, and how many there are in all."""
    found: dict[str, str] = {}
    total = 0
    each = cells.queryFormulaCells(FORMULA_ERROR).Cells.createEnumeration()
    while each.hasMoreElements():
        cell = each.nextElement()
        total += 1
        if len(found) < MAX_ERRORS:
            at = cell.CellAddress
            found[cell_name(at.Row, at.Column)] = f"{_error_text(cell)} in {cell.Formula}"
    return found, total


def describe(document: Any) -> dict[str, object]:
    """What is open and where the person is in it."""
    controller = document.getCurrentController()
    selection = controller.getSelection() if controller is not None else None
    return {
        "title": str(document.Title),
        "path": path_of(document),
        "unsaved_changes": bool(document.isModified()),
        "sheets": list(document.Sheets.ElementNames),
        "active_sheet": str(controller.ActiveSheet.Name) if controller is not None else "",
        "selection": str(getattr(selection, "AbsoluteName", "")),
    }


def read(document: Any, sheet: str, cells: str) -> dict[str, object]:
    """A range as displayed, with the formulas and errors behind it."""
    rng = _range(document, sheet, cells)
    at = rng.RangeAddress
    height, width = at.EndRow - at.StartRow + 1, at.EndColumn - at.StartColumn + 1
    if height * width > MAX_CELLS:
        raise CalcError(
            Kind.INVALID, f"{cells} is {height * width} cells; read at most {MAX_CELLS} at once"
        )
    typed = rng.getFormulaArray()
    shown = [[str(rng.getCellByPosition(c, r).String) for c in range(width)] for r in range(height)]
    formulas = {
        cell_name(at.StartRow + r, at.StartColumn + c): str(text)
        for r, row in enumerate(typed)
        for c, text in enumerate(row)
        if str(text).startswith("=")
    }
    errors, _ = _errors_in(rng)
    return {
        "range": str(rng.AbsoluteName),
        "shown": trim(shown),
        "formulas": formulas,
        "errors": errors,
    }


def write(
    document: Any, sheet: str, top_left: str, rows: Sequence[Sequence[object]], *, label: str
) -> dict[str, object]:
    """Write a block from `top_left` as one undo step; report the errors it left."""
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise CalcError(Kind.INVALID, "rows must be a rectangle with at least one cell")
    kinds = [[classify(value) for value in row] for row in rows]  # refuses before any write
    anchor = _range(document, sheet, top_left).RangeAddress
    target = _sheet(document, sheet).getCellRangeByPosition(
        anchor.StartColumn,
        anchor.StartRow,
        anchor.StartColumn + len(rows[0]) - 1,
        anchor.StartRow + len(rows) - 1,
    )
    undo = document.UndoManager
    undo.enterUndoContext(label)
    try:
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = target.getCellByPosition(c, r)
                match kinds[r][c]:
                    case Write.CLEAR:
                        cell.setFormula("")
                    case Write.NUMBER:
                        cell.setValue(float(value))  # pyright: ignore[reportArgumentType] - classify proved it a number
                    case Write.FORMULA:
                        cell.setFormula(value)
                    case Write.TEXT:
                        cell.setString(value)
    finally:
        undo.leaveUndoContext()
    errors, _ = _errors_in(target)
    return {"range": str(target.AbsoluteName), "undo_step": label, "errors": errors}


def formula_errors(document: Any, sheet: str | None) -> dict[str, object]:
    """Every formula error on one sheet or all of them, with what each code means."""
    names = [sheet] if sheet is not None else list(document.Sheets.ElementNames)
    by_sheet: dict[str, dict[str, str]] = {}
    total = 0
    for name in names:
        found, count = _errors_in(_sheet(document, name))
        total += count
        if found:
            by_sheet[name] = found
    return {"count": total, "errors": by_sheet}


def _address(document: Any, address: Any) -> str:
    sheet = document.Sheets.getByIndex(address.Sheet).Name
    top = cell_name(address.StartRow, address.StartColumn)
    return f"{sheet}.{top}:{cell_name(address.EndRow, address.EndColumn)}"


def charts(document: Any, sheet: str) -> list[dict[str, object]]:
    """Each chart on a sheet: the range it was given and how LibreOffice read it."""
    described: list[dict[str, object]] = []
    embedded = _sheet(document, sheet).Charts
    for name in embedded.ElementNames:
        chart = embedded.getByName(name)
        system = chart.EmbeddedObject.getFirstDiagram().getCoordinateSystems()[0]
        categories = system.getAxisByDimension(0, 0).ScaleData.Categories
        drawn = [
            {
                "type": str(kind.ChartType).rpartition(".")[2],
                "series": [
                    {
                        "label": str(seq.Label.SourceRangeRepresentation) if seq.Label else "",
                        "values": str(seq.Values.SourceRangeRepresentation),
                    }
                    for one in kind.getDataSeries()
                    for seq in one.getDataSequences()
                ],
            }
            for kind in system.getChartTypes()
        ]
        described.append(
            {
                "name": str(name),
                "title": str(chart.EmbeddedObject.Title.String),
                "ranges": [_address(document, a) for a in chart.getRanges()],
                "categories": str(categories.Values.SourceRangeRepresentation)
                if categories
                else "",
                "drawn": drawn,
            }
        )
    return described


def render(
    document: Any, sheet: str, cells: str | None, *, pdftoppm: str, max_pages: int
) -> list[bytes]:
    """A sheet or range as PNG pages, charts included: what the person would print.

    LibreOffice's own PNG export draws the first page of the active sheet whatever it is
    asked for, so the range goes out as PDF and poppler turns the pages into images.
    """
    if shutil.which(pdftoppm) is None:
        raise CalcError(Kind.NOT_FOUND, f"{pdftoppm} not found on PATH: install poppler")
    target = _range(document, sheet, cells) if cells else _sheet(document, sheet)
    with tempfile.TemporaryDirectory(prefix="calc-tools-") as scratch:
        pdf = Path(scratch) / "range.pdf"
        selection = uno.Any("[]com.sun.star.beans.PropertyValue", (_prop("Selection", target),))
        document.storeToURL(
            uno.systemPathToFileUrl(str(pdf)),
            (_prop("FilterName", "calc_pdf_Export"), _prop("FilterData", selection)),
        )
        subprocess.run(
            [pdftoppm, "-png", "-r", str(RENDER_DPI), "-l", str(max_pages), str(pdf), "page"],
            cwd=scratch,
            check=True,
            capture_output=True,
            timeout=RENDER_TIMEOUT_S,
        )
        return [page.read_bytes() for page in sorted(Path(scratch).glob("page*.png"))]

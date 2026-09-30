"""Tables and their filters: filter buttons, what a filter shows, clearing it. Part of the
UNO boundary, beside `sheets`.

A table is what LibreOffice calls a database range: a named area whose first row is a
header. A sheet can also carry one unnamed range, which is where Data > Standard Filter
keeps its criteria. A filter hides rows by position and nothing re-runs it when the rows
under it change, so a stale filter looks like missing data; `filters` is how to see one.
"""

from typing import Any

from calc_tools.cells import cell_name
from calc_tools.sheets import range_named, sheet_named, undo_step

OPERATORS = {
    0: "is empty",
    1: "is not empty",
    2: "=",
    3: "<>",
    4: ">",
    5: ">=",
    6: "<",
    7: "<=",
    12: "contains",
    13: "does not contain",
    14: "begins with",
    16: "ends with",
}
"""com.sun.star.sheet.FilterOperator2, the ones a person reads at a glance."""


def set_autofilter(document: Any, sheet: str, cells: str, *, name: str) -> dict[str, str]:
    """Put filter buttons on the first row of a table. The table is a database range
    called `name`; giving a name that exists moves that table rather than adding one."""
    target = range_named(document, sheet, cells)
    tables = document.DatabaseRanges
    label = f"Filter buttons: {sheet}"
    with undo_step(document, label):
        if tables.hasByName(name):
            tables.getByName(name).setDataArea(target.RangeAddress)
        else:
            tables.addNewByName(name, target.RangeAddress)
        tables.getByName(name).AutoFilter = True
    return {"range": str(target.AbsoluteName), "name": name, "undo_step": label}


def _on_sheet(document: Any, sheet: str) -> list[tuple[str, Any]]:
    """The sheet's tables by name, its unnamed range (named "") last."""
    sheet_named(document, sheet)
    index = list(document.Sheets.ElementNames).index(sheet)
    named = document.DatabaseRanges
    found = [
        (str(name), named.getByName(name))
        for name in named.ElementNames
        if named.getByName(name).DataArea.Sheet == index
    ]
    unnamed = document.getPropertyValue("UnnamedDatabaseRanges")
    if unnamed.hasByTable(index):
        found.append(("", unnamed.getByTable(index)))
    return found


def _shows(table: Any) -> list[str]:
    """Each criterion as column, operator and value: `H = suggested`."""
    left = table.DataArea.StartColumn
    shown: list[str] = []
    for field in table.getFilterDescriptor().getFilterFields3():
        column = cell_name(0, left + field.Field)[:-1]
        operator = OPERATORS.get(int(field.Operator), f"operator {field.Operator}")
        values = " or ".join(str(v.StringValue or v.NumericValue) for v in field.Values)
        shown.append(f"{column} {operator} {values}".rstrip())
    return shown


def _hidden_rows(table: Any) -> int:
    area = table.DataArea
    column = table.ReferredCells.getCellRangeByPosition(0, 0, 0, area.EndRow - area.StartRow)
    visible = sum(r.EndRow - r.StartRow + 1 for r in column.queryVisibleCells().RangeAddresses)
    return area.EndRow - area.StartRow + 1 - visible


def filters(document: Any, sheet: str) -> list[dict[str, object]]:
    """Every table on a sheet: its range, whether it has buttons, what its filter shows
    and how many of its rows are hidden."""
    return [
        {
            "name": name,
            "range": str(table.ReferredCells.AbsoluteName),
            "buttons": bool(table.AutoFilter),
            "shows": _shows(table),
            "hidden_rows": _hidden_rows(table),
        }
        for name, table in _on_sheet(document, sheet)
    ]


def clear_filters(document: Any, sheet: str) -> dict[str, object]:
    """Drop every filter criterion on a sheet and show its rows, as one undo step. Filter
    buttons stay."""
    label = f"Show every row: {sheet}"
    cleared = 0
    with undo_step(document, label):
        for _name, table in _on_sheet(document, sheet):
            if not _shows(table) and not _hidden_rows(table):
                continue
            cells = table.ReferredCells
            cells.filter(cells.createFilterDescriptor(True))
            cleared += 1
    return {"cleared": cleared, "undo_step": label}

"""The charts on a sheet: what each was given and how LibreOffice read it. Part of the UNO
boundary, beside `sheets`.

A chart's range is read by LibreOffice's own rules (which rows are labels, which are
series), and a wrong reading draws a plausible chart of the wrong thing. So every answer
here says how the range was read, not only what it is.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import uno  # pyright: ignore[reportMissingImports] - pyuno ships with LibreOffice, not PyPI

from calc_tools.cells import cell_name
from calc_tools.errors import CalcError, Kind
from calc_tools.sheets import range_named, sheet_named, undo_step


def _address(document: Any, address: Any) -> str:
    sheet = document.Sheets.getByIndex(address.Sheet).Name
    top = cell_name(address.StartRow, address.StartColumn)
    return f"{sheet}.{top}:{cell_name(address.EndRow, address.EndColumn)}"


def _described(document: Any, embedded: Any, name: str) -> dict[str, object]:
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
    return {
        "name": str(name),
        "title": str(chart.EmbeddedObject.Title.String),
        "ranges": [_address(document, a) for a in chart.getRanges()],
        "categories": str(categories.Values.SourceRangeRepresentation) if categories else "",
        "drawn": drawn,
    }


def charts(document: Any, sheet: str) -> list[dict[str, object]]:
    """Each chart on a sheet: the range it was given and how LibreOffice read it."""
    embedded = sheet_named(document, sheet).Charts
    return [_described(document, embedded, name) for name in embedded.ElementNames]


@dataclass(frozen=True)
class Source:
    """The cells a chart draws: first row and first column are labels."""

    sheet: str
    cells: str


def set_range(document: Any, sheet: str, chart: str, source: Source) -> dict[str, object]:
    """Point a chart at another range, as one named undo step."""
    embedded = sheet_named(document, sheet).Charts
    if not embedded.hasByName(chart):
        raise CalcError(
            Kind.NOT_FOUND,
            f"no chart {chart!r} on {sheet}. Charts: {', '.join(embedded.ElementNames) or 'none'}",
        )
    data = range_named(document, source.sheet, source.cells).RangeAddress
    label = f"Chart range: {chart}"
    with undo_step(document, label):
        embedded.getByName(chart).setRanges((data,))
    return _described(document, embedded, chart) | {"undo_step": label}


class ChartKind(StrEnum):
    COLUMN = "column"
    STACKED_COLUMN = "stacked_column"
    LINE = "line"
    AREA = "area"
    STACKED_AREA = "stacked_area"
    PIE = "pie"


_DIAGRAMS: dict[ChartKind, tuple[str, bool]] = {
    ChartKind.COLUMN: ("com.sun.star.chart.BarDiagram", False),
    ChartKind.STACKED_COLUMN: ("com.sun.star.chart.BarDiagram", True),
    ChartKind.LINE: ("com.sun.star.chart.LineDiagram", False),
    ChartKind.AREA: ("com.sun.star.chart.AreaDiagram", False),
    ChartKind.STACKED_AREA: ("com.sun.star.chart.AreaDiagram", True),
    ChartKind.PIE: ("com.sun.star.chart.PieDiagram", False),
}
"""The diagram service for each kind, and whether its series stack."""
MM = 100
"""LibreOffice measures positions in hundredths of a millimetre."""


@dataclass(frozen=True)
class NewChart:
    name: str
    kind: ChartKind
    cells: str
    """The data, first row and first column as labels."""
    at: str
    """The cell its top-left corner sits on."""
    title: str = ""
    data_sheet: str | None = None
    """The sheet holding the data, when it is not the sheet the chart goes on."""
    series_in_rows: bool = False
    width_mm: int = 160
    height_mm: int = 90


def create(document: Any, sheet: str, new: NewChart) -> dict[str, object]:
    """Add a chart to a sheet, as one named undo step, and say how LibreOffice read its
    range. Left alone, the step LibreOffice records for a new chart has no name."""
    embedded = sheet_named(document, sheet).Charts
    if embedded.hasByName(new.name):
        raise CalcError(Kind.INVALID, f"{sheet} already has a chart named {new.name!r}")
    data = range_named(document, new.data_sheet or sheet, new.cells).RangeAddress
    corner = range_named(document, sheet, new.at).Position
    frame = uno.createUnoStruct("com.sun.star.awt.Rectangle")
    frame.X, frame.Y = corner.X, corner.Y
    frame.Width, frame.Height = new.width_mm * MM, new.height_mm * MM
    label = f"Add chart: {new.name}"
    with undo_step(document, label):
        embedded.addNewByName(new.name, frame, (data,), True, True)
        _shape(embedded.getByName(new.name).EmbeddedObject, new)
    return _described(document, embedded, new.name) | {"undo_step": label}


def _shape(chart: Any, new: NewChart) -> None:
    """Give a new chart its kind, the direction of its series and its title."""
    service, stacked = _DIAGRAMS[new.kind]
    chart.lockControllers()
    diagram = chart.createInstance(service)
    chart.setDiagram(diagram)
    diagram.DataRowSource = uno.Enum(
        "com.sun.star.chart.ChartDataRowSource", "ROWS" if new.series_in_rows else "COLUMNS"
    )
    if stacked:
        diagram.Stacked = True
    chart.HasMainTitle = bool(new.title)
    if new.title:
        chart.Title.String = new.title
    chart.HasLegend = True
    chart.unlockControllers()

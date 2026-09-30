"""The charts on a sheet: what each was given and how LibreOffice read it. Part of the UNO
boundary, beside `sheets`.

A chart's range is read by LibreOffice's own rules (which rows are labels, which are
series), and a wrong reading draws a plausible chart of the wrong thing. So every answer
here says how the range was read, not only what it is.
"""

from typing import Any

from calc_tools.cells import cell_name
from calc_tools.sheets import sheet_named


def _address(document: Any, address: Any) -> str:
    sheet = document.Sheets.getByIndex(address.Sheet).Name
    top = cell_name(address.StartRow, address.StartColumn)
    return f"{sheet}.{top}:{cell_name(address.EndRow, address.EndColumn)}"


def charts(document: Any, sheet: str) -> list[dict[str, object]]:
    """Each chart on a sheet: the range it was given and how LibreOffice read it."""
    described: list[dict[str, object]] = []
    embedded = sheet_named(document, sheet).Charts
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

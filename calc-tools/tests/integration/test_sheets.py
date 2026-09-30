"""The tools against a real spreadsheet: what is read, written, flagged and drawn."""

import asyncio
from pathlib import Path
from typing import Any

import uno  # pyright: ignore[reportMissingImports] - pyuno ships with LibreOffice, not PyPI

import pytest

from calc_tools import charts, office, sheets, tables
from calc_tools.charts import ChartKind, NewChart, Source
from calc_tools.errors import CalcError, Kind
from calc_tools.server import Settings, build

from .conftest import Running

pytestmark = pytest.mark.integration
PNG = b"\x89PNG\r\n\x1a\n"


def test_a_range_is_read_as_shown_with_the_formulas_and_errors_behind_it(book: Any) -> None:
    got = sheets.read(book, "Data", "A1:H20")
    assert got["range"] == "$Data.$A$1:$H$20"
    assert got["shown"] == [
        ["Item", "Pounds", "Doubled", "", "#DIV/0!"],
        ["Tea", "1.5", "3", "", "#NAME?"],
        ["Coffee", "2.25", "4.5", "", ""],
    ]
    assert got["formulas"] == {
        "C2": "=B2*2",
        "C3": "=B3*2",
        "E1": "=1/0",
        "E2": "=nope(1)",
    }  # Calc lower-cases a name it does not know
    errors = got["errors"]
    assert isinstance(errors, dict) and sorted(errors) == ["E1", "E2"]
    assert "division by zero" in errors["E1"] and "=1/0" in errors["E1"]


def test_a_missing_sheet_or_a_bad_range_is_refused_by_kind(book: Any) -> None:
    with pytest.raises(CalcError) as missing:
        sheets.read(book, "Nowhere", "A1")
    assert missing.value.kind is Kind.NOT_FOUND and "Data, Notes" in str(missing.value)
    with pytest.raises(CalcError) as bad:
        sheets.read(book, "Data", "not a range")
    assert bad.value.kind is Kind.INVALID
    with pytest.raises(CalcError) as huge:
        sheets.read(book, "Data", "A1:Z1000")
    assert huge.value.kind is Kind.INVALID and "5000" in str(huge.value)


def test_a_write_keeps_types_reports_its_errors_and_is_one_undo_step(book: Any) -> None:
    rows: list[list[object]] = [["Milk", 0.95, "=B4*2"], ["007", None, "=1/0"]]
    done = sheets.write(book, "Data", "A4", rows, label="Add two rows")
    assert done["range"] == "$Data.$A$4:$C$5"
    assert done["errors"] == {"C5": "#DIV/0!: division by zero, shown as #DIV/0! in =1/0"}
    data = book.Sheets.getByName("Data")
    assert data.getCellByPosition(1, 3).getValue() == 0.95
    assert data.getCellByPosition(2, 3).getValue() == 1.9
    assert data.getCellByPosition(0, 4).getType().value == "TEXT"  # 007 stayed text
    assert data.getCellByPosition(0, 4).String == "007"
    assert book.UndoManager.getCurrentUndoActionTitle() == "Add two rows"
    book.UndoManager.undo()
    assert data.getCellByPosition(0, 3).String == "" and data.getCellByPosition(2, 4).String == ""


def test_a_write_that_cannot_be_written_changes_nothing(book: Any) -> None:
    with pytest.raises(CalcError) as refused:
        sheets.write(book, "Data", "A4", [["fine", True]], label="x")
    assert refused.value.kind is Kind.INVALID
    assert book.Sheets.getByName("Data").getCellByPosition(0, 3).String == ""
    with pytest.raises(CalcError):
        sheets.write(book, "Data", "A4", [["a", "b"], ["c"]], label="x")


def test_every_formula_error_is_listed_with_its_meaning(book: Any) -> None:
    assert sheets.formula_errors(book, None) == {
        "count": 2,
        "errors": {
            "Data": {
                "E1": "#DIV/0!: division by zero, shown as #DIV/0! in =1/0",
                "E2": "#NAME?: invalid name, shown as #NAME?: a function or named range Calc "
                "does not know. Inside LET, a variable named like a function (days, months) "
                "fails this way in =nope(1)",
            }
        },
    }
    assert sheets.formula_errors(book, "Notes") == {"count": 0, "errors": {}}


def test_a_chart_is_described_by_how_libreoffice_read_its_range(book: Any) -> None:
    (chart,) = charts.charts(book, "Data")
    assert chart["name"] == "Spend"
    assert chart["ranges"] == ["Data.A1:B3"]
    assert chart["categories"] == "$Data.$A$2:$A$3"
    assert chart["drawn"] == [
        {
            "type": "ColumnChartType",
            "series": [{"label": "$Data.$B$1", "values": "$Data.$B$2:$B$3"}],
        }
    ]
    assert "undo_step" not in chart  # describing a chart changes nothing


def test_a_chart_can_be_pointed_at_another_range_and_says_how_it_reads_it(book: Any) -> None:
    chart = charts.set_range(book, "Data", "Spend", Source("Data", "A1:C3"))
    assert chart["ranges"] == ["Data.A1:C3"]
    assert chart["undo_step"] == "Chart range: Spend"
    drawn = chart["drawn"]
    assert isinstance(drawn, list) and [len(kind["series"]) for kind in drawn] == [2]
    with pytest.raises(CalcError) as missing:
        charts.set_range(book, "Data", "Nope", Source("Data", "A1:C3"))
    assert missing.value.kind is Kind.NOT_FOUND and "Spend" in str(missing.value)
    sheets.undo(book, "Chart range: Spend")
    assert charts.charts(book, "Data")[0]["ranges"] == ["Data.A1:B3"]


def test_a_chart_is_created_where_asked_of_the_kind_asked(book: Any) -> None:
    new = NewChart(name="Doubled", kind=ChartKind.LINE, cells="A1:C3", at="E8", title="Both")
    chart = charts.create(book, "Data", new)
    assert chart["name"] == "Doubled" and chart["title"] == "Both"
    assert chart["undo_step"] == "Add chart: Doubled"
    assert chart["ranges"] == ["Data.A1:C3"]
    assert chart["drawn"] == [
        {
            "type": "LineChartType",
            "series": [
                {"label": "$Data.$B$1", "values": "$Data.$B$2:$B$3"},
                {"label": "$Data.$C$1", "values": "$Data.$C$2:$C$3"},
            ],
        }
    ]
    assert [c["name"] for c in charts.charts(book, "Data")] == ["Spend", "Doubled"]
    stacked = NewChart(
        name="ByRow", kind=ChartKind.STACKED_COLUMN, cells="A1:C3", at="E30", series_in_rows=True
    )
    by_row = charts.create(book, "Data", stacked)["drawn"]
    assert isinstance(by_row, list) and by_row[0]["type"] == "ColumnChartType"
    assert [s["label"] for s in by_row[0]["series"]] == ["$Data.$A$2", "$Data.$A$3"]
    with pytest.raises(CalcError) as taken:
        charts.create(book, "Data", new)
    assert taken.value.kind is Kind.INVALID
    sheets.undo(book, "Add chart: ByRow")
    assert [c["name"] for c in charts.charts(book, "Data")] == ["Spend", "Doubled"]


def test_a_date_is_written_as_a_date_the_sheet_can_calculate_with(book: Any) -> None:
    sheets.write(book, "Data", "G1", [["2026-09-30", "=G1+1"]], label="Dates")
    data = book.Sheets.getByName("Data")
    assert data.getCellByPosition(6, 0).getValue() == 46295  # days since 30 Dec 1899
    assert data.getCellByPosition(7, 0).getValue() == 46296
    shown = str(data.getCellByPosition(6, 0).String)
    assert shown != "46295" and "30" in shown  # formatted as a date, not the bare number


def test_a_table_is_given_filter_buttons_and_the_same_name_moves_them(book: Any) -> None:
    done = tables.set_autofilter(book, "Data", "A1:C3", name="DataTable")
    assert done == {
        "range": "$Data.$A$1:$C$3",
        "name": "DataTable",
        "undo_step": "Filter buttons: Data",
    }
    table = book.DatabaseRanges.getByName("DataTable")
    assert table.AutoFilter is True
    area = table.DataArea
    assert (area.StartRow, area.StartColumn, area.EndRow, area.EndColumn) == (0, 0, 2, 2)
    tables.set_autofilter(book, "Data", "A1:C9", name="DataTable")
    assert book.DatabaseRanges.getByName("DataTable").DataArea.EndRow == 8
    assert list(book.DatabaseRanges.ElementNames).count("DataTable") == 1
    with pytest.raises(CalcError) as bad:
        tables.set_autofilter(book, "Data", "nowhere", name="X")
    assert bad.value.kind is Kind.INVALID
    sheets.undo(book, "Filter buttons: Data")
    assert book.DatabaseRanges.getByName("DataTable").DataArea.EndRow == 2  # the first table


def _only(column: int, text: str) -> tuple[Any, ...]:
    field = uno.createUnoStruct("com.sun.star.sheet.TableFilterField")
    field.Field, field.IsNumeric, field.StringValue = column, False, text
    field.Operator = uno.Enum("com.sun.star.sheet.FilterOperator", "EQUAL")
    return (field,)


def test_filters_are_reported_with_what_they_show_and_how_much_they_hide(book: Any) -> None:
    assert tables.filters(book, "Data") == []
    tables.set_autofilter(book, "Data", "A1:C3", name="DataTable")
    table = book.DatabaseRanges.getByName("DataTable")
    table.getFilterDescriptor().setFilterFields(_only(0, "Tea"))
    table.refresh()
    assert tables.filters(book, "Data") == [
        {
            "name": "DataTable",
            "range": "$Data.$A$1:$C$3",
            "buttons": True,
            "shows": ["A = Tea"],
            "hidden_rows": 1,
        }
    ]


def test_clearing_filters_shows_every_row_and_keeps_the_buttons(book: Any) -> None:
    tables.set_autofilter(book, "Data", "A1:C3", name="DataTable")
    table = book.DatabaseRanges.getByName("DataTable")
    table.getFilterDescriptor().setFilterFields(_only(0, "Tea"))
    table.refresh()
    notes = book.Sheets.getByName("Notes")
    notes.getCellByPosition(0, 1).setString("hidden by a standard filter")
    loose = notes.getCellRangeByName("A1:A2")
    standard = loose.createFilterDescriptor(True)
    standard.setFilterFields(_only(0, "nothing matches"))
    loose.filter(standard)
    assert [f["hidden_rows"] for f in tables.filters(book, "Notes")] == [2]
    assert tables.clear_filters(book, "Data") == {"cleared": 1, "undo_step": "Show every row: Data"}
    assert tables.clear_filters(book, "Notes")["cleared"] == 1
    (still,) = tables.filters(book, "Data")
    assert (still["buttons"], still["shows"], still["hidden_rows"]) == (True, [], 0)
    assert all(f["hidden_rows"] == 0 and f["shows"] == [] for f in tables.filters(book, "Notes"))
    assert book.Sheets.getByName("Data").Rows.getByIndex(2).IsVisible is True
    assert tables.clear_filters(book, "Data")["cleared"] == 0


def test_names_are_listed_with_what_a_single_cell_shows(book: Any) -> None:
    assert sheets.named_ranges(book, None) == [
        {"name": "Prices", "refers_to": "$Data.$B$2:$B$3", "shown": ""},
        {"name": "Total", "refers_to": "$Data.$C$2", "shown": "3"},
    ]
    assert [n["name"] for n in sheets.named_ranges(book, "tot")] == ["Total"]


def test_only_the_step_named_is_undone(book: Any) -> None:
    sheets.write(book, "Data", "A4", [["Milk"]], label="Add milk")
    data = book.Sheets.getByName("Data")
    with pytest.raises(CalcError) as other:
        sheets.undo(book, "Something else")
    assert other.value.kind is Kind.INVALID and "Add milk" in str(other.value)
    assert data.getCellByPosition(0, 3).String == "Milk"
    assert sheets.undo(book, "Add milk") == {"undone": "Add milk"}
    assert data.getCellByPosition(0, 3).String == ""


def test_a_range_is_rendered_to_png_without_touching_the_document(book: Any) -> None:
    before = sheets.describe(book)
    pages = sheets.render(book, "Notes", "A1:C5", pdftoppm="pdftoppm", max_pages=2)
    assert len(pages) == 1 and pages[0].startswith(PNG)
    whole = sheets.render(book, "Data", None, pdftoppm="pdftoppm", max_pages=2)
    assert whole and all(page.startswith(PNG) for page in whole)
    assert sheets.describe(book) == before  # the active sheet and the selection stay put
    assert before["active_sheet"] == "Data"
    with pytest.raises(CalcError) as missing:
        sheets.render(book, "Data", None, pdftoppm="no-such-pdftoppm", max_pages=1)
    assert missing.value.kind is Kind.NOT_FOUND


def test_the_spreadsheet_is_found_by_title_and_the_server_reads_it(
    running: Running, book: Any
) -> None:
    assert office.find(running.desktop, None) is not None
    assert office.find(running.desktop, str(book.Title)).Title == book.Title
    with pytest.raises(CalcError) as unknown:
        office.find(running.desktop, "other.ods")
    assert unknown.value.kind is Kind.NOT_FOUND
    server = build(Settings(pipe=running.pipe, soffice="soffice", pdftoppm="pdftoppm"))
    listed = asyncio.run(server.call_tool("documents", {}))
    assert "Data" in str(listed) and "Notes" in str(listed)
    drawn = asyncio.run(server.call_tool("render", {"sheet": "Notes", "cells": "A1:B2"}))
    assert "image" in str(drawn).lower()


def test_opening_a_file_asks_libreoffice_to_accept_on_the_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "argv"
    stub = tmp_path / "bin" / "soffice"
    stub.parent.mkdir()
    stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}"\n', encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub.parent}:/usr/bin:/bin")
    file = tmp_path / "My Book.ods"
    file.write_bytes(b"")
    office.launch(file, "some-pipe", soffice="soffice")
    for _ in range(50):
        if record.exists() and record.read_text(encoding="utf-8").count("\n") == 2:
            break
        __import__("time").sleep(0.1)
    assert record.read_text(encoding="utf-8").splitlines() == [
        "--accept=pipe,name=some-pipe;urp;",
        str(file),
    ]
    with pytest.raises(CalcError) as missing:
        office.launch(tmp_path / "absent.ods", "some-pipe", soffice="soffice")
    assert missing.value.kind is Kind.NOT_FOUND

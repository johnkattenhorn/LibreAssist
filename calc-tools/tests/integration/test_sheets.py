"""The tools against a real spreadsheet: what is read, written, flagged and drawn."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from calc_tools import office, sheets
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
    (chart,) = sheets.charts(book, "Data")
    assert chart["name"] == "Spend"
    assert chart["ranges"] == ["Data.A1:B3"]
    assert chart["categories"] == "$Data.$A$2:$A$3"
    assert chart["drawn"] == [
        {
            "type": "ColumnChartType",
            "series": [{"label": "$Data.$B$1", "values": "$Data.$B$2:$B$3"}],
        }
    ]


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

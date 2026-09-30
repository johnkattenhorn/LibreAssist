"""A private headless LibreOffice for the session and a small spreadsheet per test.

The tools themselves never start LibreOffice hidden; the tests do, with a throwaway
profile and their own pipe, so they never meet a document somebody has open.
"""

import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import uno  # pyright: ignore[reportMissingImports] - pyuno ships with LibreOffice, not PyPI

from calc_tools import office

START_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class Running:
    pipe: str
    desktop: Any


@pytest.fixture(scope="session")
def running() -> Iterator[Running]:
    pipe = f"calc-tools-test-{uuid.uuid4().hex}"
    profile = Path(tempfile.mkdtemp(prefix="calc-tools-lo-"))
    process = subprocess.Popen(
        [
            "soffice",
            "--headless",
            "--invisible",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            f"--accept=pipe,name={pipe};urp;",
            f"-env:UserInstallation={profile.as_uri()}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        desktop = office.connect(pipe, timeout_s=START_TIMEOUT_S)
        yield Running(pipe, desktop)
        try:
            desktop.terminate()
        except uno.getClass("com.sun.star.uno.RuntimeException"):
            pass  # the bridge drops as soffice exits; that is the success path
        process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)
        shutil.rmtree(profile, ignore_errors=True)


def _hidden() -> tuple[Any, ...]:
    hidden = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    hidden.Name, hidden.Value = "Hidden", True
    return (hidden,)


@pytest.fixture
def book(running: Running) -> Iterator[Any]:
    """Two sheets: Data with a formula, two errors and a chart; Notes with one cell."""
    document = running.desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, _hidden())
    try:
        data = document.Sheets.getByIndex(0)
        data.Name = "Data"
        for column, header in enumerate(("Item", "Pounds", "Doubled")):
            data.getCellByPosition(column, 0).setString(header)
        for row, (item, pounds) in enumerate((("Tea", 1.5), ("Coffee", 2.25)), start=1):
            data.getCellByPosition(0, row).setString(item)
            data.getCellByPosition(1, row).setValue(pounds)
            data.getCellByPosition(2, row).setFormula(f"=B{row + 1}*2")
        data.getCellByPosition(4, 0).setFormula("=1/0")
        data.getCellByPosition(4, 1).setFormula("=NOPE(1)")
        document.Sheets.insertNewByName("Notes", 1)
        document.Sheets.getByName("Notes").getCellByPosition(0, 0).setString("kept")
        frame = uno.createUnoStruct("com.sun.star.awt.Rectangle")
        frame.X, frame.Y, frame.Width, frame.Height = 500, 3000, 9000, 6000
        source = data.getCellRangeByName("A1:B3").RangeAddress
        data.Charts.addNewByName("Spend", frame, (source,), True, True)
        document.setModified(False)
        yield document
    finally:
        document.close(True)

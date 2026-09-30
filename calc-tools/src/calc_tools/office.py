"""Reach the LibreOffice a person has open, over a named pipe. Part of the UNO boundary.

It connects, finds the spreadsheet meant and can ask LibreOffice to open a file. It never
starts a hidden LibreOffice and never closes or saves anything: the documents are the
person's. `sheets` is the other half of the boundary; nothing else imports pyuno.
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import uno  # pyright: ignore[reportMissingImports] - pyuno ships with LibreOffice, not PyPI

from calc_tools.cells import Open, choose
from calc_tools.errors import CalcError, Kind

CONNECT_TIMEOUT_S = 3.0
OPEN_TIMEOUT_S = 40.0
SPREADSHEET = "com.sun.star.sheet.SpreadsheetDocument"


def connect(pipe: str, *, timeout_s: float = CONNECT_TIMEOUT_S) -> Any:
    """The Desktop of the LibreOffice accepting on `pipe`."""
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local
    )
    no_connection = uno.getClass("com.sun.star.connection.NoConnectException")
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            remote = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
            return remote.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", remote
            )
        except no_connection:
            if time.monotonic() > deadline:
                raise CalcError(
                    Kind.NOT_RUNNING,
                    f"no LibreOffice is accepting connections on the pipe {pipe!r}: open a "
                    "spreadsheet with the open_document tool, or start LibreOffice with "
                    f"--accept='pipe,name={pipe};urp;'",
                ) from None
            time.sleep(0.2)


def spreadsheets(desktop: Any) -> list[Any]:
    found: list[Any] = []
    components = desktop.Components.createEnumeration()
    while components.hasMoreElements():
        component = components.nextElement()
        if component.supportsService(SPREADSHEET):
            found.append(component)
    return found


def path_of(document: Any) -> str:
    url = document.getURL()
    return uno.fileUrlToSystemPath(url) if url.startswith("file:") else ""


def find(desktop: Any, wanted: str | None) -> Any:
    """The spreadsheet meant: by path, file name or title, or the only one open."""
    open_now = spreadsheets(desktop)
    described = [Open(str(d.Title), path_of(d)) for d in open_now]
    return open_now[choose(described, wanted)]


def launch(path: Path, pipe: str, *, soffice: str) -> None:
    """Ask LibreOffice to open `path` and to accept connections on `pipe`.

    A LibreOffice already running takes the request from this second invocation. It is
    left running; nothing here waits on it.
    """
    if shutil.which(soffice) is None:
        raise CalcError(Kind.NOT_FOUND, f"{soffice} not found on PATH: install LibreOffice")
    if not path.is_file():
        raise CalcError(Kind.NOT_FOUND, f"no such file: {path}")
    subprocess.Popen(
        [soffice, f"--accept=pipe,name={pipe};urp;", str(path.resolve())],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def await_open(path: Path, pipe: str, *, timeout_s: float = OPEN_TIMEOUT_S) -> Any:
    """The document for `path`, once LibreOffice has it open."""
    wanted = str(path.resolve())
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            for document in spreadsheets(connect(pipe, timeout_s=1.0)):
                if path_of(document) == wanted:
                    return document
        except CalcError:
            pass  # not accepting yet: it is starting
        if time.monotonic() > deadline:
            raise CalcError(
                Kind.NOT_RUNNING, f"LibreOffice did not open {path.name} within {timeout_s:.0f}s"
            )
        time.sleep(0.5)

"""The rules that need no LibreOffice: cell names, written values, which document. Pure."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from calc_tools.errors import CalcError, Kind


def cell_name(row: int, col: int) -> str:
    """0-based row and column as Calc names the cell: (0, 26) is AA1."""
    letters = ""
    n = col + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return f"{letters}{row + 1}"


class Write(StrEnum):
    CLEAR = "clear"
    NUMBER = "number"
    FORMULA = "formula"
    DATE = "date"
    TEXT = "text"


def _is_date(text: str) -> bool:
    """Exactly YYYY-MM-DD, and a day that exists."""
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def classify(value: object) -> Write:
    """What a value becomes when written: a number stays a number, text stays text, and
    a date written YYYY-MM-DD becomes a date."""
    match value:
        case None | "":
            return Write.CLEAR
        case bool():
            raise CalcError(
                Kind.INVALID, "true and false are not cell contents: write 1, 0 or text"
            )
        case int() | float():
            return Write.NUMBER
        case str() if value.startswith("="):
            return Write.FORMULA
        case str() if _is_date(value):
            return Write.DATE
        case str():
            return Write.TEXT
        case _:
            raise CalcError(Kind.INVALID, f"not a cell content: {value!r}")


def trim(rows: Sequence[Sequence[str]]) -> list[list[str]]:
    """The rows without the empty rows below and empty columns right of the last content."""
    last_row = max((r for r, row in enumerate(rows) if any(row)), default=-1)
    kept = rows[: last_row + 1]
    last_col = max((c for row in kept for c, shown in enumerate(row) if shown), default=-1)
    return [list(row[: last_col + 1]) for row in kept]


@dataclass(frozen=True)
class Open:
    """An open spreadsheet as far as choosing between them needs."""

    title: str
    path: str
    """Empty for a document never saved."""


def _listed(open_now: Sequence[Open]) -> str:
    return ", ".join(o.path or o.title for o in open_now) or "none"


def choose(open_now: Sequence[Open], wanted: str | None) -> int:
    """Which open spreadsheet is meant: by path, then file name, then title; with no
    name, the only one."""
    if not open_now:
        raise CalcError(Kind.NOT_FOUND, "no spreadsheet is open in LibreOffice")
    if wanted is None:
        if len(open_now) == 1:
            return 0
        raise CalcError(
            Kind.INVALID, f"several spreadsheets are open, name one: {_listed(open_now)}"
        )
    folded = wanted.casefold()
    tests = (
        lambda o: o.path == wanted,
        lambda o: o.path.rpartition("/")[2].casefold() == folded,
        lambda o: o.title.casefold() == folded,
    )
    for test in tests:
        found = [i for i, o in enumerate(open_now) if test(o)]
        if len(found) == 1:
            return found[0]
        if found:
            raise CalcError(Kind.INVALID, f"{wanted} matches more than one: {_listed(open_now)}")
    raise CalcError(Kind.NOT_FOUND, f"{wanted} is not open. Open: {_listed(open_now)}")

"""What can go wrong, by kind, and what Calc's formula error codes mean. Pure.

Every failure a caller could have avoided is a `CalcError` with a kind, so the server
reports it the same way whichever tool met it. The meanings are for a reader who has the
bare code and nothing else; they are not the whole of LibreOffice's list.
"""

from enum import StrEnum


class Kind(StrEnum):
    NOT_RUNNING = "not_running"
    """No LibreOffice is accepting connections on the pipe."""
    NOT_FOUND = "not_found"
    """The document, sheet, range or program asked for does not exist."""
    INVALID = "invalid"
    """The request cannot be carried out as it was put."""


class CalcError(Exception):
    def __init__(self, kind: Kind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


MEANINGS: dict[int, str] = {
    501: "invalid character in the formula",
    502: "invalid argument: a function was given a value it cannot use",
    503: "invalid floating point operation, shown as #NUM!",
    504: "parameter list error: an argument is of the wrong kind",
    508: "brackets do not pair. Over UNO this is also what a formula with `,` between "
    "arguments gives: the separator is `;`",
    509: "missing operator",
    510: "missing variable: an operator has nothing to work on",
    511: "missing variable: a function has too few arguments",
    512: "formula overflow: too many tokens",
    519: "no result, shown as #VALUE!: a value is of the wrong type",
    522: "circular reference",
    523: "the calculation does not converge",
    524: "invalid reference, shown as #REF!: a cell, sheet or range is gone",
    525: "invalid name, shown as #NAME?: a function or named range Calc does not know. "
    "Inside LET, a variable named like a function (days, months) fails this way",
    527: "internal overflow: references nest too deeply",
    532: "division by zero, shown as #DIV/0!",
    533: "nested arrays are not supported",
    32767: "not available, shown as #N/A",
}


def meaning(code: int) -> str:
    return MEANINGS.get(code, f"error {code}")

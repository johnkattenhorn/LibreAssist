"""The pure rules: cell names, what a written value becomes, which document is meant."""

import pytest

from calc_tools.cells import Open, Write, cell_name, choose, classify, trim
from calc_tools.errors import CalcError, Kind, meaning


@pytest.mark.parametrize(
    ("row", "col", "name"), [(0, 0, "A1"), (2, 25, "Z3"), (0, 26, "AA1"), (99, 74, "BW100")]
)
def test_a_cell_is_named_as_calc_names_it(row: int, col: int, name: str) -> None:
    assert cell_name(row, col) == name


def test_a_written_value_keeps_its_type() -> None:
    assert classify(None) is Write.CLEAR
    assert classify(12) is Write.NUMBER
    assert classify(1.5) is Write.NUMBER
    assert classify("=SUM(A1:A3)") is Write.FORMULA
    assert classify("007") is Write.TEXT  # digits sent as text stay text
    assert classify("") is Write.CLEAR


@pytest.mark.parametrize("value", [True, [1], {"a": 1}])
def test_a_value_that_is_no_cell_content_is_refused(value: object) -> None:
    with pytest.raises(CalcError) as refused:
        classify(value)
    assert refused.value.kind is Kind.INVALID


def test_trailing_empty_rows_and_columns_are_dropped_and_inner_ones_kept() -> None:
    rows = [["a", "", "c", ""], ["", "", "", ""], ["x", "", "", ""], ["", "", "", ""]]
    assert trim(rows) == [["a", "", "c"], ["", "", ""], ["x", "", ""]]
    assert trim([["", ""], ["", ""]]) == []


BOOKS = (
    Open("Personal-Finances.ods (read-only)", "/home/u/Finance/Personal-Finances.ods"),
    Open("Untitled 1", ""),
    Open("budget.ods", "/home/u/old/budget.ods"),
)


def test_a_document_is_chosen_by_path_then_file_name_then_title() -> None:
    assert choose(BOOKS, "/home/u/old/budget.ods") == 2
    assert choose(BOOKS, "personal-finances.ods") == 0
    assert choose(BOOKS, "Untitled 1") == 1


def test_no_name_means_the_only_spreadsheet_and_is_refused_when_there_are_several() -> None:
    assert choose(BOOKS[:1], None) == 0
    with pytest.raises(CalcError) as refused:
        choose(BOOKS, None)
    assert refused.value.kind is Kind.INVALID
    assert "Personal-Finances.ods" in str(refused.value) and "budget.ods" in str(refused.value)


def test_an_unknown_or_missing_document_says_what_is_open() -> None:
    with pytest.raises(CalcError) as refused:
        choose(BOOKS, "other.ods")
    assert refused.value.kind is Kind.NOT_FOUND
    assert "Untitled 1" in str(refused.value)
    with pytest.raises(CalcError) as none_open:
        choose((), None)
    assert none_open.value.kind is Kind.NOT_FOUND


def test_an_error_code_comes_with_what_it_means() -> None:
    assert "division by zero" in meaning(532).lower()
    assert "name" in meaning(525).lower()
    assert ";" in meaning(508)  # the separator trap, measured over UNO
    assert meaning(999) == "error 999"

"""The server boundary with no LibreOffice behind it: settings, the tool list, a refusal."""

import asyncio

import pytest

from calc_tools.server import Settings, build


def test_settings_default_and_read_the_environment() -> None:
    assert Settings.load({}) == Settings(pipe="calc-tools", soffice="soffice", pdftoppm="pdftoppm")
    assert Settings.load({"CALC_TOOLS_PIPE": "another-pipe"}).pipe == "another-pipe"


def test_the_server_offers_every_tool() -> None:
    server = build(Settings.load({}))
    names = sorted(tool.name for tool in asyncio.run(server.list_tools()))
    assert names == [
        "charts",
        "clear_filters",
        "create_chart",
        "documents",
        "filters",
        "formula_errors",
        "named_ranges",
        "open_document",
        "read_range",
        "render",
        "set_autofilter",
        "set_chart_range",
        "undo",
        "write_range",
    ]


def test_with_no_libreoffice_listening_a_tool_says_how_to_start_one() -> None:
    server = build(Settings(pipe="calc-tools-nobody-listening", soffice="soffice", pdftoppm="x"))
    with pytest.raises(Exception, match="open_document") as refused:
        asyncio.run(server.call_tool("documents", {}))
    assert "not_running" in str(refused.value)

import asyncio
import os

from renfe_tui import bridge


def test_real_cli_offline(monkeypatch):
    monkeypatch.delenv(bridge.CLI_ENV, raising=False)
    monkeypatch.setenv("RENFE_CACHE_DIR", os.devnull + "-unused")
    found = asyncio.run(bridge.run("stations", "madrid"))
    assert found.exit_code == 0
    assert any(s["code"] == "MADRI" for s in found.data["stations"])
    bad = asyncio.run(bridge.run("status", "abc"))
    assert bad.exit_code == 2
    assert bad.data is None
    assert bad.error["type"] == "usage"


async def collect(*args: str) -> list[bridge.Line]:
    return [line async for line in bridge.stream(*args)]


def test_real_cli_rejects_new_commands_before_any_request(monkeypatch):
    monkeypatch.delenv(bridge.CLI_ENV, raising=False)
    watch = asyncio.run(collect("watch", "abc"))[-1].result
    assert watch.exit_code == 2 and watch.error["type"] == "usage"
    opened = asyncio.run(bridge.run("open", "MADRI", "BARCE", "--date", "2027-01-29", "--train", "x"))
    assert opened.exit_code == 2 and opened.error["type"] == "usage"
    late = asyncio.run(collect("checkout", "MADRI", "BARCE", "--date", "2027-02-01", "--train", "03091"))[-1].result
    assert late.exit_code == 2 and late.error["type"] == "usage"

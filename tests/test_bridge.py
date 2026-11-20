import asyncio
from datetime import date

import pytest

from renfe_tui import bridge, format as fmt


def test_partial_search_keeps_stdout_and_error(fake_cli, scenario):
    scenario("partial")
    result = asyncio.run(bridge.run("search", "MADRI", "BARCE"))
    assert result.exit_code == 5
    assert result.data["count"] == 2
    assert result.error["type"] == "blocked"
    assert result.blocked


def test_usage_error_has_no_data(fake_cli, scenario):
    scenario("usage")
    result = asyncio.run(bridge.run("search", "Xyz", "BARCE"))
    assert (result.exit_code, result.data, result.error["type"]) == (2, None, "usage")


def test_missing_cli(monkeypatch, tmp_path):
    monkeypatch.setenv(bridge.CLI_ENV, str(tmp_path / "nope"))
    result = asyncio.run(bridge.run("delays"))
    assert result.exit_code == 127
    assert result.error["type"] == "missing_cli"


def test_cancel_kills_child(fake_cli, tmp_path, monkeypatch):
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nexec sleep 30\n")
    slow.chmod(0o755)
    monkeypatch.setenv(bridge.CLI_ENV, str(slow))

    spawned = asyncio.Event()
    spawn = asyncio.create_subprocess_exec

    async def spawn_and_tell(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        spawned.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_and_tell)

    async def go():
        task = asyncio.create_task(bridge.run("delays"))
        await spawned.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)

    asyncio.run(go())


def test_search_args():
    assert bridge.search_args("MADRI", "BARCE", "2027-01-29", "08:00") == [
        "search", "MADRI", "BARCE", "--date", "2027-01-29", "--limit", "30", "--after", "08:00"]


@pytest.mark.parametrize("text,expected", [
    ("hoy", "2026-11-20"), ("mañana", "2026-11-21"), ("29/01", "2027-01-29"),
    ("25/12", "2026-12-25"), ("1/2/27", "2027-02-01"), ("2027-03-04", "2027-03-04"),
])
def test_parse_day(text, expected):
    assert fmt.parse_day(text, date(2026, 11, 20)) == expected


def test_parse_clock():
    assert fmt.parse_clock("8") == "08:00"
    assert fmt.parse_clock("0830") == "08:30"
    with pytest.raises(ValueError):
        fmt.parse_clock("25:00")


def test_price():
    assert fmt.price(1234.5) == "1.234,50 €"


@pytest.mark.parametrize("english,spanish", [
    ("no station matches 'Xyz'; try `renfe stations Xyz`", "No encuentro la estación «Xyz»."),
    ("no station matches 'Chamartn'; try `renfe stations Chamartn`. Did you mean Madrid-Chamartín (17000)?",
     "¿Quizás Madrid-Chamartín (17000)?"),
    ("No more trains today after 23:30; try --date tomorrow.", "Hoy no quedan trenes después de las 23:30"),
    ("Delays are unknown (live map: timeout).", "No se han podido consultar los retrasos."),
    ("Selected card (44,07 €). Review Renfe's total and terms, then continue in Chrome. Keep this window open.",
     "Pago elegido: Tarjeta (44,07 €). Revisa el total y las condiciones de Renfe y sigue en el navegador. "
     "Deja la ventana abierta hasta volver del proveedor de pago."),
    ("The train is probably stopped at Lleida, since about 11:40.", "Parece detenido en Lleida desde las 11:40."),
    ("Something new from the CLI.", "Something new from the CLI."),
])
def test_translate(english, spanish):
    assert spanish in fmt.translate(english)


def test_usage_error_is_translated():
    assert fmt.error_text({"type": "usage", "message": "origin and destination are the same station"}) == \
        "Origen y destino son la misma estación."


def test_language_detection(monkeypatch):
    from renfe_tui import i18n

    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert i18n.detect() == "es"
    monkeypatch.setenv("LANG", "en_GB.UTF-8")
    assert i18n.detect() == "en"
    monkeypatch.setenv("LC_ALL", "es_MX.UTF-8")
    assert i18n.detect() == "es"


def test_english_formats():
    from renfe_tui import i18n

    i18n.set_language("en")
    try:
        assert fmt.price(44.07) == "€44.07"
        assert fmt.long_day_human("2026-11-20") == "Friday 20 November"
        assert fmt.translate("Delays are unknown (x).") == "Delays are unknown (x)."
    finally:
        i18n.set_language("es")


def test_stream_kills_a_live_watch_on_cancel(fake_cli, scenario):
    scenario("hold")
    seen: list[asyncio.subprocess.Process] = []
    spawn = asyncio.create_subprocess_exec

    async def spawn_and_keep(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        seen.append(process)
        return process

    async def go():
        first = asyncio.Event()

        async def follow():
            async for line in bridge.stream("watch", "03081"):
                if line.data is not None:
                    first.set()

        task = asyncio.create_task(follow())
        await asyncio.wait_for(first.wait(), 5)
        assert seen[0].returncode is None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert seen[0].returncode is not None

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(asyncio, "create_subprocess_exec", spawn_and_keep)
        asyncio.run(go())


def test_stream_reads_indented_json_at_exit(fake_cli, scenario):
    scenario("indented")
    lines = asyncio.run(collect_lines("checkout", "MADRI", "BARCE"))
    assert lines[-1].result.data == {"status": "confirmed"}


async def collect_lines(*args):
    return [line async for line in bridge.stream(*args)]

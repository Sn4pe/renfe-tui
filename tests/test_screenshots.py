import asyncio
import os

import pytest

from renfe_tui import i18n, theme
from renfe_tui.app import Credits, Delays, Follow, RenfeTui, Results

OUT = os.environ.get("SHOTS_DIR")


@pytest.mark.skipif(not OUT, reason="solo para capturas")
@pytest.mark.parametrize("mode", ["claro", "oscuro"])
@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("size", [(80, 24), (100, 30), (120, 40)])
def test_shots(fake_cli, size, lang, mode):
    tag = f"{mode}-{lang}-{size[0]}x{size[1]}"
    i18n.set_language(lang)

    async def go():
        app = RenfeTui(animate=True, palette=theme.NAMES[mode])
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.wait_for_scheduled_animations()
            await pilot.pause()
            await pilot.click("#other")
            app.save_screenshot(f"{OUT}/calendar-{tag}.svg")
            await pilot.press("escape")
            await pilot.click("#after")
            app.save_screenshot(f"{OUT}/select-{tag}.svg")
            await pilot.press("escape")
            app.screen.query_one("#origin").focus()
            await pilot.press(*"madr")
            app.save_screenshot(f"{OUT}/home-{tag}.svg")
            app.push_screen(Results("MADRI", "BARCE", "2027-01-29", "", ""))
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.save_screenshot(f"{OUT}/results-{tag}.svg")
            app.push_screen(Follow("03081"))
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.save_screenshot(f"{OUT}/follow-{tag}.svg")
            app.push_screen(Delays())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.save_screenshot(f"{OUT}/delays-{tag}.svg")
            app.push_screen(Results("MADRI", "BARCE", "2027-01-20", "", ""))
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.click("#buy")
            app.save_screenshot(f"{OUT}/pay-{tag}.svg")
            await pilot.press("escape")
            app.push_screen(Credits())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.save_screenshot(f"{OUT}/credits-{tag}.svg")

    try:
        asyncio.run(go())
    finally:
        i18n.set_language("es")

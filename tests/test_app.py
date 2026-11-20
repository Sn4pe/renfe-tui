import asyncio
from datetime import date, timedelta

import pytest
from textual.widgets import DataTable, OptionList, Static

from renfe_tui.app import Follow, Home, RenfeTui, Results, today
from renfe_tui.art import Train

SIZE = (120, 40)


def run(scenario_body, size=SIZE):
    async def go():
        app = RenfeTui(animate=False)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario_body(app, pilot)

    asyncio.run(go())


async def finished(pilot, app):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


def test_search_flow(fake_cli):
    async def body(app, pilot):
        await pilot.press(*"madr")
        suggestions = app.screen.query_one("#suggestions", OptionList)
        assert suggestions.display and suggestions.option_count > 0
        await pilot.press("enter")
        await pilot.press(*"barcelona", "enter")
        assert app.screen.focused.id == "search"
        app.screen.set_day(date(2027, 1, 29))
        await pilot.press("enter")
        await finished(pilot, app)
        assert isinstance(app.screen, Results)
        table = app.screen.query_one(DataTable)
        assert table.row_count == 2
        assert "No disponible" in str(table.get_row_at(1)[5])
        assert "Básico" in text_of(app.screen, "#fares")
        assert fake_cli()[-1][:5] == ["search", "MADRI", "BARCE", "--date", "2027-01-29"]

        opened = []
        app.open_url = lambda url, **kw: opened.append(url)
        await pilot.click("#buy")
        await finished(pilot, app)
        assert opened == ["https://example.invalid/shop?o=MADRI&d=BARCE"]
        assert fake_cli()[-1] == ["open", "MADRI", "BARCE", "--date", "2027-01-29", "--train", "03091",
                                  "--no-browser"]
        assert "25 de enero de 2027" in text_of(app.screen, "#status")

    run(body)


def test_partial_results_show_rows_and_warning(fake_cli, scenario):
    scenario("partial")

    async def body(app, pilot):
        app.push_screen(Results("MADRI", "BARCE", "2027-01-29", "", ""))
        await finished(pilot, app)
        assert app.screen.query_one(DataTable).row_count == 2
        assert "bloqueado" in text_of(app.screen, "#status")

    run(body)


def test_follow_watches_and_shows_each_change(fake_cli):
    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        screen = app.screen
        assert fake_cli()[-1] == ["watch", "03081"]
        assert "20 min de retraso" in text_of(screen, "#delay")
        assert "Lleida" in text_of(screen, "#where")
        assert "sale a las 08:00 y llega a las 10:30" in text_of(screen, "#schedule")
        legs = text_of(screen, "#segments")
        assert "03081" in legs and "03181" in legs and "Zaragoza-Delicias" in legs
        assert "Siguiendo desde las" in text_of(screen, "#status")

    run(body)


def test_follow_r_starts_a_new_watch(fake_cli):
    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        await pilot.press("r")
        await finished(pilot, app)
        assert [call[0] for call in fake_cli()] == ["watch", "watch"]

    run(body)


def test_follow_reports_watch_events(fake_cli, scenario):
    scenario("events")

    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        assert "12 min de retraso" in text_of(app.screen, "#delay")
        assert "12 horas" in text_of(app.screen, "#status")

    run(body)


def test_follow_explains_an_ambiguous_ticket(fake_cli, scenario):
    scenario("ambiguous")

    async def body(app, pilot):
        app.push_screen(Follow("500"))
        await finished(pilot, app)
        assert "03000, 03100" in text_of(app.screen, "#status")

    run(body)


def test_follow_stops_when_blocked(fake_cli, scenario):
    scenario("blocked")

    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        assert "bloqueado" in text_of(app.screen, "#status")
        assert not app.screen.watching

    run(body)


def test_follow_reports_outage(fake_cli, scenario):
    scenario("outage")

    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        assert "no responde" in text_of(app.screen, "#status")

    run(body)


def test_delays_show_legs_and_filter_by_train(fake_cli, scenario):
    from renfe_tui.app import Delays

    async def body(app, pilot):
        app.push_screen(Delays())
        await finished(pilot, app)
        row = [str(cell) for cell in app.screen.query_one(DataTable).get_row_at(0)]
        assert "03181" in row[2] and "08:00 a 10:30" in row[5]
        scenario("none")
        await pilot.press("slash", *"9999", "enter")
        await finished(pilot, app)
        assert fake_cli()[-1] == ["delays", "9999"]
        assert "09999" in text_of(app.screen, "#status")
        await pilot.press("r")
        await finished(pilot, app)
        assert fake_cli()[-1] == ["delays", "9999"] and len(fake_cli()) == 3

    run(body)


def buy_flow(day):
    async def body(app, pilot):
        app.push_screen(Results("MADRI", "BARCE", day, "", ""))
        await finished(pilot, app)
        app.open_url = lambda url, **kw: app.opened.append(url)
        app.opened = []
        await pilot.click("#buy")
        return app.screen

    return body


def test_buy_runs_checkout_with_the_chosen_method(fake_cli):
    from renfe_tui.app import Checkout, PayWith

    async def body(app, pilot):
        screen = await buy_flow("2027-01-20")(app, pilot)
        assert isinstance(screen, PayWith)
        await pilot.press("down", "enter")
        await finished(pilot, app)
        assert isinstance(app.screen, Checkout)
        assert fake_cli()[-1] == ["checkout", "MADRI", "BARCE", "--date", "2027-01-20", "--train", "03091",
                                  "--method", "card"]
        assert "Elige la tarifa" in text_of(app.screen, "#progress")
        assert "confirmado la compra" in text_of(app.screen, "#status")
        await pilot.press("escape")
        assert isinstance(app.screen, Results)

    run(body)


def test_buy_without_confirmation_warns(fake_cli, scenario):
    scenario("unconfirmed")

    async def body(app, pilot):
        await buy_flow("2027-01-20")(app, pilot)
        await pilot.press("enter")
        await finished(pilot, app)
        assert "no ha confirmado" in text_of(app.screen, "#status")

    run(body)


def test_buy_without_the_checkout_extra_opens_the_site(fake_cli, scenario):
    scenario("missing")

    async def body(app, pilot):
        await buy_flow("2027-01-20")(app, pilot)
        await pilot.press("enter")
        await finished(pilot, app)
        await finished(pilot, app)
        assert [call[0] for call in fake_cli()][-2:] == ["checkout", "open"]
        assert app.opened == ["https://example.invalid/shop?o=MADRI&d=BARCE"]
        assert "--with playwright" in text_of(app.screen, "#status")

    run(body)


def test_checkout_screen_stays_while_chrome_is_open(fake_cli):
    from renfe_tui.app import Checkout, Help, Trip

    async def body(app, pilot):
        screen = Checkout(Trip("MADRI", "BARCE", "2027-01-20", "03091", ""), None)
        app.push_screen(screen)
        await finished(pilot, app)
        screen.running = True
        await pilot.press("escape")
        app.go_home(Help)
        app.restart("en", app.palette)
        await app.action_quit()
        assert app.screen is screen and app.return_value is None and app.is_running
        screen.running = False
        await pilot.press("escape")
        assert app.screen is not screen

    run(body)


def test_train_parks_on_key():
    async def go():
        app = RenfeTui(animate=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            train = app.screen.query_one(Train)
            assert isinstance(app.screen, Home) and train.moving
            await pilot.press("x")
            assert not train.moving
            assert train.offset == train.parked()

    asyncio.run(go())


def test_small_terminal_arrows_pick_second_suggestion(fake_cli):
    async def go():
        app = RenfeTui(animate=False)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert callable(app.screen.animate)
            await pilot.press(*"madrid", "down", "enter")
            suggestions = app.screen.query_one("#suggestions", OptionList)
            assert app.screen.codes["origin"].code != "MADRI"
            assert not suggestions.display
            assert app.screen.focused.id == "destination"

    asyncio.run(go())


def test_reload_ignored_while_loading(fake_cli, tmp_path, monkeypatch):
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\necho x >> \"$FAKE_RENFE_LOG\"\nsleep 1\n")
    slow.chmod(0o755)
    monkeypatch.setenv("RENFE_TUI_CLI", str(slow))

    async def body(app, pilot):
        app.push_screen(Results("MADRI", "BARCE", "2027-01-29", "", ""))
        await pilot.pause()
        await pilot.press("r", "r", "r")
        await finished(pilot, app)
        assert len(fake_cli.path.read_text().splitlines()) == 1

    run(body)


def test_swap_and_day_buttons(fake_cli):
    async def body(app, pilot):
        home = app.screen
        await pilot.press(*"madr", "enter", *"barcelona", "enter")
        await pilot.click("#swap")
        assert home.query_one("#origin").value.startswith("Barcelona")
        assert home._station("origin") == "BARCE" and home._station("destination") == "MADRI"
        await pilot.click("#tomorrow")
        assert home.day == today() + timedelta(days=1)
        assert home.query_one("#tomorrow").has_class("selected")
        assert not home.query_one("#today").has_class("selected")

    run(body)


def test_credits_mention_the_cli(fake_cli):
    async def body(app, pilot):
        await pilot.click("#credits")
        page = " ".join(str(w.render()) for w in app.screen.query(Static))
        assert "renfe-cli" in page and "luisgonzaleznf" in page and "No oficial" in page
        opened = []
        app.open_url = lambda url, **kw: opened.append(url)
        app.screen.query(".link")[1].press()
        await pilot.pause()
        assert opened == ["https://github.com/luisgonzaleznf/renfe-cli"]

    run(body)


def test_follow_in_plain_spanish_when_off_map(fake_cli, tmp_path, monkeypatch):
    async def body(app, pilot):
        app.push_screen(Follow("03081"))
        await finished(pilot, app)
        assert "Va con 20 min de retraso" in text_of(app.screen, "#delay")
        screen = app.screen
        screen.show({"train": "03081", "on_map": False, "delay_minutes": None, "next_station": None,
                     "notice": "Train 03081 isn't on Renfe's live map, which lists long- and medium-distance "
                               "trains only while they run: it may not have left yet, may have arrived or been "
                               "cancelled, or isn't one of those trains. Its delay is unknown, not zero."}, "10:00")
        assert "no está circulando" in text_of(screen, "#delay")
        assert "no aparece ahora en circulación" in text_of(screen, "#status")

    run(body)


class WatchedTui(RenfeTui):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.arrival = asyncio.Event()

    def on_train_arrived(self) -> None:
        self.arrival.set()


def test_train_arrives_by_itself():
    async def go():
        app = WatchedTui(animate=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            train = app.screen.query_one(Train)
            assert train.moving
            await asyncio.wait_for(app.arrival.wait(), 5)
            assert not train.moving
            assert train.offset == train.parked() > 0

    asyncio.run(go())


def test_hidden_train_waits_until_it_has_room():
    async def go():
        app = WatchedTui(animate=True)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            train = app.screen.query_one(Train)
            assert not train.display and not train.moving and train.pending
            await pilot.resize_terminal(120, 40)
            await asyncio.wait_for(app.arrival.wait(), 5)
            assert train.display and not train.pending
            assert train.offset == train.parked() > 0

    asyncio.run(go())


def test_calendar_picks_a_day_and_keeps_to_the_sale_window(fake_cli):
    from renfe_tui.calendar import Calendar, DatePicker

    async def body(app, pilot):
        home = app.screen
        await pilot.click("#other")
        assert isinstance(app.screen, DatePicker)
        calendar = app.screen.query_one(Calendar)
        await pilot.press("left")
        assert calendar.cursor == today()
        await pilot.press("right", "down", "enter")
        assert app.screen is home
        assert home.day == today() + timedelta(days=8)
        assert home.query_one("#other").has_class("selected")

    run(body)


def test_times_come_from_the_selects(fake_cli):
    async def body(app, pilot):
        home = app.screen
        await pilot.press(*"madr", "enter", *"barcelona", "enter")
        home.query_one("#after").value = "08:30"
        await pilot.click("#search")
        await finished(pilot, app)
        assert fake_cli()
        args = fake_cli()[-1]
        assert args[args.index("--after") + 1] == "08:30"
        assert "--arrive-by" not in args

    run(body)


def test_english(fake_cli):
    from renfe_tui import i18n

    i18n.set_language("en")
    try:
        async def body(app, pilot):
            app.push_screen(Follow("03081"))
            await finished(pilot, app)
            assert "20 min late" in text_of(app.screen, "#delay")
            assert "Next stop: Lleida" in text_of(app.screen, "#where")

        run(body)
    finally:
        i18n.set_language("es")


def test_calendar_mouse_hover_and_click(fake_cli):
    from renfe_tui.calendar import CELL, Calendar

    async def body(app, pilot):
        home = app.screen
        await pilot.click("#other")
        calendar = app.screen.query_one(Calendar)
        target = today() + timedelta(days=1)
        if target.month != today().month:
            await pilot.click(Calendar, offset=(calendar.size.width - 1, 0))
        row, col = next((r, c) for r, week in enumerate(calendar.weeks()) for c, d in enumerate(week) if d == target)
        where = (col * CELL + 2, row + 2)
        await pilot.hover(Calendar, offset=where)
        assert calendar.hover == target
        await pilot.hover(Calendar, offset=(1, 1))
        assert calendar.hover is None
        await pilot.click(Calendar, offset=where)
        assert app.screen is home and home.day == target

    run(body)


def test_palette_is_localized_and_switches_language(fake_cli):
    from textual.command import CommandPalette

    from renfe_tui import theme

    async def go():
        app = RenfeTui(animate=False, palette=theme.DARK)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            titles = [command.title for command in app.get_system_commands(app.screen)]
            assert titles[0] == "Language: English"
            assert "Tema claro" in titles and "Salir" in titles and "Theme" not in titles
            await pilot.press("ctrl+p")
            palette = app.screen
            assert isinstance(palette, CommandPalette)
            assert palette.query_one("Input").placeholder == "Busca una acción…"
            await pilot.press(*"English", "enter")
        assert app.return_value == ["--lang", "en", "--theme", "dark", "--no-anim"]

    asyncio.run(go())


def test_footer_palette_label_is_translated(fake_cli):
    from textual.widgets import Footer

    async def body(app, pilot):
        footer = app.screen.query_one(Footer)
        labels = " ".join(str(w.render()) for w in footer.query("*"))
        assert "acciones" in labels and "palette" not in labels
        assert "^p" in labels

    run(body)


def test_time_menu_footer_is_translated(fake_cli):
    from textual.widgets import Footer

    async def body(app, pilot):
        await pilot.click("#after")
        labels = " ".join(str(w.render()) for w in app.screen.query_one(Footer).query("*"))
        assert "cerrar" in labels and "Dismiss" not in labels

    run(body)


def test_scrollbars_use_the_theme_everywhere(fake_cli):
    from renfe_tui.app import Delays, PayWith

    async def body(app, pilot):
        panel = app.current_theme.to_color_system().generate()["panel"]
        for screen in (Delays(), PayWith()):
            app.push_screen(screen)
            await finished(pilot, app)
            for widget in [screen, *screen.query("*")]:
                assert widget.styles.scrollbar_background.hex.lower() == panel.lower(), widget
                assert widget.styles.scrollbar_corner_color.hex.lower() == panel.lower(), widget
        await app.pop_screen()
        await app.pop_screen()
        await pilot.click("#after")
        overlay = app.screen.query_one("TimeOverlay")
        assert overlay.styles.scrollbar_background.hex.lower() == panel.lower()

    run(body)


@pytest.mark.parametrize("size", [(80, 24), (100, 30), (120, 34), (120, 40)])
def test_home_never_scrolls(fake_cli, size):
    async def body(app, pilot):
        home = app.screen
        assert home.max_scroll_y == 0
        for button in home.query("#more Button"):
            assert button.region.right <= size[0] - 2, button
        await pilot.press(*"madr")
        assert home.query_one("#suggestions").display
        assert home.max_scroll_y == 0 and not home.show_vertical_scrollbar
        await pilot.click("#after")
        assert home.max_scroll_y == 0 and not home.show_vertical_scrollbar

    run(body, size=size)

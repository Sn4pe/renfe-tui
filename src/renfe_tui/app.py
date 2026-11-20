import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from renfe import config as cli_config, stations as stations_mod
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Label, OptionList, Select, Static
from textual.widgets._select import SelectCurrent, SelectOverlay
from textual.widgets.option_list import Option

from . import bridge, format as fmt
from .art import Train, wordmark
from .calendar import DatePicker
from .i18n import lang, t
from .theme import DARK, LIGHT, PURPLE, Palette, pick

CLI_URL = "https://github.com/luisgonzaleznf/renfe-cli"
TUI_URL = "https://github.com/Sn4pe/renfe-tui"
TEXTUAL_URL = "https://github.com/Textualize/textual"
TRAIN_MIN_HEIGHT = 28
MAX_DAYS_AHEAD = 365
TIMES = [f"{h:02d}:{m:02d}" for h in range(5, 24) for m in (0, 30)]


def busy(node) -> bool:
    return any(worker.node is node and worker.is_running for worker in node.app.workers)


def today() -> date:
    return datetime.now(fmt.MADRID).date()


class TimeOverlay(SelectOverlay):
    BINDINGS = [Binding("escape", "dismiss", t("b_close_menu"))]


class TimeSelect(Select[str]):
    def compose(self) -> ComposeResult:
        yield SelectCurrent(self.prompt)
        yield TimeOverlay(type_to_search=self._type_to_search).data_bind(compact=Select.compact)


class Home(Screen):
    BINDINGS = [
        Binding("ctrl+r", "delays", t("b_delays")),
        Binding("ctrl+t", "follow", t("b_mytrain")),
        Binding("f1", "help", t("b_help")),
        Binding("ctrl+q", "app.quit", t("b_quit")),
    ]

    def __init__(self, animate: bool):
        super().__init__()
        self.animate_train = animate
        self.stations = stations_mod.bundled()
        self.codes: dict[str, stations_mod.Station] = {}
        self.day = today()

    def compose(self) -> ComposeResult:
        muted = self.app.palette.muted
        times = [(time, time) for time in TIMES]
        with Vertical(id="hero"):
            yield Static(wordmark(), id="wordmark")
            yield Static(Text(t("tagline"), style=muted), id="tagline")
            yield Train(animate=self.animate_train)
        with Center():
            with Vertical(id="form"):
                with Horizontal(classes="row"):
                    yield Label(t("from"), classes="field")
                    yield Input(placeholder=t("station_placeholder"), id="origin", classes="station")
                    yield Button("⇄", id="swap", classes="quiet", tooltip=t("swap_tip"))
                with Horizontal(classes="row"):
                    yield Label(t("to"), classes="field")
                    yield Input(placeholder=t("station_placeholder"), id="destination", classes="station")
                yield OptionList(id="suggestions")
                with Horizontal(classes="row"):
                    yield Label(t("day"), classes="field")
                    yield Button(t("today"), id="today", classes="choice")
                    yield Button(t("tomorrow"), id="tomorrow", classes="choice")
                    yield Button(t("other_day"), id="other", classes="choice")
                    yield Static(id="day-label")
                with Horizontal(classes="row"):
                    yield Label(t("hour"), classes="field")
                    yield Label(t("leave_after"), classes="time-label")
                    yield TimeSelect(times, prompt=t("any_time"), id="after", compact=True)
                    yield Label(t("arrive_by"), classes="time-label")
                    yield TimeSelect(times, prompt=t("any_time"), id="arrive_by", compact=True)
                with Horizontal(classes="row"):
                    yield Static(classes="field")
                    yield Button(t("search"), id="search", classes="primary")
                yield Static(id="message")
            with Horizontal(id="more"):
                yield Button(t("where_train"), id="follow", classes="quiet")
                yield Button(t("delays_now"), id="delays", classes="quiet")
                yield Button(t("help"), id="help", classes="quiet")
                yield Button(t("credits"), id="credits", classes="quiet")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#suggestions").display = False
        self.set_day(today())
        self.query_one("#origin").focus()

    def on_resize(self, event: events.Resize) -> None:
        self.query_one(Train).display = event.size.height >= TRAIN_MIN_HEIGHT

    def set_day(self, day: date) -> None:
        self.day = day
        offset = (day - today()).days
        chosen = {0: "today", 1: "tomorrow"}.get(offset, "other")
        for button in self.query(".choice").results(Button):
            button.set_class(button.id == chosen, "selected")
        label = Text(fmt.long_day_human(day.isoformat()), style=self.app.palette.muted)
        self.query_one("#day-label", Static).update(label)

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        suggestions = self.query_one("#suggestions", OptionList)
        if suggestions.display and isinstance(focused, Input) and focused.id in ("origin", "destination"):
            if event.key == "down":
                suggestions.action_cursor_down()
                event.stop()
            elif event.key == "up":
                suggestions.action_cursor_up()
                event.stop()

    @on(Input.Changed, "#origin, #destination")
    def suggest(self, event: Input.Changed) -> None:
        picked = self.codes.get(event.input.id)
        if picked and picked.name == event.value:
            return
        self.codes.pop(event.input.id, None)
        suggestions = self.query_one("#suggestions", OptionList)
        suggestions.clear_options()
        found = stations_mod.find(event.value, self.stations, 6) if event.value.strip() else []
        muted = self.app.palette.muted
        for s in found:
            where = f"  {s.province}" if s.province and s.province not in s.name else ""
            suggestions.add_option(Option(Text.assemble(s.name, (where, muted)), id=s.code))
        suggestions.display = bool(found)
        if found:
            suggestions.highlighted = 0

    def choose(self, field: str, code: str) -> None:
        chosen = next(s for s in self.stations if s.code == code)
        self.codes[field] = chosen
        self.query_one(f"#{field}", Input).value = chosen.name
        self.query_one("#suggestions").display = False
        self.query_one("#destination" if field == "origin" else "#search").focus()

    @on(Input.Submitted, "#origin, #destination")
    def pick(self, event: Input.Submitted) -> None:
        suggestions = self.query_one("#suggestions", OptionList)
        if suggestions.display and suggestions.highlighted is not None:
            self.choose(event.input.id, suggestions.get_option_at_index(suggestions.highlighted).id)
        else:
            self.query_one("#destination" if event.input.id == "origin" else "#search").focus()

    @on(OptionList.OptionSelected, "#suggestions")
    def clicked(self, event: OptionList.OptionSelected) -> None:
        field = "destination" if self.codes.get("origin") and not self.codes.get("destination") else "origin"
        if isinstance(self.app.focused, Input) and self.app.focused.id in ("origin", "destination"):
            field = self.app.focused.id
        self.choose(field, event.option.id)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "today":
                self.set_day(today())
            case "tomorrow":
                self.set_day(today() + timedelta(days=1))
            case "other":
                self.pick_day()
            case "swap":
                self.swap()
            case "search":
                self.search()
            case "follow":
                self.action_follow()
            case "delays":
                self.action_delays()
            case "help":
                self.action_help()
            case "credits":
                self.app.push_screen(Credits())

    def pick_day(self) -> None:
        first = today()

        def done(day: date | None) -> None:
            if day:
                self.set_day(day)

        self.app.push_screen(DatePicker(self.day, first, first + timedelta(days=MAX_DAYS_AHEAD)), done)

    def swap(self) -> None:
        origin, destination = self.query_one("#origin", Input), self.query_one("#destination", Input)
        picked = self.codes.pop("origin", None), self.codes.pop("destination", None)
        origin.value, destination.value = destination.value, origin.value
        for field, station in zip(("destination", "origin"), picked):
            if station:
                self.codes[field] = station
        self.query_one("#suggestions").display = False

    def _station(self, field: str) -> str:
        if picked := self.codes.get(field):
            return picked.code
        text = self.query_one(f"#{field}", Input).value.strip()
        found = stations_mod.find(text, self.stations, 1) if text else []
        return found[0].code if found else text

    def _time(self, field: str) -> str:
        value = self.query_one(f"#{field}", Select).value
        return value if isinstance(value, str) else ""

    def say(self, text: str) -> None:
        self.query_one("#message", Static).update(Text(text, style=self.app.palette.warning))

    def search(self) -> None:
        origin, destination = self._station("origin"), self._station("destination")
        if not origin or not destination:
            self.say(t("need_stations"))
            return
        self.say("")
        self.app.push_screen(Results(origin, destination, self.day.isoformat(), self._time("after"),
                                     self._time("arrive_by")))

    def action_delays(self) -> None:
        self.app.push_screen(Delays())

    def action_help(self) -> None:
        self.app.push_screen(Help())

    def action_follow(self) -> None:
        def go(number: str | None) -> None:
            if number:
                self.app.push_screen(Follow(number))

        self.app.push_screen(AskTrain(), go)


class AskTrain(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", t("b_cancel"))]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(t("ask_title"), classes="title")
            yield Static(Text(t("ask_hint"), style=self.app.palette.muted))
            yield Input(placeholder=t("ask_placeholder"), id="number", restrict=r"[0-9 ]*")
            with Horizontal(classes="buttons"):
                yield Button(t("ask_ok"), id="ok", classes="primary")
                yield Button(t("cancel"), id="cancel", classes="quiet")

    @on(Input.Submitted)
    @on(Button.Pressed, "#ok")
    def done(self) -> None:
        self.dismiss(self.query_one("#number", Input).value.strip() or None)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class Results(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", t("b_new_search")),
        Binding("c", "shop", t("b_buy")),
        Binding("s", "follow", t("b_follow")),
        Binding("r", "reload", t("b_refresh")),
    ]

    def __init__(self, origin: str, destination: str, day: str, after: str, arrive_by: str):
        super().__init__()
        self.args = bridge.search_args(origin, destination, day, after, arrive_by)
        self.origin, self.destination, self.day = origin, destination, day
        self.payload: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="route")
        yield Static(t("searching"), id="status")
        yield DataTable(id="trains", cursor_type="row", zebra_stripes=False)
        with Horizontal(id="detail"):
            yield Static(id="fares")
            with Vertical(id="detail-actions"):
                yield Button(t("buy"), id="buy", classes="primary")
                yield Button(t("follow_this"), id="follow", classes="quiet")
                yield Button(t("new_search"), id="back", classes="quiet")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*t("cols"))
        self.query_one("#detail").display = False
        self.load()

    def action_reload(self) -> None:
        if not busy(self):
            self.load()

    @work(exclusive=True)
    async def load(self) -> None:
        self.query_one("#status", Static).update(Text(t("searching"), style=self.app.palette.muted))
        result = await bridge.run(*self.args)
        self.show(result)

    def show(self, result: bridge.Result) -> None:
        palette = self.app.palette
        status = self.query_one("#status", Static)
        table = self.query_one(DataTable)
        table.clear()
        data = result.data
        if data is None:
            status.update(Text(fmt.error_text(result.error), style=palette.error))
            return
        self.payload = data
        route = Text.assemble((fmt.station(data["origin"]), "bold"), ("  ›  ", PURPLE),
                              (fmt.station(data["destination"]), "bold"),
                              (f"    {fmt.long_day_human(data['date'])}", palette.muted))
        self.query_one("#route", Static).update(route)
        for i, train in enumerate(data["trains"]):
            fares = train.get("fares") or []
            if fares:
                cheapest = fmt.price(fares[0]["price"])
            else:
                cheapest = t("not_available") if train["available"] is False else ""
            late = train.get("delay_minutes")
            name = train.get("type") or ""
            row = [fmt.clock(train["departure"]), fmt.clock(train["arrival"]), fmt.duration(train["duration_minutes"]),
                   t("direct") if not train["changes"] else str(train["changes"]),
                   f"{name} {train['service']}".strip(), cheapest, fmt.delay(late)]
            style = palette.muted if train["available"] is False else (palette.warning if late else "")
            table.add_row(*(Text(cell, style=style) for cell in row), key=str(i))
        notes = [fmt.translate(data.get("notice"))] if data.get("notice") else []
        if result.error:
            notes.append(fmt.error_text(result.error))
        notes.insert(0, t("count_hint", n=data["count"]) if data["trains"] else t("no_trains"))
        status.update(Text("  ".join(notes), style=palette.warning if len(notes) > 1 else palette.muted))
        self.query_one("#detail").display = bool(data["trains"])
        if data["trains"]:
            table.focus()
            self.detail()

    def selected(self) -> dict | None:
        if not self.payload or not self.payload["trains"]:
            return None
        row = self.query_one(DataTable).cursor_row
        trains = self.payload["trains"]
        return trains[row] if 0 <= row < len(trains) else None

    @on(DataTable.RowHighlighted)
    def detail(self) -> None:
        train = self.selected()
        if not train:
            return
        muted = self.app.palette.muted
        text = Text()
        text.append(f"{train.get('type') or t('train')} {train['service']}\n", style="bold")
        text.append(t("span", dep=fmt.clock(train["departure"]), arr=fmt.clock(train["arrival"]),
                      dur=fmt.duration(train["duration_minutes"])) + "\n\n", style=muted)
        fares = train.get("fares") or []
        for fare in fares:
            text.append(f"{fare['name']:<18}", style=muted)
            text.append(f"{fmt.price(fare['price'])}\n")
        if not fares:
            text.append(t("not_on_sale") if train["available"] is False else t("no_fares"), style=muted)
        self.query_one("#fares", Static).update(text)

    @on(Button.Pressed, "#buy")
    def action_shop(self) -> None:
        train = self.selected()
        if not train:
            return
        trip = Trip(self.origin, self.destination, self.day, train["service"],
                    ((self.payload or {}).get("shop") or {}).get("url", ""))
        if date.fromisoformat(self.day) >= cli_config.NSV_FIRST_SALE_DATE:
            self.app.push_screen(Checkout(trip, None))
            return

        def chosen(method: str | None) -> None:
            if method is not None:
                self.app.push_screen(Checkout(trip, method or None))

        self.app.push_screen(PayWith(), chosen)

    @on(Button.Pressed, "#follow")
    def action_follow(self) -> None:
        train = self.selected()
        if train:
            self.app.push_screen(Follow(train["service"].split("+")[0].strip()))

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


@dataclass(frozen=True)
class Trip:
    origin: str
    destination: str
    day: str
    service: str
    shop: str


class PayWith(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", t("b_cancel"))]

    def compose(self) -> ComposeResult:
        methods = [m for m in t("methods") if m != "apple-pay" or sys.platform == "darwin"]
        with Vertical(classes="dialog"):
            yield Label(t("buy_title"), classes="title")
            yield Static(Text(t("buy_hint"), style=self.app.palette.muted))
            yield OptionList(*(Option(t("methods")[m], id=m) for m in methods), Option(t("just_open"), id=""),
                             id="methods")
            with Horizontal(classes="buttons"):
                yield Button(t("cancel"), id="cancel", classes="quiet")

    @on(OptionList.OptionSelected, "#methods")
    def picked(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id or "")

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class Checkout(Screen):
    BINDINGS = [Binding("escape", "leave", t("b_back"))]

    def __init__(self, trip: Trip, method: str | None):
        super().__init__()
        self.trip, self.method = trip, method
        self.running = False

    def compose(self) -> ComposeResult:
        yield Static(Text(t("checkout_title", train=self.trip.service), style="bold"), id="route")
        yield Static(id="progress")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        if self.method:
            self.buy()
        else:
            self.open_site()

    def action_leave(self) -> None:
        if not self.app.buying():
            self.app.pop_screen()

    def say(self, text: str, style: str = "") -> None:
        self.query_one("#status", Static).update(Text(text, style=style or self.app.palette.muted))

    @work(exclusive=True)
    async def open_site(self, note: str = "") -> None:
        trip = self.trip
        result = await bridge.run("open", trip.origin, trip.destination, "--date", trip.day, "--train",
                                  trip.service, "--no-browser")
        data = result.data or {}
        url = (data.get("shop") or {}).get("url") or trip.shop
        if not url:
            self.say(fmt.error_text(result.error), self.app.palette.error)
            return
        self.app.open_url(url)
        lines = [note] if note else []
        lines.append(t("shop_body", train=trip.service))
        if data.get("notice"):
            lines.append(fmt.translate(data["notice"]))
        cutoff = cli_config.NSV_FIRST_SALE_DATE
        if date.fromisoformat(trip.day) >= cutoff:
            lines.insert(0, t("buy_after_cutoff", day=fmt.full_date(cutoff)))
        self.say("\n\n".join(lines))

    @work(exclusive=True)
    async def buy(self) -> None:
        trip, palette = self.trip, self.app.palette
        self.running = True
        self.say(t("checkout_running"))
        progress: list[str] = []
        result = None
        async for line in bridge.stream("checkout", trip.origin, trip.destination, "--date", trip.day, "--train",
                                        trip.service, "--method", self.method or "paypal"):
            if line.progress:
                progress.append(fmt.translate(line.progress))
                self.query_one("#progress", Static).update(Text("\n\n".join(progress)))
            elif line.result is not None:
                result = line.result
        self.running = False
        if result is None:
            return
        data, error = result.data, result.error
        if data is None:
            if error and "checkout extra" in (error.get("message") or ""):
                self.open_site(t("checkout_missing"))
                return
            self.say(fmt.error_text(error), palette.error)
            return
        method = t("methods").get(data.get("selected_method") or "", "")
        paid = t("selected_method", method=method, total=data["total"]) + "\n\n" if data.get("total") else ""
        match data.get("status"):
            case "confirmed":
                self.say(paid + t("checkout_confirmed"), palette.success)
            case "handed_off":
                self.say(t("checkout_handed_off", browser=data.get("browser", "")) + "\n\n"
                         + fmt.translate(data.get("next")))
            case _:
                self.say(paid + t("checkout_unconfirmed"), palette.warning)


class Delays(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", t("b_back")),
        Binding("s", "follow", t("b_follow")),
        Binding("r", "reload", t("b_refresh")),
        Binding("slash", "filter", t("b_filter"), key_display="/"),
    ]

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.train = ""

    def compose(self) -> ComposeResult:
        yield Static(Text(t("delays_title"), style="bold"), id="route")
        yield Input(placeholder=t("filter_placeholder"), id="train-filter", restrict=r"[0-9]*")
        yield Static(t("checking"), id="status")
        yield DataTable(id="delays", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*t("delay_cols"))
        self.load()

    def action_reload(self) -> None:
        if not busy(self):
            self.load()

    def action_filter(self) -> None:
        self.query_one("#train-filter", Input).focus()

    @on(Input.Submitted, "#train-filter")
    def filtered(self, event: Input.Submitted) -> None:
        self.train = event.value.strip()
        self.load()

    @work(exclusive=True)
    async def load(self) -> None:
        palette = self.app.palette
        self.query_one("#status", Static).update(Text(t("checking"), style=palette.muted))
        result = await bridge.run("delays", *([self.train] if self.train else []))
        status, table = self.query_one("#status", Static), self.query_one(DataTable)
        table.clear()
        data = result.data
        if data is None:
            status.update(Text(fmt.error_text(result.error), style=palette.error))
            return
        self.rows = data["trains"]
        for row in self.rows:
            nxt = row.get("next_station") or {}
            others = " ".join(leg["train"] for leg in row.get("number_segments") or [] if leg["train"] != row["train"])
            timetable = ""
            if row.get("scheduled_departure") and row.get("scheduled_arrival"):
                timetable = t("span_short", dep=fmt.clock(row["scheduled_departure"]),
                              arr=fmt.clock(row["scheduled_arrival"]))
            table.add_row(Text(fmt.delay(row["delay_minutes"]), style=palette.warning), row["train"], others,
                          fmt.station(row.get("origin")), fmt.station(row.get("destination")), timetable,
                          f"{fmt.station(nxt)} {fmt.clock(nxt.get('expected_arrival'))}".strip())
        summary = t("delays_summary", mapped=data["mapped_trains"], delayed=data["delayed"],
                    at=fmt.clock(data.get("map_updated")))
        if self.train:
            number = data.get("requested_train") or self.train
            summary = t("filter_some", n=number) if self.rows else t("filter_none", n=number)
        notes = [summary] + ([fmt.translate(data["notice"])] if data.get("notice") else [])
        status.update(Text("  ".join(notes), style=palette.muted))
        table.focus()

    def action_follow(self) -> None:
        row = self.query_one(DataTable).cursor_row
        if 0 <= row < len(self.rows):
            self.app.push_screen(Follow(self.rows[row]["train"]))


def now_clock() -> str:
    return datetime.now(fmt.MADRID).strftime("%H:%M")


def segments_text(segments: list[dict], muted: str) -> Text:
    text = Text()
    if not segments:
        return text
    text.append(t("segments_title") + "\n", style="bold")
    for leg in segments:
        text.append(t("segment", train=leg["train"], origin=fmt.station(leg.get("origin")),
                      destination=fmt.station(leg.get("destination")), dep=fmt.clock(leg.get("scheduled_departure")),
                      arr=fmt.clock(leg.get("scheduled_arrival"))) + "\n", style=muted)
    return text


class Follow(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", t("b_back")),
        Binding("r", "check", t("b_check")),
    ]

    def __init__(self, number: str):
        super().__init__()
        self.number = number
        self.started = ""
        self.watching = False

    def compose(self) -> ComposeResult:
        yield Static(Text(f"{t('train')} {self.number}", style="bold"), id="route")
        yield Static(id="delay")
        yield Static(id="where")
        yield Static(id="schedule")
        yield Static(id="segments")
        yield Static(t("checking"), id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.follow()

    def action_check(self) -> None:
        self.follow()

    @work(exclusive=True)
    async def follow(self) -> None:
        self.started, self.watching = now_clock(), True
        status = self.query_one("#status", Static)
        status.update(Text(t("checking"), style=self.app.palette.muted))
        async for line in bridge.stream("watch", self.number):
            if line.data is not None:
                self.event(line.data)
            elif line.result is not None:
                self.watching = False
                if line.result.error:
                    status.update(Text(f"{fmt.error_text(line.result.error)}  ({now_clock()})",
                                       style=self.app.palette.error))

    def event(self, data: dict) -> None:
        palette = self.app.palette
        status = self.query_one("#status", Static)
        match data.get("event"):
            case "map_unreachable":
                status.update(Text(f"{t('map_down')}  ({now_clock()})", style=palette.warning))
            case "ended":
                status.update(Text(t("watch_ended"), style=palette.muted))
            case _:
                self.show(data, now_clock())

    def show(self, data: dict, now: str) -> None:
        palette = self.app.palette
        route = Text(f"{t('train')} {data['train']}", style="bold")
        if data.get("requested_train") and data["requested_train"] != data["train"]:
            route.append(t("ticket_note", n=data["requested_train"]), style=palette.muted)
        if data.get("origin"):
            route.append_text(Text.assemble(("    ", ""), fmt.station(data["origin"]), ("  ›  ", PURPLE),
                                            fmt.station(data["destination"])))
        self.query_one("#route", Static).update(route)
        if data["on_map"]:
            late = data["delay_minutes"]
            colour = palette.warning if late and late > 0 else palette.success
            big = Text(fmt.delay_sentence(late), style=f"bold {colour}")
        else:
            big = Text(t("not_running"), style=f"bold {palette.muted}")
        self.query_one("#delay", Static).update(big)
        nxt = data.get("next_station")
        where = Text()
        if nxt:
            where.append(t("next_stop", name=fmt.station(nxt), at=fmt.clock(nxt.get("expected_arrival"))))
        self.query_one("#where", Static).update(where)
        schedule = Text(style=palette.muted)
        if data.get("scheduled_departure") and data.get("scheduled_arrival"):
            schedule.append(t("scheduled", dep=fmt.clock(data["scheduled_departure"]),
                              arr=fmt.clock(data["scheduled_arrival"])))
        self.query_one("#schedule", Static).update(schedule)
        self.query_one("#segments", Static).update(segments_text(data.get("number_segments") or [], palette.muted))
        lines = []
        if data.get("schedule_match") == "ambiguous" and data.get("matching_trains"):
            lines.append(t("ambiguous", trains=", ".join(data["matching_trains"])))
        elif data.get("schedule_match") == "unavailable":
            lines.append(t("schedule_unavailable"))
        if data.get("notice"):
            lines.append(fmt.translate(data["notice"]))
        lines.append(t("checked", start=self.started or now, at=now))
        self.query_one("#status", Static).update(Text("\n\n".join(lines), style=palette.muted))


class Info(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", t("b_back"))]
    TITLE_KEY = ""

    def parts(self) -> ComposeResult:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="page"):
            yield Static(Text(t(self.TITLE_KEY), style=f"bold {PURPLE}"), classes="page-title")
            yield from self.parts()
            with Horizontal(classes="buttons"):
                yield Button(t("b_back").capitalize(), id="back", classes="primary")
        yield Footer()

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


class Help(Info):
    TITLE_KEY = "help_title"

    def parts(self) -> ComposeResult:
        muted = self.app.palette.muted
        for title, body in t("help_sections"):
            yield Static(Text.assemble((f"{title}\n", "bold"), (body, muted)), classes="section")


class Credits(Info):
    TITLE_KEY = "credits_title"
    LINKS = {"renfe-tui": TUI_URL, "renfe-cli": CLI_URL, "Textual": TEXTUAL_URL}

    def parts(self) -> ComposeResult:
        palette, theme = self.app.palette, self.app.current_theme
        yield Train(animate=False, classes="credits-train")
        for name, author, body in t("credit_entries"):
            with Horizontal(classes="credit"):
                yield Static(Text.assemble((name, f"bold {theme.primary}"), (f"  {t('by')} ", palette.muted),
                                           (author, f"bold {theme.accent}"), "\n", (body, palette.muted)),
                             classes="credit-text")
                yield Button(t("on_github", name=name), classes="quiet link", name=self.LINKS[name])
        yield Static(Text.assemble((t("unofficial_title") + "\n", f"bold {theme.warning}"),
                                   (t("unofficial"), palette.muted)), classes="section unofficial")

    @on(Button.Pressed, ".link")
    def open_link(self, event: Button.Pressed) -> None:
        self.app.open_url(event.button.name)


class RenfeTui(App[list[str] | None]):
    CSS_PATH = Path(__file__).with_name("app.tcss")
    TITLE = "renfe-tui"
    BINDINGS = [Binding("ctrl+p", "command_palette", t("b_palette"), show=False, priority=True,
                        tooltip=t("palette_placeholder"))]

    def __init__(self, animate: bool = True, palette: Palette | None = None):
        super().__init__()
        self.animate_train = animate
        self.palette = palette or pick()

    def on_mount(self) -> None:
        self.register_theme(self.palette.theme)
        self.theme = self.palette.theme.name
        self.push_screen(Home(self.animate_train))

    def action_command_palette(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(CommandPalette(id="--command-palette", placeholder=t("palette_placeholder")))

    def buying(self) -> bool:
        if any(isinstance(screen, Checkout) and screen.running for screen in self.screen_stack):
            self.notify(t("checkout_wait"), timeout=6)
            return True
        return False

    async def action_quit(self) -> None:
        if not self.buying():
            await super().action_quit()

    def restart(self, language: str, palette: Palette) -> None:
        if self.buying():
            return
        self.exit(["--lang", language, "--theme", "dark" if palette is DARK else "light", "--no-anim"])

    def go_home(self, screen: type[Screen]) -> None:
        if self.buying():
            return
        while len(self.screen_stack) > 2:
            self.pop_screen()
        self.push_screen(screen())

    def get_system_commands(self, screen: Screen):
        other = "en" if lang() == "es" else "es"
        yield SystemCommand(t("cmd_language"), t("cmd_language_help"), lambda: self.restart(other, self.palette))
        if self.palette is DARK:
            yield SystemCommand(t("cmd_light"), t("cmd_light_help"), lambda: self.restart(lang(), LIGHT))
        else:
            yield SystemCommand(t("cmd_dark"), t("cmd_dark_help"), lambda: self.restart(lang(), DARK))
        yield SystemCommand(t("delays_now"), t("cmd_delays_help"), lambda: self.go_home(Delays))
        yield SystemCommand(t("where_train"), t("cmd_follow_help"), self.ask_train)
        yield SystemCommand(t("help"), t("cmd_help_help"), lambda: self.go_home(Help))
        yield SystemCommand(t("credits"), t("cmd_credits_help"), lambda: self.go_home(Credits))
        if screen.query("HelpPanel"):
            yield SystemCommand(t("cmd_hide_keys"), t("cmd_hide_keys_help"), self.action_hide_help_panel)
        else:
            yield SystemCommand(t("cmd_keys"), t("cmd_keys_help"), self.action_show_help_panel)
        yield SystemCommand(t("cmd_quit"), t("cmd_quit_help"), self.action_quit)

    def ask_train(self) -> None:
        def go(number: str | None) -> None:
            if number:
                self.go_home(lambda: Follow(number))

        self.push_screen(AskTrain(), go)

    async def on_event(self, event: events.Event) -> None:
        if isinstance(event, (events.Key, events.MouseDown)) and isinstance(self.screen, Home):
            train = self.screen.query_one(Train)
            if train.moving:
                await train.park()
        await super().on_event(event)

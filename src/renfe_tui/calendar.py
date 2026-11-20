import calendar
from datetime import date, timedelta

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from .i18n import t

CELL = 4
WIDTH = CELL * 7


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class Calendar(Widget, can_focus=True):
    DEFAULT_CSS = f"Calendar {{ width: {WIDTH}; height: 9; }}"
    BINDINGS = [
        Binding("left", "move(-1)", show=False),
        Binding("right", "move(1)", show=False),
        Binding("up", "move(-7)", show=False),
        Binding("down", "move(7)", show=False),
        Binding("pageup", "month(-1)", show=False),
        Binding("pagedown", "month(1)", show=False),
        Binding("enter", "pick", t("b_pick")),
    ]

    cursor: reactive[date] = reactive(date.today)
    hover: reactive[date | str | None] = reactive(None)

    class Picked(Message):
        def __init__(self, day: date):
            super().__init__()
            self.day = day

    def __init__(self, value: date, first: date, last: date, **kwargs):
        super().__init__(**kwargs)
        self.first, self.last, self.today = first, last, first
        self.set_reactive(Calendar.cursor, min(max(value, first), last))

    def clamp(self, day: date) -> date:
        return min(max(day, self.first), self.last)

    def action_move(self, days: int) -> None:
        self.cursor = self.clamp(self.cursor + timedelta(days=days))

    def action_month(self, months: int) -> None:
        self.cursor = self.clamp(add_months(self.cursor, months))

    def action_pick(self) -> None:
        self.post_message(self.Picked(self.cursor))

    def weeks(self) -> list[list[date | None]]:
        return [[d if d.month == self.cursor.month else None for d in week]
                for week in calendar.Calendar().monthdatescalendar(self.cursor.year, self.cursor.month)]

    def target(self, x: int, y: int) -> date | str | None:
        if y == 0:
            if x < 3:
                return "back"
            if x >= WIDTH - 3:
                return "forward"
            return None
        row, col = y - 2, x // CELL
        weeks = self.weeks()
        if 0 <= row < len(weeks) and 0 <= col < 7 and (day := weeks[row][col]) and self.first <= day <= self.last:
            return day
        return None

    def on_mouse_move(self, event: events.MouseMove) -> None:
        self.hover = self.target(event.x, event.y)

    def on_leave(self) -> None:
        self.hover = None

    def on_click(self, event: events.Click) -> None:
        match self.target(event.x, event.y):
            case "back":
                self.action_month(-1)
            case "forward":
                self.action_month(1)
            case date() as day:
                self.cursor = day
                self.action_pick()

    def render(self) -> Text:
        styles = self.app.current_theme
        muted, accent = self.app.palette.muted, styles.accent
        title = f"{t('months')[self.cursor.month - 1]} {self.cursor.year}"
        can_back = add_months(self.cursor, -1) >= self.first.replace(day=1)
        can_forward = add_months(self.cursor, 1).replace(day=1) <= self.last
        text = Text()
        hovered = f"bold {styles.primary} on {styles.panel}"
        text.append(" ‹ ", style=(hovered if self.hover == "back" else f"bold {styles.primary}") if can_back else muted)
        text.append(title.center(WIDTH - 6), style="bold")
        text.append(" › ", style=(hovered if self.hover == "forward" else f"bold {styles.primary}")
                    if can_forward else muted)
        text.append("\n")
        for i, name in enumerate(t("weekdays")):
            text.append(f"{name:>3} ", style=accent if i >= 5 else muted)
        for week in self.weeks():
            text.append("\n")
            for i, day in enumerate(week):
                if day is None:
                    text.append(" " * CELL)
                    continue
                label = f"{day.day:>3} "
                if day == self.cursor:
                    style = f"bold {styles.background} on {styles.primary}"
                elif not self.first <= day <= self.last:
                    style = muted
                elif day == self.hover:
                    style = f"bold {styles.foreground} on {styles.panel}"
                elif day == self.today:
                    style = f"bold underline {styles.primary}"
                elif i >= 5:
                    style = accent
                else:
                    style = ""
                text.append(label, style=style)
        return text


class DatePicker(ModalScreen[date | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", t("b_cancel"))]

    def __init__(self, value: date, first: date, last: date):
        super().__init__()
        self.value, self.first, self.last = value, first, last

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(t("pick_day"), classes="title")
            yield Calendar(self.value, self.first, self.last)
            yield Static(Text(t("cal_hint"), style=self.app.palette.muted), classes="cal-hint")
            with Horizontal(classes="buttons"):
                yield Button(t("b_pick").capitalize(), id="ok", classes="primary")
                yield Button(t("cancel"), id="cancel", classes="quiet")

    def on_mount(self) -> None:
        self.query_one(Calendar).focus()

    @on(Calendar.Picked)
    def picked(self, event: Calendar.Picked) -> None:
        self.dismiss(event.day)

    @on(Button.Pressed, "#ok")
    def ok(self) -> None:
        self.dismiss(self.query_one(Calendar).cursor)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

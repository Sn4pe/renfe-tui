from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from .theme import PURPLE

WORDMARK = (
    "█▀▀▄ █▀▀▀ █▄  █ █▀▀▀ █▀▀▀",
    "█▄▄▀ █▀▀  █ ▀▄█ █▀▀  █▀▀ ",
    "█  █ █▄▄▄ █   █ █    █▄▄▄",
)

TRAIN = (
    "        ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
    "    ▄▄██▀ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ ▐▀▀▌ █",
    " ▄██▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀█",
    "▀█████████████████████████████████████████████████████▀",
    "   ▀◉◉▀            ▀◉◉▀            ▀◉◉▀            ▀◉◉▀ ",
)
TRAIN_WIDTH = max(len(row) for row in TRAIN)


def _windows(row: str) -> set[int]:
    cells, inside = set(), False
    for i, ch in enumerate(row):
        if ch == "▐":
            inside = True
        if inside:
            cells.add(i)
        if ch == "▌":
            inside = False
    return cells


WINDOWS = [_windows(row) for row in TRAIN]


def wordmark() -> Text:
    text = Text(justify="center")
    for i, row in enumerate(WORDMARK):
        text.append(row, style=f"bold {PURPLE}")
        if i < len(WORDMARK) - 1:
            text.append("\n")
    return text


def _train_row(row: str, offset: int, width: int, index: int, muted: str, window: str) -> Text:
    text = Text()
    for x in range(width):
        i = x - offset
        ch = row[i] if 0 <= i < len(row) else " "
        if index == len(TRAIN) - 1:
            style = muted if ch != " " else ""
        elif i in WINDOWS[index]:
            style = window
        else:
            style = PURPLE
        text.append(ch, style=style)
    return text


class Train(Widget):
    DEFAULT_CSS = "Train { height: 6; width: 1fr; }"

    offset = reactive(0.0, layout=False)

    class Arrived(Message):
        pass

    def __init__(self, animate: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.pending = animate
        self.moving = False

    def parked(self) -> int:
        return max(0, (self.size.width - TRAIN_WIDTH) // 2)

    def on_resize(self) -> None:
        if self.pending and self.size.width:
            self.pending, self.moving = False, True
            self.offset = self.size.width
            self.animate("offset", self.parked(), duration=1.8, easing="out_cubic", on_complete=self.arrived)
        elif not self.moving:
            self.offset = self.parked()

    def arrived(self) -> None:
        self.moving = False
        self.offset = self.parked()
        self.post_message(self.Arrived())

    async def park(self) -> None:
        self.pending = False
        await self.stop_animation("offset", complete=False)
        self.arrived()

    def render(self) -> Text:
        width, palette = self.size.width, self.app.palette
        text = Text()
        for index, row in enumerate(TRAIN):
            text.append_text(_train_row(row, int(self.offset), width, index, palette.muted, palette.window))
            text.append("\n")
        text.append("═" * width, style=palette.muted)
        return text

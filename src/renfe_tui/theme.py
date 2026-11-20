import os
import re
import subprocess
import sys
from dataclasses import dataclass

from textual.theme import Theme

ENV = "RENFE_TUI_THEME"
PURPLE = "#8a1f7b"


@dataclass(frozen=True)
class Palette:
    theme: Theme
    muted: str
    window: str

    @property
    def warning(self) -> str:
        return self.theme.warning

    @property
    def error(self) -> str:
        return self.theme.error

    @property
    def success(self) -> str:
        return self.theme.success


LIGHT = Palette(
    Theme(name="renfe-claro", primary=PURPLE, secondary="#6b175f", accent="#b0479f", foreground="#231a22",
          background="#f7f4f6", surface="#eee7ec", panel="#ddd1da", warning="#8f5300", error="#b3261e",
          success="#2e6b34", dark=False),
    muted="#6f6470",
    window="#cdbccb",
)

DARK = Palette(
    Theme(name="renfe-oscuro", primary=PURPLE, secondary="#b0479f", accent="#d9a3cf", foreground="#e9e3ea",
          background="#161115", surface="#1f181e", panel="#2a2028", warning="#e0b25c", error="#e0675c",
          success="#8fc48a", dark=True),
    muted="#9a8f9c",
    window="#e9e3ea",
)

NAMES = {"claro": LIGHT, "light": LIGHT, "oscuro": DARK, "dark": DARK}


def _run(*cmd: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None


def parse_portal(output: str) -> bool | None:
    match = re.search(r"(?:uint32|\bu)\s+(\d)", output)
    return {1: True, 2: False}.get(int(match[1])) if match else None


PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
          "org.freedesktop.portal.Settings", "org.freedesktop.appearance", "color-scheme")


def _linux() -> bool | None:
    dest, path, iface, namespace, key = PORTAL
    for cmd in (("busctl", "--user", "call", dest, path, iface, "ReadOne", "ss", namespace, key),
                ("gdbus", "call", "--session", "--dest", dest, "--object-path", path,
                 "--method", f"{iface}.ReadOne", namespace, key),
                ("dbus-send", "--session", "--print-reply", f"--dest={dest}", path, f"{iface}.ReadOne",
                 f"string:{namespace}", f"string:{key}")):
        done = _run(*cmd)
        if done and done.returncode == 0:
            return parse_portal(done.stdout)
    return None


def _macos() -> bool | None:
    done = _run("defaults", "read", "-g", "AppleInterfaceStyle")
    if done is None:
        return None
    return done.returncode == 0 and "dark" in done.stdout.lower()


def _windows() -> bool | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return None


def system_dark() -> bool | None:
    if sys.platform == "darwin":
        return _macos()
    if sys.platform == "win32":
        return _windows()
    return _linux()


def parse_background(reply: str) -> bool | None:
    match = re.search(r"\]11;rgba?:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", reply)
    if not match:
        return None
    r, g, b = (int(part, 16) / (16 ** len(part) - 1) for part in match.groups())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5


def terminal_dark(timeout: float = 0.3) -> bool | None:
    if sys.platform == "win32" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    import select
    import termios
    import tty

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None
    saved = termios.tcgetattr(fd)
    reply = b""
    try:
        tty.setcbreak(fd)
        os.write(fd, b"\x1b]11;?\x1b\\\x1b[c")
        while not re.search(rb"\x1b\[\?[\d;]*c", reply):
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                break
            reply += os.read(fd, 1024)
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
        os.close(fd)
    return parse_background(reply.decode("ascii", "replace"))


def pick(requested: str | None = None) -> Palette:
    choice = (requested or os.environ.get(ENV) or "").strip().lower()
    if choice in NAMES:
        return NAMES[choice]
    dark = system_dark()
    if dark is None:
        dark = terminal_dark()
    return LIGHT if dark is False else DARK

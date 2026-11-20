import pytest

from renfe_tui import theme


@pytest.mark.parametrize("output,dark", [
    ("v u 1\n", True), ("v u 2\n", False), ("v u 0\n", None),
    ("(<<uint32 1>>,)\n", True), ("   variant       uint32 2\n", False), ("", None),
])
def test_parse_portal(output, dark):
    assert theme.parse_portal(output) is dark


@pytest.mark.parametrize("reply,dark", [
    ("\x1b]11;rgb:ffff/ffff/ffff\x1b\\\x1b[?62;22c", False),
    ("\x1b]11;rgb:1e1e/1e1e/2e2e\x07\x1b[?1;2c", True),
    ("\x1b]11;rgb:f7/f4/f6\x1b\\", False),
    ("\x1b[?1;2c", None),
])
def test_parse_background(reply, dark):
    assert theme.parse_background(reply) is dark


def test_explicit_choice_wins(monkeypatch):
    monkeypatch.setattr(theme, "system_dark", lambda: True)
    assert theme.pick("claro") is theme.LIGHT
    monkeypatch.setenv(theme.ENV, "claro")
    assert theme.pick() is theme.LIGHT


@pytest.mark.parametrize("system,terminal,expected", [
    (True, False, "DARK"), (False, True, "LIGHT"), (None, False, "LIGHT"), (None, None, "DARK"),
])
def test_system_then_terminal_then_dark(monkeypatch, system, terminal, expected):
    monkeypatch.delenv(theme.ENV, raising=False)
    monkeypatch.setattr(theme, "system_dark", lambda: system)
    monkeypatch.setattr(theme, "terminal_dark", lambda: terminal)
    assert theme.pick() is getattr(theme, expected)

import json
import stat
import sys
from pathlib import Path

import pytest

from renfe_tui import bridge

FAKE = Path(__file__).parent / "fake_renfe.py"


class Calls:
    def __init__(self, path: Path):
        self.path = path

    def __call__(self) -> list[list[str]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines()]


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    wrapper = tmp_path / "renfe"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv(bridge.CLI_ENV, str(wrapper))
    monkeypatch.setenv("FAKE_RENFE_LOG", str(log))
    return Calls(log)


@pytest.fixture
def scenario(monkeypatch):
    return lambda name: monkeypatch.setenv("FAKE_RENFE_SCENARIO", name)


@pytest.fixture(autouse=True)
def fixed_theme(monkeypatch):
    monkeypatch.setenv("RENFE_TUI_THEME", "oscuro")

import asyncio
import json
import os
import shutil
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

CLI_ENV = "RENFE_TUI_CLI"


def cli_path() -> str:
    if override := os.environ.get(CLI_ENV):
        return override
    beside = Path(sys.executable).parent / ("renfe.exe" if os.name == "nt" else "renfe")
    if beside.exists():
        return str(beside)
    if found := shutil.which("renfe"):
        return found
    raise FileNotFoundError("renfe")


@dataclass
class Result:
    exit_code: int
    data: dict | None = None
    error: dict | None = field(default=None)

    @property
    def blocked(self) -> bool:
        return self.exit_code == 5 and (self.error or {}).get("type") == "blocked"


def _json(text: bytes) -> dict | None:
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def _error(stderr: bytes) -> dict | None:
    for line in reversed(stderr.splitlines()):
        doc = _json(line)
        if doc and isinstance(doc.get("error"), dict):
            return doc["error"]
    return None


async def run(*args: str) -> Result:
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path(), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
    except (FileNotFoundError, PermissionError):
        return Result(127, error={"type": "missing_cli", "message": "renfe-cli no está instalado"})
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    error = _error(err)
    if proc.returncode and error is None:
        error = {"type": "internal", "message": f"renfe terminó con código {proc.returncode}"}
    return Result(proc.returncode or 0, _json(out), error)


@dataclass
class Line:
    data: dict | None = None
    progress: str = ""
    result: Result | None = None


async def _pump(stream: asyncio.StreamReader, kind: str, queue: asyncio.Queue) -> None:
    async for raw in stream:
        await queue.put((kind, raw))
    await queue.put((kind, None))


async def stream(*args: str) -> AsyncIterator[Line]:
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path(), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
    except (FileNotFoundError, PermissionError):
        yield Line(result=Result(127, error={"type": "missing_cli", "message": "renfe-cli no está instalado"}))
        return
    queue: asyncio.Queue = asyncio.Queue()
    pumps = [asyncio.create_task(_pump(proc.stdout, "out", queue)),
             asyncio.create_task(_pump(proc.stderr, "err", queue))]
    stdout: list[bytes] = []
    stderr: list[bytes] = []
    last: dict | None = None
    try:
        open_streams = 2
        while open_streams:
            kind, raw = await queue.get()
            if raw is None:
                open_streams -= 1
            elif kind == "out":
                stdout.append(raw)
                if doc := _json(raw):
                    last = doc
                    yield Line(data=doc)
            else:
                stderr.append(raw)
                if _json(raw) is None and (text := raw.decode(errors="replace").strip()):
                    yield Line(progress=text)
        await proc.wait()
    finally:
        for pump in pumps:
            pump.cancel()
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    error = _error(b"\n".join(stderr))
    if proc.returncode and error is None:
        error = {"type": "internal", "message": f"renfe terminó con código {proc.returncode}"}
    yield Line(result=Result(proc.returncode or 0, last or _json(b"".join(stdout)), error))


def search_args(origin: str, destination: str, day: str, after: str = "", arrive_by: str = "",
                limit: int = 30) -> list[str]:
    args = ["search", origin, destination, "--date", day, "--limit", str(limit)]
    if after:
        args += ["--after", after]
    if arrive_by:
        args += ["--arrive-by", arrive_by]
    return args

import json
import os
import signal
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

with open(os.environ["FAKE_RENFE_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")

scenario = os.environ.get("FAKE_RENFE_SCENARIO", "ok")
command = sys.argv[1]
name = f"{command}.{scenario}"
stdout, stderr = FIXTURES / f"{name}.json", FIXTURES / f"{name}.err"
lines, progress = FIXTURES / f"{name}.jsonl", FIXTURES / f"{name}.progress"
if progress.exists():
    for text in progress.read_text().splitlines():
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
if lines.exists():
    for line in lines.read_text().splitlines():
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    if (FIXTURES / f"{name}.hold").exists():
        signal.pause()
if stdout.exists():
    sys.stdout.write(stdout.read_text())
if stderr.exists():
    sys.stderr.write(stderr.read_text())
sys.exit(int((FIXTURES / f"{name}.code").read_text()) if (FIXTURES / f"{name}.code").exists() else 0)

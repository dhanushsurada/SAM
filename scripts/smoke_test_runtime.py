#!/usr/bin/env python3
"""End-to-end smoke test of a staged or installed SAM runtime.

Does exactly what the desktop app does on first launch, against a throwaway
HOME so nothing touches real user data:

  1. python sam_cli.py start api --json     (spawns the API backend)
  2. GET /api/iqoo/health and /api/environment
  3. python sam_cli.py status --json
  4. python sam_cli.py stop api --json      (and asserts the port is freed)

Usage:
    python scripts/smoke_test_runtime.py PATH/TO/sam-runtime [--port 18420]

Exit code 0 only when every step succeeds.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def fail(message: str) -> None:
    print(f"SMOKE TEST FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    fail(f"no JSON line in CLI output: {text!r}")
    return {}


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_json(port: int, path: str, timeout: float) -> dict:
    """Call the local API directly, without consulting proxy environment vars."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        if response.status >= 400:
            fail(f"GET {path} returned HTTP {response.status}: {payload}")
        return payload
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--port", type=int, default=18420)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    runtime = args.runtime.resolve()
    meta = json.loads((runtime / "bundle.json").read_text(encoding="utf-8"))
    python = runtime / meta["python_executable"]
    source = runtime / "source"
    site = runtime / "site-packages"
    for label, path in (("python", python), ("source", source), ("site-packages", site)):
        if not path.exists():
            fail(f"{label} missing at {path}")
    if port_open(args.port):
        fail(f"port {args.port} is already in use; choose another with --port")

    with tempfile.TemporaryDirectory(prefix="sam-smoke-home-") as home:
        data = Path(home) / ".sam_data"
        data.mkdir()
        (data / "settings.yaml").write_text(f"api_port: {args.port}\n", encoding="utf-8")
        env = dict(os.environ)
        env.update({
            "HOME": home, "USERPROFILE": home, "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": os.pathsep.join([str(source), str(site)]),
            "SAM_USER_PACKAGES_DIR": str(data / "python-packages"),
        })
        creation = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

        def cli(*cli_args: str, timeout: float = 90.0) -> dict:
            result = subprocess.run(
                [str(python), str(source / "sam_cli.py"), *cli_args, "--json"],
                cwd=source, env=env, capture_output=True, text=True,
                timeout=timeout, creationflags=creation,
            )
            if not result.stdout.strip():
                fail(f"sam_cli {cli_args} produced no output. stderr: {result.stderr[-800:]}")
            return last_json(result.stdout)

        started = False
        try:
            print("1/4 start api ...", flush=True)
            start = cli("start", "api")
            summary = json.dumps(start)
            print("   ", summary if start.get("success") is False else summary[:300])
            started = True
            deadline = time.monotonic() + args.timeout
            health = None
            while time.monotonic() < deadline:
                try:
                    health = get_json(args.port, "/api/iqoo/health", timeout=2)
                    break
                except Exception:
                    time.sleep(0.5)
            if health is None:
                fail("API health endpoint never answered")
            print("2/4 health:", health)
            environment = get_json(args.port, "/api/environment", timeout=10)
            if "environment" not in environment:
                fail(f"/api/environment lacks 'environment': {list(environment)}")
            print("    environment endpoint ok")
            print("3/4 status ...", flush=True)
            status = cli("status")
            print("   ", json.dumps(status)[:300])
        finally:
            if started:
                print("4/4 stop api ...", flush=True)
                try:
                    stop = cli("stop", "api")
                    print("   ", json.dumps(stop)[:300])
                except BaseException as exc:  # still check the port below
                    print("    stop raised:", exc, file=sys.stderr)
        for _ in range(30):
            if not port_open(args.port):
                break
            time.sleep(0.5)
        else:
            fail(f"port {args.port} still open after stop; backend leaked")
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline regression checks for the macOS screenshot and shell-pipeline fixes.

Usage: python3 tests/test_macos_screenshot_and_terminal_exit_offline.py
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.verifier import Verifier
from hands.terminal.runner import TerminalRunner
from hands.vision.screen_reader import ScreenReader


class Settings:
    vision_model = "moondream"
    ollama_host = "http://localhost:11434"


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise AssertionError(label)


def test_screenshot_uses_system_binary_tmp_and_surfaces_error():
    reader = ScreenReader(Settings())
    calls = []

    def failed_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=1, stdout="", stderr="could not create image from display")

    with patch("hands.vision.screen_reader.subprocess.run", side_effect=failed_run):
        try:
            reader._take_screenshot()
            raise AssertionError("Expected capture failure")
        except RuntimeError as exc:
            check("Screenshot error retains macOS diagnostic", "could not create image from display" in str(exc))
            check("Screenshot error identifies Screen Recording permission", "Screen Recording" in str(exc))

    check("Vision calls the stable system screencapture binary", calls[0][0][0] == "/usr/sbin/screencapture")
    check("Vision capture is kept under /tmp", calls[0][0][-1].startswith("/tmp/"))


def test_terminal_pipeline_failure_is_not_accepted():
    runner = TerminalRunner(working_dir=tempfile.gettempdir())
    output = runner.run("grep -rl 'needle' definitely-not-a-real-sam-path | xargs sed -n '1p'")
    check("A failed earlier pipeline command is marked failed", "SAM_TERMINAL_FAILED" in output)
    result = Verifier().verify("terminal", {}, output, 0.01)
    check("Verifier rejects terminal failure marker", result.success is False)


def test_terminal_success_remains_accepted():
    output = TerminalRunner(working_dir=tempfile.gettempdir()).run("printf 'ok'")
    check("Successful command has no failure marker", "SAM_TERMINAL_FAILED" not in output)
    check("Verifier accepts successful terminal command", Verifier().verify("terminal", {}, output, 0.01).success)


if __name__ == "__main__":
    test_screenshot_uses_system_binary_tmp_and_surfaces_error()
    test_terminal_pipeline_failure_is_not_accepted()
    test_terminal_success_remains_accepted()
    print("All screenshot and terminal-exit checks passed.")

"""
Offline regression tests for Phase 1 (Hands / computer-control reliability).

Covers the two concrete failures from real testing:

1. "Open Spotlight and search for Visual Studio Code, then launch it" --
   vision failed to find "click the Visual Studio Code application in the
   search results" because the description sent to the vision model still
   had the action verb attached (core/brain.py's own action-payload prompt
   example literally shows `"description": "click the send button"`, so
   the Brain reliably produces text in this shape). Fixed by stripping a
   leading action-verb phrase in hands/vision/screen_reader.py before the
   description reaches the vision model.

2. "open VS Code" got stuck repeating "Typed: VS Code" until stagnation
   detection aborted it. The type action's observation was a bare
   self-report ("Typed: {text}") no matter what actually happened on
   screen, so the next reasoning step had nothing to distinguish "typing
   worked, now click the result" from "nothing happened, try again".
   Fixed by having click and type actions re-observe the screen after
   acting, in agent/react_loop.py's _execute_control().

Usage:
    python3 tests/test_hands_reliability_offline.py

(No HOME override needed -- this test doesn't touch ~/.sam_data, Ollama,
or pyautogui; everything vision/control-related is faked.)
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from hands.vision.screen_reader import ScreenReader  # noqa: E402
from hands.control.controller import ComputerController  # noqa: E402
from agent.react_loop import ReactLoop  # noqa: E402
from agent.verifier import Verifier  # noqa: E402
from core.brain import SYSTEM_PROMPT  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


class FakeSettings:
    vision_model = "moondream"
    ollama_host = "http://localhost:11434"


def _make_loop():
    return ReactLoop(FakeSettings())


# ─── Description cleaning (Failure 1: Spotlight/VS Code click) ─────────────

def test_clean_target_description():
    clean = ScreenReader._clean_target_description
    check("Strips 'click ' prefix",
          clean("click the send button") == "the send button")
    check("Strips the exact real-world phrase from testing",
          clean("click the Visual Studio Code application in the search results")
          == "the Visual Studio Code application in the search results")
    check("Strips 'click on ' prefix",
          clean("click on the submit icon") == "the submit icon")
    check("Strips 'tap ' prefix",
          clean("tap the menu icon") == "the menu icon")
    check("Strips 'double click ' prefix",
          clean("double click the file icon") == "the file icon")
    check("Leaves a description with no verb prefix untouched",
          clean("play the video") == "play the video")
    check("Leaves already-clean descriptions untouched",
          clean("center button") == "center button")
    check("Handles an empty string without crashing",
          clean("") == "")


def test_find_element_sends_cleaned_description_to_vision_model():
    sr = ScreenReader(FakeSettings())
    with patch.object(sr, "_take_screenshot", return_value="/tmp/fake.png"), \
         patch.object(sr, "_image_to_base64", return_value="fakebase64"), \
         patch("hands.vision.screen_reader.requests.post") as mock_post, \
         patch.object(sr, "_get_screen_size", return_value=(1920, 1080)), \
         patch("os.unlink"):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": '{"x": 0.5, "y": 0.5}'}
        sr.find_element("click the Visual Studio Code application in the search results")
        sent_prompt = mock_post.call_args.kwargs["json"]["prompt"]
        check("Vision prompt contains the cleaned description",
              "the Visual Studio Code application in the search results" in sent_prompt)
        check("Vision prompt does not still ask it to find the word 'click'",
              "find: click" not in sent_prompt.lower())


# ─── Post-click re-observation ──────────────────────────────────────────────

def test_same_spot_tolerance():
    check("Identical points are the same spot",
          ReactLoop._same_spot((500, 300), (500, 300)) is True)
    check("Points 10px apart are still the same spot",
          ReactLoop._same_spot((500, 300), (510, 305)) is True)
    check("Points far apart are not the same spot",
          ReactLoop._same_spot((500, 300), (900, 700)) is False)


def test_click_not_found_never_clicks():
    loop = _make_loop()
    click_calls = []
    loop._vision = type("V", (), {"find_element": staticmethod(lambda desc: None)})()
    loop._control = type("C", (), {"click": lambda self, x, y: click_calls.append((x, y))})()
    obs = loop._execute_control({"type": "click", "description": "Visual Studio Code"})
    check("No click is issued when the target isn't found", len(click_calls) == 0)
    check("Observation honestly reports not-found", "Could not find" in obs)


def test_click_recheck_flags_unregistered_click():
    loop = _make_loop()
    calls = {"n": 0}

    def fake_find(desc):
        calls["n"] += 1
        return (500, 300)  # same coordinates every time -> nothing moved

    loop._vision = type("V", (), {"find_element": staticmethod(fake_find)})()
    loop._control = type("C", (), {"click": lambda self, x, y: None})()
    obs = loop._execute_control({"type": "click", "description": "Visual Studio Code"})
    check("Vision is consulted twice (find, then re-check)", calls["n"] == 2)
    check("Observation flags a click that may not have registered",
          "may not have registered" in obs)
    check("Verifier treats this as a failure needing retry",
          Verifier().verify("control", {}, obs, 0.1).success is False)


def test_click_recheck_confirms_screen_changed():
    loop = _make_loop()
    responses = [(500, 300), None]  # found once, then gone after the click

    def fake_find(desc):
        return responses.pop(0)

    loop._vision = type("V", (), {"find_element": staticmethod(fake_find)})()
    loop._control = type("C", (), {"click": lambda self, x, y: None})()
    obs = loop._execute_control({"type": "click", "description": "Visual Studio Code"})
    check("Observation reflects the target disappearing after the click",
          "no longer visible" in obs)
    check("Verifier accepts this as a success",
          Verifier().verify("control", {}, obs, 0.1).success is True)


# ─── Post-type re-observation (Failure 2: repeated "Typed: VS Code") ────────

def test_type_includes_fresh_screen_state():
    loop = _make_loop()
    loop._vision = type("V", (), {
        "read": staticmethod(lambda prompt: "A search results list showing Visual Studio Code.")
    })()
    typed = {}
    loop._control = type("C", (), {
        "type_text": lambda self, text, interval=0.02: typed.setdefault("text", text)
    })()
    obs = loop._execute_control({"type": "type", "text": "VS Code"})
    check("Typed text is still actually typed", typed.get("text") == "VS Code")
    check("Observation includes the typed text", "Typed: VS Code" in obs)
    check("Observation includes a fresh screen description, not just a bare self-report",
          "Visual Studio Code" in obs and "Screen now shows" in obs)


def test_repeated_type_reflects_genuine_progress_instead_of_looking_identical():
    """Regression for the exact reported bug: three "Typed: VS Code" self
    reports with no other information were byte-for-byte identical and
    triggered stagnation-abort before a click was ever attempted. With a
    real (changing) screen description attached, steps that are actually
    progressing are no longer indistinguishable from a truly stuck loop."""
    loop = _make_loop()
    screen_states = iter([
        "An empty search box.",
        "A search box containing 'VS Code' with no results yet.",
        "A search results list showing Visual Studio Code.",
    ])
    loop._vision = type("V", (), {"read": staticmethod(lambda prompt: next(screen_states))})()
    loop._control = type("C", (), {"type_text": lambda self, text, interval=0.02: None})()

    observations = []
    for _ in range(3):
        obs = loop._execute_control({"type": "type", "text": "VS Code"})
        observations.append({"observation": obs})
    check("Three successive type observations are not byte-for-byte identical",
          len(set(o["observation"] for o in observations)) == 3)
    check("So stagnation detection does not (mis)fire on genuine progress",
          loop._is_stagnant(observations) is False)


def test_truly_stuck_type_loop_is_still_detected_as_stagnant():
    """The fix adds real information -- it must not mask a real stall. If
    the screen genuinely never changes, the enriched observation is
    identical every time too, and stagnation is still caught exactly as
    before."""
    loop = _make_loop()
    loop._vision = type("V", (), {"read": staticmethod(lambda prompt: "Nothing has changed.")})()
    loop._control = type("C", (), {"type_text": lambda self, text, interval=0.02: None})()

    observations = []
    for _ in range(3):
        obs = loop._execute_control({"type": "type", "text": "VS Code"})
        observations.append({"observation": obs})
    check("A genuinely unchanging screen still produces identical observations",
          len(set(o["observation"] for o in observations)) == 1)
    check("So real stagnation is still correctly detected",
          loop._is_stagnant(observations) is True)


# ─── open_app verification (extends the same Phase 1 gap to open_app) ──────

def test_same_app_matching():
    check("Exact match", ReactLoop._same_app("Chrome", "Chrome"))
    check("Case-insensitive match", ReactLoop._same_app("chrome", "Chrome"))
    check("Substring match (Chrome vs Google Chrome)",
          ReactLoop._same_app("Chrome", "Google Chrome"))
    check("Shared-last-word match (the actual bug-report app: VS Code vs "
          "Visual Studio Code)",
          ReactLoop._same_app("VS Code", "Visual Studio Code"))
    check("Shared-last-word match (VS Code vs Code)",
          ReactLoop._same_app("VS Code", "Code"))
    check("Genuinely different apps do not match",
          ReactLoop._same_app("Chrome", "Safari") is False)
    check("Empty strings never match", ReactLoop._same_app("", "Safari") is False)


def test_poll_for_frontmost_match_immediate_match_has_no_extra_delay():
    loop = _make_loop()
    calls = {"n": 0}

    def fake_frontmost():
        calls["n"] += 1
        return "Visual Studio Code"

    fake_controller = type("C", (), {"get_frontmost_app": staticmethod(fake_frontmost)})()
    matched, seen = loop._poll_for_frontmost_match(fake_controller, "VS Code")
    check("Immediate match returns True", matched is True)
    check("Immediate match returns what was observed", seen == "Visual Studio Code")
    check("Immediate match costs exactly one call — no unnecessary polling",
          calls["n"] == 1)


def test_poll_for_frontmost_match_eventual_match():
    loop = _make_loop()
    responses = iter(["Finder", "Finder", "Visual Studio Code"])
    fake_controller = type("C", (), {
        "get_frontmost_app": staticmethod(lambda: next(responses))
    })()
    with patch("agent.react_loop.OPEN_APP_POLL_TIMEOUT_S", 0.05), \
         patch("agent.react_loop.OPEN_APP_POLL_INTERVAL_S", 0.005):
        matched, seen = loop._poll_for_frontmost_match(fake_controller, "VS Code")
    check("A match found partway through the poll window is caught",
          matched is True)
    check("Returns the matched value once found", seen == "Visual Studio Code")


def test_poll_for_frontmost_match_never_matches_times_out():
    loop = _make_loop()
    fake_controller = type("C", (), {"get_frontmost_app": staticmethod(lambda: "Finder")})()
    with patch("agent.react_loop.OPEN_APP_POLL_TIMEOUT_S", 0.05), \
         patch("agent.react_loop.OPEN_APP_POLL_INTERVAL_S", 0.005):
        matched, seen = loop._poll_for_frontmost_match(fake_controller, "VS Code")
    check("Polling is bounded — times out instead of looping forever",
          matched is False)
    check("Still reports the last thing actually seen in front", seen == "Finder")


def test_poll_for_frontmost_match_permission_denied():
    loop = _make_loop()

    def always_raises():
        raise RuntimeError("osascript failed: not authorized")

    fake_controller = type("C", (), {"get_frontmost_app": staticmethod(always_raises)})()
    with patch("agent.react_loop.OPEN_APP_POLL_TIMEOUT_S", 0.05), \
         patch("agent.react_loop.OPEN_APP_POLL_INTERVAL_S", 0.005):
        matched, seen = loop._poll_for_frontmost_match(fake_controller, "VS Code")
    check("A query that always fails is never treated as a match", matched is False)
    check("last_seen is None only when the query itself never once succeeded",
          seen is None)


def test_execute_control_open_app_matched():
    loop = _make_loop()
    events = []
    fake_controller = type("C", (), {
        "open_app": lambda self, app: events.append(app),
        "get_frontmost_app": staticmethod(lambda: "Visual Studio Code"),
    })()
    loop._control = fake_controller
    obs = loop._execute_control({"type": "open_app", "app": "VS Code"})
    check("open_app is actually called with the requested app", events == ["VS Code"])
    check("Observation confirms the app reached the foreground",
          "confirmed in the foreground" in obs)
    check("Verifier accepts a confirmed open_app",
          Verifier().verify("control", {}, obs, 0.1).success is True)


def test_execute_control_open_app_mismatch():
    loop = _make_loop()
    fake_controller = type("C", (), {
        "open_app": lambda self, app: None,
        "get_frontmost_app": staticmethod(lambda: "Finder"),
    })()
    loop._control = fake_controller
    with patch("agent.react_loop.OPEN_APP_POLL_TIMEOUT_S", 0.05), \
         patch("agent.react_loop.OPEN_APP_POLL_INTERVAL_S", 0.005):
        obs = loop._execute_control({"type": "open_app", "app": "VS Code"})
    check("Observation honestly reports the wrong app in the foreground",
          "Finder' is in the foreground instead" in obs)
    check("Verifier treats an open_app mismatch as a failure needing retry",
          Verifier().verify("control", {}, obs, 0.1).success is False)


def test_execute_control_open_app_cannot_verify():
    loop = _make_loop()

    def always_raises():
        raise RuntimeError("osascript failed: not authorized")

    fake_controller = type("C", (), {
        "open_app": lambda self, app: None,
        "get_frontmost_app": staticmethod(always_raises),
    })()
    loop._control = fake_controller
    with patch("agent.react_loop.OPEN_APP_POLL_TIMEOUT_S", 0.05), \
         patch("agent.react_loop.OPEN_APP_POLL_INTERVAL_S", 0.005):
        obs = loop._execute_control({"type": "open_app", "app": "VS Code"})
    check("Observation is honest that verification itself wasn't possible, "
          "rather than guessing success or failure",
          "could not confirm" in obs)


# ─── _applescript now surfaces real failures (open_app's execution layer) ──

def test_applescript_raises_on_failure_and_still_returns_on_success():
    controller = ComputerController()
    with patch("hands.control.controller.IS_MAC", True):
        with patch("hands.control.controller.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=1, stdout="", stderr="Application isn't running.")
            try:
                controller._applescript('tell application "NotARealApp123" to activate')
                check("_applescript raises on a non-zero osascript exit", False)
            except RuntimeError as e:
                check("_applescript raises on a non-zero osascript exit", True)
                check("The raised error keeps osascript's own diagnostic",
                      "Application isn't running" in str(e))

        with patch("hands.control.controller.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="Finder\n", stderr="")
            result = controller._applescript("some working script")
            check("_applescript still returns stripped stdout on success",
                  result == "Finder")


# ─── ComputerController.screenshot() surfaces real failures too ────────────

def test_screenshot_pyautogui_path_success():
    controller = ComputerController()
    calls = []
    controller._pyautogui = type("PG", (), {
        "screenshot": lambda self, path: calls.append(path)
    })()
    result = controller.screenshot("/tmp/fake_out.png")
    check("screenshot() returns the given path on success", result == "/tmp/fake_out.png")
    check("PyAutoGUI's screenshot was actually called", calls == ["/tmp/fake_out.png"])


def test_screenshot_pyautogui_path_failure_wrapped_with_permission_hint():
    controller = ComputerController()

    def raising_screenshot(self, path):
        raise OSError("could not create image from display")

    controller._pyautogui = type("PG", (), {"screenshot": raising_screenshot})()
    with patch("hands.control.controller.IS_MAC", True):
        try:
            controller.screenshot("/tmp/fake_out.png")
            check("Raises on a PyAutoGUI capture failure", False)
        except RuntimeError as e:
            check("Raises on a PyAutoGUI capture failure", True)
            check("Keeps the underlying error text",
                  "could not create image from display" in str(e))
            check("Adds the Screen Recording permission hint on macOS",
                  "Screen Recording" in str(e))


def test_screenshot_screencapture_fallback_success():
    controller = ComputerController()
    controller._pyautogui = None
    with patch("hands.control.controller.IS_MAC", True), \
         patch("hands.control.controller.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = controller.screenshot("/tmp/fake_out.png")
        check("screencapture fallback returns the path on success",
              result == "/tmp/fake_out.png")
        check("Uses the stable system screencapture binary",
              mock_run.call_args.args[0][0] == "/usr/sbin/screencapture")


def test_screenshot_screencapture_fallback_failure():
    controller = ComputerController()
    controller._pyautogui = None
    with patch("hands.control.controller.IS_MAC", True), \
         patch("hands.control.controller.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=1, stdout="", stderr="could not create image from display")
        try:
            controller.screenshot("/tmp/fake_out.png")
            check("Raises when the screencapture fallback fails", False)
        except RuntimeError as e:
            check("Raises when the screencapture fallback fails", True)
            check("Keeps screencapture's own diagnostic",
                  "could not create image from display" in str(e))
            check("Adds the Screen Recording permission hint",
                  "Screen Recording" in str(e))


def test_screenshot_windows_failure_has_no_macos_specific_hint():
    controller = ComputerController()
    controller._pyautogui = None

    def raising_windows(path):
        raise OSError("some windows-specific screenshot error")

    controller._screenshot_windows = raising_windows
    with patch("hands.control.controller.IS_MAC", False), \
         patch("hands.control.controller.IS_WIN", True):
        try:
            controller.screenshot("C:\\fake_out.png")
            check("Raises on a Windows capture failure too", False)
        except RuntimeError as e:
            check("Raises on a Windows capture failure too", True)
            check("Does not claim a macOS-specific cause on Windows",
                  "Screen Recording" not in str(e))


# ─── core/brain.py: fixed at the source, not just compensated downstream ───

def test_brain_prompt_no_longer_seeds_verb_prefixed_descriptions():
    check("Prompt no longer shows the old 'click the send button' example",
          '"description": "click the send button"' not in SYSTEM_PROMPT)
    check("Prompt still shows a control/click example",
          '"type": "click"' in SYSTEM_PROMPT)
    check("Prompt explicitly tells the model not to repeat the verb",
          "don't repeat the verb" in SYSTEM_PROMPT)
    check("The vision-layer stripping in screen_reader.py stays in place as "
          "a safety net (belt-and-suspenders, not an either/or)",
          hasattr(ScreenReader, "_clean_target_description"))


# ─── Verifier picks up the new failure text ─────────────────────────────────

def test_verifier_recognizes_new_failure_signals():
    v = Verifier()
    check("'may not have registered' is treated as a failure",
          v.verify("control", {},
                   "Clicked 'X' at (1,2), but the same target is still visible "
                   "in the same place afterward — the click may not have "
                   "registered.", 0.1).success is False)
    check("'could not read screen' is treated as a failure",
          v.verify("control", {},
                   "Typed: VS Code. Screen now shows: Could not read screen: "
                   "timeout", 0.1).success is False)
    check("'is in the foreground instead' (open_app mismatch) is a failure",
          v.verify("control", {},
                   "Opened: VS Code, but 'Finder' is in the foreground "
                   "instead — VS Code may not have launched yet, may still "
                   "be loading, or the name may not match exactly.",
                   0.1).success is False)
    check("A confirmed open_app is still accepted",
          v.verify("control", {}, "Opened: VS Code, confirmed in the "
                                    "foreground.", 0.1).success is True)
    check("A normal successful click observation is still accepted",
          v.verify("control", {},
                   "Clicked on 'X' at (1,2); it's no longer visible in the "
                   "same spot afterward, consistent with the click taking "
                   "effect.", 0.1).success is True)


def main():
    test_clean_target_description()
    test_find_element_sends_cleaned_description_to_vision_model()
    test_same_spot_tolerance()
    test_click_not_found_never_clicks()
    test_click_recheck_flags_unregistered_click()
    test_click_recheck_confirms_screen_changed()
    test_type_includes_fresh_screen_state()
    test_repeated_type_reflects_genuine_progress_instead_of_looking_identical()
    test_truly_stuck_type_loop_is_still_detected_as_stagnant()
    test_same_app_matching()
    test_poll_for_frontmost_match_immediate_match_has_no_extra_delay()
    test_poll_for_frontmost_match_eventual_match()
    test_poll_for_frontmost_match_never_matches_times_out()
    test_poll_for_frontmost_match_permission_denied()
    test_execute_control_open_app_matched()
    test_execute_control_open_app_mismatch()
    test_execute_control_open_app_cannot_verify()
    test_applescript_raises_on_failure_and_still_returns_on_success()
    test_screenshot_pyautogui_path_success()
    test_screenshot_pyautogui_path_failure_wrapped_with_permission_hint()
    test_screenshot_screencapture_fallback_success()
    test_screenshot_screencapture_fallback_failure()
    test_screenshot_windows_failure_has_no_macos_specific_hint()
    test_brain_prompt_no_longer_seeds_verb_prefixed_descriptions()
    test_verifier_recognizes_new_failure_signals()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Phase 1 (Hands / computer-control reliability) fixes verified.")


if __name__ == "__main__":
    main()

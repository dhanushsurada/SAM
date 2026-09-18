"""
Offline regression tests for Phase 3 (Hands / desktop-control reliability
reform) — builds on Phase 1 (tests/test_hands_reliability_offline.py) and
Phase 1.5/2, which this file does not duplicate.

Covers the concrete gaps found by auditing the Hands path end to end
against the real-world failures reported (Spotlight/VS Code launch,
YouTube video selection, a screenshot that couldn't be found on disk):

1. Every ComputerController mouse/keyboard action silently did nothing
   when PyAutoGUI wasn't loaded — no exception, no log the caller could
   see. Fixed with an explicit guard on each action method.
2. click()/double_click()/move_to()/drag()/scroll() forwarded whatever
   coordinates they were given straight to PyAutoGUI, with no check that
   they were numeric or on-screen. Fixed with _validate_coords().
3. ComputerController.screenshot()'s default path used
   tempfile.mktemp(suffix=".png") with no dir= — which resolves to
   macOS's per-boot $TMPDIR (under /var/folders/...), NOT /tmp. That's
   the exact, previously-unexplained reason a screenshot SAM reported as
   taken couldn't be found by searching ~/.sam_data, /tmp, or
   /private/tmp. Fixed by defaulting to ~/.sam_data/screenshots/.
4. open_app() passed the raw app name straight to AppleScript with no
   fallback, so "VS Code" failed outright even with Visual Studio Code
   installed and running — same root cause, one layer earlier, as the
   shared-last-word matching agent/react_loop.py's _same_app() already
   uses to verify AFTER activation. Fixed by resolving the name (known
   aliases, then a fuzzy match against installed apps) before ever
   calling AppleScript.
5. core/brain.py's SYSTEM_PROMPT documented only "click" and "type" as
   control subtypes — open_app, hotkey, and screenshot existed in the
   executor but were never mentioned, so the model had no way to know
   open_app existed at all. Fixed by documenting the full vocabulary.
6. hands/vision/screen_reader.py's find_element() only rejected exact
   (0,0) as a degenerate vision answer; a wildly out-of-range result
   (not a valid 0.0-1.0 fraction) fell through unfiltered. Fixed by
   rejecting any pixel result outside the real screen bounds the same
   way. Also documents the normalized-fraction coordinate convention
   end to end, per this phase's explicit request, after confirming via
   the code (not assumption) that it's already Retina/DPI-safe.
7. hands/browser/playwright_agent.py's _smart_click() tried single
   words in left-to-right order via Playwright's `text=` selector —
   reliably matching the first coincidental word on a content-dense
   page (YouTube search results) rather than the requested item. Fixed
   with phrase-first candidate extraction and get_by_text(exact=False),
   plus real before/after-URL verification. goto()'s wait_until also
   changed from "networkidle" (which can hang on pages with persistent
   background connections — YouTube being exactly this kind of page) to
   "domcontentloaded" plus a short, bounded best-effort settle wait.

Usage:
    python3 tests/test_hands_phase3_reliability_offline.py

(No HOME override needed — PyAutoGUI/AppleScript/Playwright are all
faked or exercised only through pure functions; the one test that reads
a real directory listing uses a temp dir, not the real ~/Applications.)
"""

import os
import re
import sys
import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from hands.control.controller import (  # noqa: E402
    ComputerController, SCREENSHOTS_DIR, MAC_APP_NAME_ALIASES,
)
from hands.vision.screen_reader import ScreenReader  # noqa: E402
from hands.browser.playwright_agent import BrowserAgent  # noqa: E402
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


# ═══════════════════════════════════════════════════════════════════════
# Reform 3/4/9 — actions raise instead of silently no-op'ing
# ═══════════════════════════════════════════════════════════════════════

def test_actions_raise_when_pyautogui_missing():
    c = ComputerController()
    c._pyautogui = None
    attempts = [
        ("click", lambda: c.click(100, 100)),
        ("double_click", lambda: c.double_click(100, 100)),
        ("right_click", lambda: c.right_click(100, 100)),
        ("move_to", lambda: c.move_to(100, 100)),
        ("scroll", lambda: c.scroll(100, 100, 3)),
        ("drag", lambda: c.drag(10, 10, 50, 50)),
        ("type_text", lambda: c.type_text("hello")),
        ("hotkey", lambda: c.hotkey("command", "space")),
        ("press", lambda: c.press("enter")),
        ("key_down", lambda: c.key_down("shift")),
        ("key_up", lambda: c.key_up("shift")),
    ]
    for name, fn in attempts:
        try:
            fn()
            check(f"{name}() raises when PyAutoGUI is unavailable (got no exception)", False)
        except RuntimeError as e:
            check(f"{name}() raises when PyAutoGUI is unavailable", True)
            check(f"{name}()'s error is actionable", "pyautogui" in str(e).lower())


def test_click_still_works_normally_when_pyautogui_present():
    c = ComputerController()
    calls = []
    c._pyautogui = SimpleNamespace(
        click=lambda x, y, button="left": calls.append((x, y, button)),
        size=lambda: (1920, 1080),
    )
    c.click(500, 300)
    check("A normal in-bounds click still reaches PyAutoGUI unchanged",
          calls == [(500, 300, "left")])


# ═══════════════════════════════════════════════════════════════════════
# Reform 3 — coordinate bounds validation
# ═══════════════════════════════════════════════════════════════════════

def test_click_rejects_out_of_bounds_coords():
    c = ComputerController()
    c._pyautogui = SimpleNamespace(click=lambda *a, **k: None, size=lambda: (1920, 1080))
    for bad in [(9999, 300), (-5, 300), (500, 99999)]:
        try:
            c.click(*bad)
            check(f"click{bad} is rejected as out of bounds (got no exception)", False)
        except RuntimeError as e:
            check(f"click{bad} is rejected as out of bounds", True)
            check(f"click{bad}'s error explains the real bounds", "screen bounds" in str(e))


def test_click_rejects_non_numeric_coords():
    c = ComputerController()
    c._pyautogui = SimpleNamespace(click=lambda *a, **k: None, size=lambda: (1920, 1080))
    for bad in [("500", 300), (None, 300), (500, None)]:
        try:
            c.click(*bad)
            check(f"click{bad} is rejected as non-numeric (got no exception)", False)
        except RuntimeError:
            check(f"click{bad} is rejected as non-numeric", True)


def test_click_accepts_boundary_coords():
    c = ComputerController()
    calls = []
    c._pyautogui = SimpleNamespace(
        click=lambda x, y, button="left": calls.append((x, y)),
        size=lambda: (1920, 1080),
    )
    c.click(0, 0)
    c.click(1920, 1080)
    check("Coordinates exactly on the screen edge are accepted, not rejected",
          calls == [(0, 0), (1920, 1080)])


def test_drag_validates_both_endpoints():
    c = ComputerController()
    c._pyautogui = SimpleNamespace(drag=lambda *a, **k: None, size=lambda: (1920, 1080))
    try:
        c.drag(10, 10, 99999, 50)
        check("drag() validates its second endpoint too (got no exception)", False)
    except RuntimeError:
        check("drag() validates its second endpoint too", True)


# ═══════════════════════════════════════════════════════════════════════
# Reform 1 — screenshot default path is deterministic and discoverable
# ═══════════════════════════════════════════════════════════════════════

def test_screenshot_default_path_lands_under_sam_data():
    check("SCREENSHOTS_DIR is under ~/.sam_data (not an OS temp dir)",
          SCREENSHOTS_DIR == os.path.join(os.path.expanduser("~"), ".sam_data", "screenshots"))

    c = ComputerController()
    saved_to = []
    c._pyautogui = SimpleNamespace(screenshot=lambda path: saved_to.append(path))
    with tempfile.TemporaryDirectory() as fake_home:
        with patch("hands.control.controller.SCREENSHOTS_DIR",
                   os.path.join(fake_home, ".sam_data", "screenshots")):
            result = c.screenshot()
        check("screenshot() with no path returns a path under SCREENSHOTS_DIR",
              result.startswith(os.path.join(fake_home, ".sam_data", "screenshots")))
        check("The screenshot directory is actually created",
              os.path.isdir(os.path.join(fake_home, ".sam_data", "screenshots")))
        check("PyAutoGUI was told to save to that same discoverable path",
              saved_to == [result])


def test_screenshot_default_path_avoids_collisions():
    c = ComputerController()
    c._pyautogui = SimpleNamespace(screenshot=lambda path: None)
    with tempfile.TemporaryDirectory() as fake_home:
        fake_dir = os.path.join(fake_home, ".sam_data", "screenshots")
        with patch("hands.control.controller.SCREENSHOTS_DIR", fake_dir):
            first = c.screenshot()
            Path(first).touch()  # Simulate the file actually having been written.
            second = c.screenshot()
    check("Two default-path screenshots in the same run don't collide",
          first != second)


def test_screenshot_explicit_path_still_bypasses_default_entirely():
    c = ComputerController()
    saved_to = []
    c._pyautogui = SimpleNamespace(screenshot=lambda path: saved_to.append(path))
    result = c.screenshot("/tmp/explicit_name.png")
    check("An explicitly-given path is used completely unchanged",
          result == "/tmp/explicit_name.png" and saved_to == ["/tmp/explicit_name.png"])


# ═══════════════════════════════════════════════════════════════════════
# Reform 5 — open_app() name resolution
# ═══════════════════════════════════════════════════════════════════════

def test_app_name_candidates_known_alias():
    candidates = ComputerController._app_name_candidates("VS Code")
    check("Known alias table resolves 'VS Code' -> 'Visual Studio Code'",
          "Visual Studio Code" in candidates)
    check("The alias is the first (highest-priority) candidate tried",
          candidates[0] == "Visual Studio Code")


def _patch_applications_dir(fake_apps_dir):
    """
    Makes hands.control.controller's os.listdir("/Applications") return
    the contents of fake_apps_dir, and [] for every other directory.

    Patching os.listdir replaces it on the shared `os` module object
    itself (hands.control.controller does `import os`, not `from os
    import listdir`, so there's only the one os module in sys.modules
    either way) -- which means the real os.listdir must be read BEFORE
    entering the patch, not from inside the fake, or the fake ends up
    recursively calling its own mocked self and always returns [].
    """
    real_listing = os.listdir(fake_apps_dir)

    def fake_listdir(d):
        return list(real_listing) if d == "/Applications" else []

    return patch("hands.control.controller.os.listdir", side_effect=fake_listdir)


def test_app_name_candidates_fuzzy_matches_installed_apps():
    fake_apps_dir = tempfile.mkdtemp()
    try:
        os.mkdir(os.path.join(fake_apps_dir, "Visual Studio Code.app"))
        os.mkdir(os.path.join(fake_apps_dir, "Notes.app"))
        os.mkdir(os.path.join(fake_apps_dir, "Safari.app"))

        with _patch_applications_dir(fake_apps_dir):
            candidates = ComputerController._app_name_candidates("Visual Studio")
        check("A name sharing a substring with an installed app resolves to it, "
              "with the .app suffix stripped",
              "Visual Studio Code" in candidates)
        check("Unrelated installed apps are not pulled in as candidates",
              "Notes" not in candidates and "Safari" not in candidates)
    finally:
        shutil.rmtree(fake_apps_dir)


def test_app_name_candidates_shared_last_word():
    fake_apps_dir = tempfile.mkdtemp()
    try:
        os.mkdir(os.path.join(fake_apps_dir, "Visual Studio Code.app"))

        with _patch_applications_dir(fake_apps_dir):
            # "MS Code" shares only its LAST word with "Visual Studio
            # Code" -- it's not a substring either way -- isolating the
            # shared-last-word branch specifically, same rule
            # principles-and-workflow.md notes as the proven approach
            # for fuzzy macOS app-name resolution (VS Code vs Visual
            # Studio Code is the alias-table entry; this is the general
            # fallback for names not in that table).
            candidates = ComputerController._app_name_candidates("MS Code")
        check("A name sharing only a last word (not a substring) still resolves",
              "Visual Studio Code" in candidates)
    finally:
        shutil.rmtree(fake_apps_dir)


def test_app_name_candidates_survives_unreadable_directory():
    with patch("hands.control.controller.os.listdir", side_effect=OSError("no permission")):
        try:
            candidates = ComputerController._app_name_candidates("Anything")
            check("An unreadable app directory doesn't crash resolution (best-effort)", True)
        except OSError:
            check("An unreadable app directory doesn't crash resolution (best-effort)", False)


def test_open_app_mac_falls_back_to_resolved_alias():
    c = ComputerController()
    attempted = []

    def fake_applescript(script):
        attempted.append(script)
        if '"VS Code"' in script:
            raise RuntimeError("osascript failed (exit 1): Application isn't running.")
        return ""  # "Visual Studio Code" succeeds

    with patch("hands.control.controller.IS_MAC", True), \
         patch.object(c, "_applescript", side_effect=fake_applescript):
        c.open_app("VS Code")
    check("The literal name is tried first", '"VS Code"' in attempted[0])
    check("The resolved alias is tried next and succeeds",
          any('"Visual Studio Code"' in s for s in attempted))


def test_open_app_mac_raises_naming_every_attempt_when_nothing_resolves():
    c = ComputerController()
    with patch("hands.control.controller.IS_MAC", True), \
         patch.object(c, "_applescript", side_effect=RuntimeError("Application isn't running.")), \
         patch("hands.control.controller.os.listdir", return_value=[]):
        try:
            c.open_app("TotallyMadeUpApp99")
            check("open_app raises when nothing resolves (got no exception)", False)
        except RuntimeError as e:
            check("open_app raises when nothing resolves", True)
            check("The error names what was actually tried",
                  "TotallyMadeUpApp99" in str(e))


def test_open_app_direct_success_skips_resolution_entirely():
    """The common case -- the name given already works -- does exactly
    one AppleScript call, no fuzzy scan at all."""
    c = ComputerController()
    calls = []
    with patch("hands.control.controller.IS_MAC", True), \
         patch.object(c, "_applescript", side_effect=lambda s: calls.append(s) or ""):
        c.open_app("Safari")
    check("A name that resolves directly makes exactly one AppleScript call",
          len(calls) == 1)


# ═══════════════════════════════════════════════════════════════════════
# Reform 2/3 — vision out-of-bounds rejection + coordinate convention
# ═══════════════════════════════════════════════════════════════════════

def _fake_vision_response(sr, x, y, screen_size=(1920, 1080)):
    return (
        patch.object(sr, "_take_screenshot", return_value="/tmp/fake.png"),
        patch.object(sr, "_image_to_base64", return_value="b64"),
        patch("hands.vision.screen_reader.requests.post"),
        patch.object(sr, "_get_screen_size", return_value=screen_size),
        patch("os.unlink"),
        x, y,
    )


def test_find_element_rejects_out_of_bounds_pixel_result():
    sr = ScreenReader(FakeSettings())
    with patch.object(sr, "_take_screenshot", return_value="/tmp/fake.png"), \
         patch.object(sr, "_image_to_base64", return_value="b64"), \
         patch("hands.vision.screen_reader.requests.post") as mock_post, \
         patch.object(sr, "_get_screen_size", return_value=(1920, 1080)), \
         patch("os.unlink"):
        mock_post.return_value.status_code = 200
        # Not a valid 0.0-1.0 fraction -- the defensive raw-pixel
        # passthrough in _to_pixel_coords lets this reach here unscaled.
        mock_post.return_value.json.return_value = {"response": '{"x": 5000, "y": 3}'}
        result = sr.find_element("play button")
    check("An out-of-bounds vision result is treated as not-found", result is None)


def test_find_element_still_accepts_normal_results_after_bounds_check():
    sr = ScreenReader(FakeSettings())
    with patch.object(sr, "_take_screenshot", return_value="/tmp/fake.png"), \
         patch.object(sr, "_image_to_base64", return_value="b64"), \
         patch("hands.vision.screen_reader.requests.post") as mock_post, \
         patch.object(sr, "_get_screen_size", return_value=(1920, 1080)), \
         patch("os.unlink"):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": '{"x": 0.25, "y": 0.75}'}
        result = sr.find_element("play button")
    check("A normal in-bounds result is still returned correctly",
          result == (480, 810))


def test_coordinate_convention_is_scale_invariant():
    """Documents/verifies the property the new docstring in
    screen_reader.py claims: the SAME normalized fraction maps correctly
    onto different logical screen sizes (standing in for different
    Retina scale factors), because it's a fraction of the image, not a
    raw pixel count, being scaled by pyautogui.size() -- never by the
    screenshot's own raw pixel dimensions."""
    sr = ScreenReader(FakeSettings())
    for width, height in [(1512, 982), (2880, 1800), (1920, 1080)]:
        with patch.object(sr, "_get_screen_size", return_value=(width, height)):
            px, py = sr._to_pixel_coords(0.5, 0.5)
        check(f"(0.5, 0.5) maps to the exact center at {width}x{height}",
              (px, py) == (width // 2, height // 2))


# ═══════════════════════════════════════════════════════════════════════
# Reform 5/6 — Brain prompt documents the full control vocabulary
# ═══════════════════════════════════════════════════════════════════════

def test_brain_prompt_documents_full_control_vocabulary():
    for subtype in ('"type": "click"', '"type": "type"', '"type": "hotkey"',
                     '"type": "open_app"', '"type": "screenshot"'):
        check(f"Prompt documents the {subtype} control subtype",
              subtype in SYSTEM_PROMPT)
    check("Prompt tells the model open_app is the reliable way to launch an app",
          "open_app" in SYSTEM_PROMPT and "reliable" in SYSTEM_PROMPT.lower())
    # Guard against regressing the Phase 1 prompt fix while extending it.
    check("Phase 1 fix preserved: old verb-prefixed example is still gone",
          '"description": "click the send button"' not in SYSTEM_PROMPT)
    check("Phase 1 fix preserved: 'don't repeat the verb' guidance still present",
          "don't repeat the verb" in SYSTEM_PROMPT)


# ═══════════════════════════════════════════════════════════════════════
# Reform 7 — browser _smart_click candidate extraction + verification
# ═══════════════════════════════════════════════════════════════════════

def test_extract_click_targets_prefers_quoted_phrase():
    targets = BrowserAgent._extract_click_targets(
        'click the video titled "Never Gonna Give You Up"')
    check("Quoted phrase is the first (highest-priority) candidate",
          targets[0] == "Never Gonna Give You Up")


def test_extract_click_targets_strips_filler_into_a_phrase():
    targets = BrowserAgent._extract_click_targets(
        "click on the Weekly Team Standup Notes link")
    check("Filler-stripped phrase candidate is produced when no quotes are given",
          "Weekly Team Standup Notes" in targets)


def test_extract_click_targets_generic_task_still_yields_something():
    """Regression guard: a fully generic task with no distinguishing
    text at all must not silently give up with zero candidates -- it
    should fall back to trying the individual real words, exactly the
    spirit of the word-by-word strategy this replaces."""
    targets = BrowserAgent._extract_click_targets("click the first video result")
    check("A fully generic click task still produces candidates to try",
          len(targets) > 0)
    check("The fallback candidates are the task's own real words, "
          "longest (most specific) first",
          targets == ["result", "first", "video"])


def test_extract_click_targets_empty_task_yields_no_candidates():
    check("An empty task yields no candidates (nothing to try)",
          BrowserAgent._extract_click_targets("") == [])
    check("A bare 'click' with nothing else yields no candidates",
          BrowserAgent._extract_click_targets("click") == [])


def test_smart_click_tries_specific_phrase_before_generic_words():
    agent = BrowserAgent()
    page = MagicMock()
    page.url = "https://example.com/search"
    agent._page = page
    attempted = []

    def fake_get_by_text(text, exact=False):
        attempted.append(text)
        locator = MagicMock()
        if text == "Never Gonna Give You Up":
            def do_click(timeout=None):
                page.url = "https://example.com/watch?v=1"
            locator.first.click.side_effect = do_click
        else:
            locator.first.click.side_effect = Exception("not found")
        return locator

    page.get_by_text.side_effect = fake_get_by_text
    result = agent._smart_click('click the video titled "Never Gonna Give You Up"')
    check("The specific quoted phrase is tried before any generic fallback word",
          attempted[0] == "Never Gonna Give You Up")
    check("Result reports the click as taking effect (URL changed)",
          "taking effect" in result)


def test_smart_click_reports_verifier_compatible_failure_when_url_unchanged():
    agent = BrowserAgent()
    page = MagicMock()
    page.url = "https://example.com"
    agent._page = page
    page.get_by_text.return_value.first.click.return_value = None  # "succeeds" but nothing moves
    result = agent._smart_click("click the submit link")
    check("Observation uses the same 'may not have registered' phrasing as the "
          "control-click path, so the existing Verifier needs no changes",
          "may not have registered" in result)
    check("Verifier treats an unchanged-URL browser click as a failure needing retry",
          Verifier().verify("browser", {}, result, 0.2).success is False)


def test_smart_click_reports_verifier_compatible_success_when_url_changes():
    agent = BrowserAgent()
    page = MagicMock()
    page.url = "https://example.com"
    agent._page = page

    def do_click(timeout=None):
        page.url = "https://example.com/next"
    page.get_by_text.return_value.first.click.side_effect = do_click
    result = agent._smart_click("click the continue button")
    check("Verifier accepts a browser click whose URL actually changed",
          Verifier().verify("browser", {}, result, 0.2).success is True)


def test_smart_click_reports_not_found_when_nothing_matches():
    agent = BrowserAgent()
    page = MagicMock()
    page.url = "https://example.com"
    agent._page = page
    page.get_by_text.return_value.first.click.side_effect = Exception("strict mode violation")
    result = agent._smart_click('click "A Video That Is Not There"')
    check("Observation says 'could not find' when nothing on the page matches",
          "could not find" in result.lower())
    check("Verifier treats this as a failure needing retry",
          Verifier().verify("browser", {}, result, 0.2).success is False)


# ═══════════════════════════════════════════════════════════════════════
# Reform 7 — goto()/settle no longer risk hanging on networkidle
# ═══════════════════════════════════════════════════════════════════════

def test_goto_uses_domcontentloaded_not_networkidle():
    agent = BrowserAgent()
    page = MagicMock()
    agent._page = page
    agent._started = True
    agent._owner_thread_id = __import__("threading").get_ident()
    agent._do_execute("https://example.com", "")
    goto_kwargs = page.goto.call_args.kwargs
    check("goto() no longer waits on networkidle (would risk hanging on pages "
          "with persistent background connections, e.g. YouTube)",
          goto_kwargs.get("wait_until") != "networkidle")
    check("goto() uses domcontentloaded instead — fires promptly and reliably",
          goto_kwargs.get("wait_until") == "domcontentloaded")
    check("A bounded settle wait is still attempted after navigation",
          page.wait_for_load_state.called)


def test_settle_swallows_timeout_instead_of_propagating():
    agent = BrowserAgent()
    page = MagicMock()
    page.wait_for_load_state.side_effect = Exception("Timeout 4000ms exceeded")
    agent._page = page
    try:
        agent._settle()
        check("_settle() swallows a networkidle timeout rather than raising", True)
    except Exception:
        check("_settle() swallows a networkidle timeout rather than raising", False)


def main():
    test_actions_raise_when_pyautogui_missing()
    test_click_still_works_normally_when_pyautogui_present()
    test_click_rejects_out_of_bounds_coords()
    test_click_rejects_non_numeric_coords()
    test_click_accepts_boundary_coords()
    test_drag_validates_both_endpoints()
    test_screenshot_default_path_lands_under_sam_data()
    test_screenshot_default_path_avoids_collisions()
    test_screenshot_explicit_path_still_bypasses_default_entirely()
    test_app_name_candidates_known_alias()
    test_app_name_candidates_fuzzy_matches_installed_apps()
    test_app_name_candidates_shared_last_word()
    test_app_name_candidates_survives_unreadable_directory()
    test_open_app_mac_falls_back_to_resolved_alias()
    test_open_app_mac_raises_naming_every_attempt_when_nothing_resolves()
    test_open_app_direct_success_skips_resolution_entirely()
    test_find_element_rejects_out_of_bounds_pixel_result()
    test_find_element_still_accepts_normal_results_after_bounds_check()
    test_coordinate_convention_is_scale_invariant()
    test_brain_prompt_documents_full_control_vocabulary()
    test_extract_click_targets_prefers_quoted_phrase()
    test_extract_click_targets_strips_filler_into_a_phrase()
    test_extract_click_targets_generic_task_still_yields_something()
    test_extract_click_targets_empty_task_yields_no_candidates()
    test_smart_click_tries_specific_phrase_before_generic_words()
    test_smart_click_reports_verifier_compatible_failure_when_url_unchanged()
    test_smart_click_reports_verifier_compatible_success_when_url_changes()
    test_smart_click_reports_not_found_when_nothing_matches()
    test_goto_uses_domcontentloaded_not_networkidle()
    test_settle_swallows_timeout_instead_of_propagating()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Phase 3 (Hands / desktop-control reliability reform) fixes verified.")


if __name__ == "__main__":
    main()

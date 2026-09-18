"""
THE HANDS — Computer Controller
Cross-platform: macOS + Windows

macOS:   PyAutoGUI + AppleScript
Windows: PyAutoGUI + pywinauto + PowerShell

Platform auto-detected. Same API surface on both OS.
"""

import logging
import subprocess
import time
import platform
import os

logger = logging.getLogger("SAM.Controller")

PLATFORM = platform.system()
IS_MAC = PLATFORM == "Darwin"
IS_WIN = PLATFORM == "Windows"

# Absolute path to the macOS system binary — not subject to PATH manipulation.
# Mirrors hands/vision/screen_reader.py's SCREENCAPTURE_BIN; duplicated rather
# than shared since the two modules don't otherwise share any state.
SCREENCAPTURE_BIN = "/usr/sbin/screencapture"

# Phase 3 (Hands reliability): where a user-requested "take a screenshot"
# action saves its file by default. Deterministic and discoverable on
# purpose — see screenshot()'s docstring for the bug this fixes. Mirrors
# config/settings.py's SAM_DATA_DIR (~/.sam_data) convention as a plain
# duplicated constant rather than an import, for the same reason
# SCREENCAPTURE_BIN above is duplicated instead of shared: hands/ modules
# stay importable on their own, without pulling in config/settings.py's
# own import-time side effects (it creates several ~/.sam_data
# subdirectories as soon as it's imported) or its yaml dependency.
# os.path.expanduser("~") resolves correctly on both macOS and Windows.
SCREENSHOTS_DIR = os.path.join(os.path.expanduser("~"), ".sam_data", "screenshots")

# Phase 3 (Hands reliability): common macOS display-name aliases for
# open_app()'s name resolution below. Not an exhaustive app database —
# just the handful of well-known cases where the name someone would
# naturally say ("VS Code", "Chrome") doesn't match the exact name
# AppleScript's `tell application` needs to resolve it, and the
# installed-app fuzzy-match fallback (_resolve_mac_app_name) either
# can't help (no local install to scan against, e.g. in this repo's own
# offline tests) or would require a real filesystem scan. Checked first
# because it's instant; the fuzzy scan below is the general-purpose
# fallback for anything not in this small table.
MAC_APP_NAME_ALIASES = {
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "chrome": "Google Chrome",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "outlook": "Microsoft Outlook",
    "teams": "Microsoft Teams",
}


class ComputerController:
    def __init__(self):
        self._pyautogui = None
        self._winauto = None
        self._load_pyautogui()
        if IS_WIN:
            self._load_winauto()

    def _load_pyautogui(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.1
            self._pyautogui = pyautogui
            logger.info("PyAutoGUI loaded")
        except ImportError:
            logger.warning("PyAutoGUI not installed — pip install pyautogui")

    def _load_winauto(self):
        try:
            from pywinauto import Application
            self._winauto = Application
            logger.info("pywinauto loaded (Windows)")
        except ImportError:
            logger.warning("pywinauto not installed — pip install pywinauto")

    # ─── Reform 3/4/9 guards ────────────────────────────────────────────────
    # Every mouse/keyboard action below used to silently do nothing when
    # PyAutoGUI wasn't loaded (`if self._pyautogui: ...`, no else) — no
    # exception, no log line the caller could see, no return value to
    # check. agent/react_loop.py's execute() only reports what a step's
    # OWN observation says happened; with nothing raised here, a click or
    # a whole typed string could vanish silently and still be described
    # as if it had been attempted. That's a worse gap than the
    # screenshot/AppleScript false-successes Phase 1 already closed, for
    # the same underlying reason this phase exists: "the executor ran"
    # must never be treated as "the action happened." Coordinates get the
    # matching guard: never click/move without valid, in-bounds numbers,
    # and never silently clamp a bad one into an arbitrary real position.

    def _require_pyautogui(self, action_name: str):
        if self._pyautogui is None:
            raise RuntimeError(
                f"Cannot {action_name} — PyAutoGUI is not installed or "
                f"failed to load. Run: pip install pyautogui"
            )

    def _validate_coords(self, x, y):
        if isinstance(x, bool) or isinstance(y, bool) or \
           not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise RuntimeError(
                f"Refusing to click/move: coordinates must be numeric, "
                f"got ({x!r}, {y!r})")
        width, height = self.get_screen_size()
        if not (0 <= x <= width) or not (0 <= y <= height):
            raise RuntimeError(
                f"Refusing to click/move to ({x}, {y}) — outside the real "
                f"screen bounds (0-{width}, 0-{height}). This is rejected "
                f"here rather than silently clamped to the nearest valid "
                f"point, which would just substitute one arbitrary "
                f"position for another.")

    # ─── Mouse ────────────────────────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left"):
        self._require_pyautogui("click")
        self._validate_coords(x, y)
        self._pyautogui.click(x, y, button=button)
        logger.info(f"Clicked ({x}, {y})")

    def double_click(self, x: int, y: int):
        self._require_pyautogui("double-click")
        self._validate_coords(x, y)
        self._pyautogui.doubleClick(x, y)

    def right_click(self, x: int, y: int):
        self._require_pyautogui("right-click")
        self._validate_coords(x, y)
        self._pyautogui.click(x, y, button="right")

    def move_to(self, x: int, y: int, duration: float = 0.3):
        self._require_pyautogui("move the mouse")
        self._validate_coords(x, y)
        self._pyautogui.moveTo(x, y, duration=duration)

    def scroll(self, x: int, y: int, clicks: int):
        self._require_pyautogui("scroll")
        self._validate_coords(x, y)
        self._pyautogui.scroll(clicks, x=x, y=y)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5):
        self._require_pyautogui("drag")
        self._validate_coords(x1, y1)
        self._validate_coords(x2, y2)
        self._pyautogui.drag(x2 - x1, y2 - y1, duration=duration)

    # ─── Keyboard ─────────────────────────────────────────────────────────

    def type_text(self, text: str, interval: float = 0.02):
        self._require_pyautogui("type")
        self._pyautogui.write(text, interval=interval)

    def hotkey(self, *keys):
        self._require_pyautogui("send hotkey")
        self._pyautogui.hotkey(*keys)

    def press(self, key: str):
        self._require_pyautogui("press key")
        self._pyautogui.press(key)

    def key_down(self, key: str):
        self._require_pyautogui("key down")
        self._pyautogui.keyDown(key)

    def key_up(self, key: str):
        self._require_pyautogui("key up")
        self._pyautogui.keyUp(key)

    # ─── Screenshot ───────────────────────────────────────────────────────

    def screenshot(self, path: str = None) -> str:
        """
        Take a screenshot cross-platform and return the saved PNG's path.

        Raises RuntimeError with an actionable diagnostic on failure
        instead of letting a bare exception through (PyAutoGUI path) or
        silently trusting check=True to catch it (screencapture fallback
        path) — same reasoning as hands/vision/screen_reader.py's
        _take_screenshot(): on macOS, the most likely real-world cause is
        Screen Recording permission not granted, which applies to the
        PyAutoGUI capture path here just as much as the direct
        `screencapture` fallback, since both ultimately hit the same OS
        gate.

        Reform 1 (Hands reliability, Phase 3): when no path is given, this
        used to fall through to bare `tempfile.mktemp(suffix=".png")` —
        which does NOT save under /tmp. Python's tempfile module resolves
        the OS default temp directory, and on macOS that's a random,
        per-boot path under /var/folders/.../T/ (from $TMPDIR), not
        /tmp — /tmp on macOS is only where you get if you pass
        `dir="/tmp"` explicitly, which this call never did. That's the
        exact, previously-unexplained root cause of screenshots that SAM
        reported as taken but that filesystem searches in ~/.sam_data,
        /tmp, and /private/tmp could never find: they were real files,
        saved to a real path, just not any path a person would think to
        check. (This was a deliberate prior decision, not an oversight —
        see git history — reasoned that hardcoding /tmp, as the vision
        module's own throwaway screenshots do, would break the Windows
        branch, since /tmp isn't a real directory there. That reasoning
        is correct about /tmp specifically; it doesn't apply to
        SCREENSHOTS_DIR below, which is built from
        os.path.expanduser("~") and is a real, writable location on
        Windows too.)

        Now defaults to SCREENSHOTS_DIR (~/.sam_data/screenshots/), a
        fixed, discoverable location consistent with this project's own
        "everything persists under ~/.sam_data" convention
        (config/settings.py's SAM_DATA_DIR) — creating the directory if
        it doesn't exist yet. An explicitly-passed `path` is used
        unchanged, exactly as before.
        """
        if path is None:
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SCREENSHOTS_DIR, f"screenshot_{timestamp}.png")
            candidate = path
            suffix = 1
            while os.path.exists(candidate):
                candidate = os.path.join(
                    SCREENSHOTS_DIR, f"screenshot_{timestamp}_{suffix}.png")
                suffix += 1
            path = candidate

        try:
            if self._pyautogui:
                self._pyautogui.screenshot(path)
            elif IS_MAC:
                result = subprocess.run(
                    [SCREENCAPTURE_BIN, "-x", path],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    diagnostic = (result.stderr or result.stdout or "").strip() or "no output"
                    raise RuntimeError(
                        f"screencapture failed (exit {result.returncode}): {diagnostic}")
            elif IS_WIN:
                self._screenshot_windows(path)
        except Exception as e:
            if IS_MAC:
                raise RuntimeError(
                    f"Screenshot capture failed: {e}. This is usually caused "
                    f"by macOS not having granted Screen Recording permission "
                    f"to the app SAM is running in — System Settings -> "
                    f"Privacy & Security -> Screen Recording — then fully "
                    f"quit and reopen the app (macOS requires a restart after "
                    f"granting this, not just re-running)."
                ) from e
            raise RuntimeError(f"Screenshot capture failed: {e}") from e

        return path

    def _screenshot_windows(self, path: str):
        """Windows screenshot via PIL or PowerShell."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
        except ImportError:
            ps_cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$s=[System.Windows.Forms.Screen]::PrimaryScreen; "
                f"$b=New-Object System.Drawing.Bitmap($s.Bounds.Width,$s.Bounds.Height); "
                f"$g=[System.Drawing.Graphics]::FromImage($b); "
                f"$g.CopyFromScreen($s.Bounds.Location,[System.Drawing.Point]::Empty,$s.Bounds.Size); "
                f"$b.Save('{path}')"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], check=True, timeout=15)

    def get_screen_size(self) -> tuple:
        if self._pyautogui:
            return self._pyautogui.size()
        return (1920, 1080)

    def get_mouse_position(self) -> tuple:
        if self._pyautogui:
            return self._pyautogui.position()
        return (0, 0)

    # ─── App Control ──────────────────────────────────────────────────────

    def open_app(self, app_name: str):
        """
        Open an application — cross-platform.

        Reform 5 (Hands reliability, Phase 3): on macOS, `tell
        application "{app_name}" to activate` only resolves if app_name
        is close enough to how Launch Services actually names the app.
        It previously used the raw name from the Brain's payload with no
        fallback, so "VS Code" (a completely natural thing to call it)
        failed outright even with Visual Studio Code installed and
        running, because AppleScript has no app literally named "VS
        Code" to find — same root cause, and the same shared-last-word
        heuristic, as agent/react_loop.py's _same_app() (which only
        verifies AFTER activation whether the right app came to the
        front — it can't fix a resolution failure before activation ever
        succeeds; this is that fix, one layer earlier).

        Resolution order, stopping at the first success:
          1. The name as given — most apps' real names, unchanged.
          2. A small known-alias table (MAC_APP_NAME_ALIASES) for common
             short names ("VS Code", "Chrome", ...) — not exclusive to
             any one app.
          3. A fuzzy match (substring, or shared last word) against the
             names of applications actually installed in /Applications,
             /System/Applications, and ~/Applications — the general
             fallback that covers names not in the small table above.
        Raises RuntimeError naming every name that was tried if all of
        them fail, rather than reporting only the first, literal
        failure.
        """
        if IS_MAC:
            self._open_app_mac(app_name)
        elif IS_WIN:
            self._win_open_app(app_name)
        logger.info(f"Opened app: {app_name}")

    def _open_app_mac(self, app_name: str):
        tried = [app_name]
        try:
            self._applescript(f'tell application "{app_name}" to activate')
            return
        except RuntimeError:
            pass

        for candidate in self._app_name_candidates(app_name):
            if candidate in tried:
                continue
            tried.append(candidate)
            try:
                self._applescript(f'tell application "{candidate}" to activate')
                logger.info(f"Resolved app name '{app_name}' -> '{candidate}'")
                return
            except RuntimeError:
                continue

        raise RuntimeError(
            f"Could not open '{app_name}' — tried {tried} and none "
            f"resolved to an installed application. It may not be "
            f"installed, or may be named differently than any of these."
        )

    @staticmethod
    def _app_name_candidates(app_name: str) -> list:
        """
        Builds an ordered list of alternate names to try for open_app()
        on macOS: the known-alias table first (instant, no filesystem
        access), then a fuzzy match against whatever is actually
        installed (substring or shared-last-word, same rule as
        agent/react_loop.py's _same_app — kept as an independent
        implementation here since hands/ doesn't import from agent/, per
        this project's existing pattern of small local duplication over
        cross-layer imports — see SCREENCAPTURE_BIN/SCREENSHOTS_DIR
        above). Directory scan errors (e.g. no permission) are swallowed
        — this is a best-effort fallback, not a required step.
        """
        candidates = []
        alias = MAC_APP_NAME_ALIASES.get(app_name.strip().lower())
        if alias:
            candidates.append(alias)

        requested = app_name.strip().lower()
        requested_words = requested.split()
        search_dirs = ["/Applications", "/System/Applications",
                       os.path.expanduser("~/Applications")]
        installed = []
        for d in search_dirs:
            try:
                installed.extend(
                    name[:-4] for name in os.listdir(d) if name.endswith(".app")
                )
            except OSError:
                continue

        for installed_name in installed:
            low = installed_name.strip().lower()
            if not low or low == requested:
                continue
            same_substring = requested in low or low in requested
            low_words = low.split()
            same_last_word = (requested_words and low_words
                               and requested_words[-1] == low_words[-1])
            if same_substring or same_last_word:
                candidates.append(installed_name)

        return candidates

    def close_app(self, app_name: str):
        """Close/quit an application — cross-platform."""
        if IS_MAC:
            self._applescript(f'tell application "{app_name}" to quit')
        elif IS_WIN:
            subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"],
                           capture_output=True)

    def _win_open_app(self, app_name: str):
        """Open app on Windows via start command."""
        # Map common app names to Windows executables
        win_app_map = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "chrome": "chrome.exe",
            "firefox": "firefox.exe",
            "edge": "msedge.exe",
            "word": "winword.exe",
            "excel": "excel.exe",
            "terminal": "wt.exe",        # Windows Terminal
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
        }
        exe = win_app_map.get(app_name.lower(), f"{app_name}.exe")
        try:
            subprocess.Popen(["start", exe], shell=True)
        except Exception:
            # Try pywinauto
            if self._winauto:
                self._winauto(backend="uia").start(exe)

    # ─── System Actions ───────────────────────────────────────────────────

    def set_volume(self, level: int):
        """Set system volume (0-100) cross-platform."""
        if IS_MAC:
            self._applescript(f"set volume output volume {level}")
        elif IS_WIN:
            # PowerShell via nircmd or built-in
            ps_cmd = (
                f"$obj = New-Object -ComObject WScript.Shell; "
                f"$obj.SendKeys([char]174)"  # Volume key simulation is limited
            )
            # Better: use nircmd if available
            try:
                subprocess.run(
                    ["nircmd.exe", "setsysvolume", str(int(level / 100 * 65535))],
                    check=True, capture_output=True
                )
            except Exception:
                logger.warning("nircmd not found — volume control limited on Windows")

    def notify(self, title: str, message: str):
        """Show system notification cross-platform."""
        if IS_MAC:
            self._applescript(
                f'display notification "{message}" with title "{title}"'
            )
        elif IS_WIN:
            ps_cmd = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                f"ContentType = WindowsRuntime] | Out-Null; "
                f"$t = [Windows.UI.Notifications.ToastNotificationManager]"
                f"::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText01); "
                f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}: {message}')) | Out-Null; "
                f"$n = [Windows.UI.Notifications.ToastNotification]::new($t); "
                f"[Windows.UI.Notifications.ToastNotificationManager]"
                f"::CreateToastNotifier('SAM').Show($n)"
            )
            subprocess.run(["powershell", "-Command", ps_cmd],
                           capture_output=True, timeout=10)

    def open_url_in_browser(self, url: str):
        """Open URL in default browser — cross-platform."""
        if IS_MAC:
            subprocess.run(["open", url])
        elif IS_WIN:
            subprocess.run(["start", url], shell=True)

    # ─── Clipboard ────────────────────────────────────────────────────────

    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard cross-platform."""
        if IS_MAC:
            subprocess.run(["pbcopy"], input=text.encode())
        elif IS_WIN:
            subprocess.run(["clip"], input=text.encode(), shell=True)

    def get_clipboard(self) -> str:
        """Get clipboard content cross-platform."""
        if IS_MAC:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return result.stdout
        elif IS_WIN:
            ps_cmd = "Get-Clipboard"
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True
            )
            return result.stdout.strip()
        return ""

    # ─── Window Info ──────────────────────────────────────────────────────

    def get_frontmost_app(self) -> str:
        """Get currently active application name."""
        if IS_MAC:
            return self._applescript(
                'tell application "System Events" to get name of first '
                'application process whose frontmost is true'
            )
        elif IS_WIN:
            ps_cmd = (
                "Add-Type @'\n"
                "using System;\nusing System.Runtime.InteropServices;\n"
                "public class WinAPI { [DllImport(\"user32.dll\")] "
                "public static extern IntPtr GetForegroundWindow(); }\n'@\n"
                "$hwnd = [WinAPI]::GetForegroundWindow();\n"
                "(Get-Process | Where-Object { $_.MainWindowHandle -eq $hwnd }).ProcessName"
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        return ""

    def get_all_windows(self) -> list:
        """Get all visible windows."""
        if IS_MAC:
            script = """
tell application "System Events"
    set windowList to {}
    repeat with aProcess in (every application process whose visible is true)
        repeat with aWindow in (every window of aProcess)
            set end of windowList to (name of aProcess) & ": " & (name of aWindow)
        end repeat
    end repeat
    return windowList
end tell
"""
            result = self._applescript(script)
            return result.split(", ") if result else []
        elif IS_WIN:
            ps_cmd = (
                "Get-Process | Where-Object {$_.MainWindowTitle} | "
                "Select-Object ProcessName, MainWindowTitle | "
                "ForEach-Object { $_.ProcessName + ': ' + $_.MainWindowTitle }"
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10
            )
            return [l for l in result.stdout.strip().split("\n") if l]
        return []

    # ─── AppleScript (macOS only) ─────────────────────────────────────────

    def _applescript(self, script: str) -> str:
        """
        Execute AppleScript and return its stdout. No-op on Windows.

        Raises RuntimeError (with osascript's own stderr) on failure
        instead of silently returning an empty string. Previously
        open_app()'s only caller reported "Opened: {app}" regardless of
        whether `tell application "{app}" to activate` actually resolved
        to a real, running application — same silent-failure shape as
        the _take_screenshot() fix in hands/vision/screen_reader.py, and
        the same fix. Confirmed no other caller in the codebase depends
        on this never raising (set_volume/notify/get_frontmost_app/
        get_all_windows/close_app currently have no external callers).
        """
        if not IS_MAC:
            logger.debug("AppleScript called on non-Mac — skipped")
            return ""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"osascript failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout or 'no output').strip()}"
            )
        return result.stdout.strip()

    # Keep public alias for any code that calls it directly
    def applescript(self, script: str) -> str:
        return self._applescript(script)

    def speak_text(self, text: str):
        """Emergency TTS via system — use mouth/tts.py instead."""
        if IS_MAC:
            subprocess.run(["say", text])
        elif IS_WIN:
            ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
            subprocess.run(["powershell", "-Command", ps_cmd], timeout=30)

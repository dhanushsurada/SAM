"""
THE HANDS — Vision
Takes screenshots and understands what's on screen.
Primary: Moondream (1.8B, fast)
Fallback: LLaVA (7B, more capable)
"""

import logging
import base64
import json
import subprocess
import tempfile
import requests
from pathlib import Path

logger = logging.getLogger("SAM.Vision")

# Absolute path to the macOS system binary — not subject to PATH manipulation,
# and guaranteed present on every real macOS install (unlike a bare
# "screencapture", which depends on the calling process's PATH being set up
# the way a normal Terminal session's is).
SCREENCAPTURE_BIN = "/usr/sbin/screencapture"


class ScreenReader:
    def __init__(self, settings):
        self.settings = settings

    def _take_screenshot(self) -> str:
        """
        Take a screenshot via macOS's screencapture and return the saved
        PNG's path.

        Raises RuntimeError (with the tool's own stderr plus a permission
        hint) instead of silently returning a path to a missing/corrupt
        image when capture itself fails. The most common real-world cause
        (see docs/VISION_COORDINATE_FIX.md item #1) is macOS not having
        granted Screen Recording permission to the app SAM is running in —
        previously this was invisible here and surfaced only as a
        confusing downstream "could not find X on screen" from
        find_element(), with no hint about the real cause.
        """
        path = tempfile.mktemp(suffix=".png", dir="/tmp")
        result = subprocess.run(
            [SCREENCAPTURE_BIN, "-x", path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout or "").strip() or "no output"
            raise RuntimeError(
                f"screencapture failed (exit {result.returncode}): {diagnostic}. "
                f"This is usually caused by macOS not having granted Screen "
                f"Recording permission to the app SAM is running in — System "
                f"Settings -> Privacy & Security -> Screen Recording — then "
                f"fully quit and reopen the app (macOS requires a restart after "
                f"granting this, not just re-running)."
            )
        return path

    def _image_to_base64(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def read(self, task: str = "Describe what you see on the screen") -> str:
        """
        Take a screenshot and ask the vision model to interpret it.
        Returns text description.
        """
        try:
            screenshot_path = self._take_screenshot()
            image_b64 = self._image_to_base64(screenshot_path)

            model = (
                "moondream" if self.settings.vision_model == "moondream"
                else "llava"
            )

            response = requests.post(
                f"{self.settings.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": task,
                    "images": [image_b64],
                    "stream": False
                },
                timeout=60
            )

            import os
            os.unlink(screenshot_path)

            if response.status_code == 200:
                result = response.json().get("response", "")
                logger.info(f"Vision result: {result[:100]}")
                return result
            else:
                return f"Vision error: {response.status_code}"

        except Exception as e:
            logger.error(f"Vision error: {e}", exc_info=True)
            return f"Could not read screen: {e}"

    def find_element(self, description: str) -> tuple:
        """
        Find an element on screen by description.
        Returns (x, y) PIXEL coordinates ready to click, or None.

        Bug fixed here (found via real Mac testing): Moondream returns
        NORMALIZED coordinates (0.0-1.0 fractional) for pointing tasks, not
        pixel coordinates. This code used to do int(x), int(y) directly on
        those fractions — e.g. (0.17, 0.18) became (0, 0), the literal
        top-left corner of the screen. Every click was aiming at the
        corner, which is exactly why PyAutoGUI's own fail-safe kept firing
        ("mouse moving to a corner of the screen") — nothing was actually
        moving there accidentally, it was being told to, every time.

        Also strips a leading action-verb phrase ("click on ", "tap ",
        "select ", etc.) from the description before asking the vision
        model to find it. core/brain.py's own action-payload prompt
        example shows `{"type": "click", "description": "click the send
        button"}` — so the Brain reliably produces descriptions like
        "click the Visual Studio Code application in the search results"
        (the exact phrase from real testing that vision then failed to
        find). Moondream is asked to point at a visual object, not parse
        an imperative sentence, so stripping the verb before it ever
        reaches the prompt makes matching noticeably more reliable.

        Coordinate convention (Reform 2, Hands reliability Phase 3 —
        documenting this end-to-end per that phase's request, after
        verifying the math against the code rather than assuming it
        needs to change for Retina displays):

            vision model output  →  normalized (x, y), each 0.0-1.0,
                                     as a FRACTION of the screenshot
                                     image _take_screenshot() actually
                                     captured (via macOS's
                                     `screencapture`, at that display's
                                     real backing resolution — 2x/3x
                                     pixels on Retina).
            _to_pixel_coords()    →  pixel = fraction * pyautogui.size()
                                     — pyautogui.size() returns the
                                     LOGICAL/point resolution, the same
                                     coordinate space pyautogui.click()
                                     itself expects.
            ComputerController    →  click(pixel_x, pixel_y) — same
                                     space as pyautogui.size(), so this
                                     is self-consistent by construction.

        This is already correct on a Retina display, and NOT because the
        scale factor is being tracked anywhere — it's sidestepped
        entirely. A normalized fraction is resolution-independent: (0.5,
        0.5) means "the middle of the image" whether that image is
        1512x982 or a 2x-Retina 3024x1964 capture of the exact same
        screen. Scaling that fraction by pyautogui.size() (rather than by
        the screenshot's own raw pixel dimensions) is what keeps the
        result correct regardless of backing scale factor, since
        pyautogui.size() and pyautogui.click() always agree with each
        other on what coordinate space they're using, whatever it
        actually is on a given platform. Changing this to account for
        Retina scaling explicitly, as one might reflexively expect to
        need to, would be a bug, not a fix — it would double-apply a
        correction this design already gets for free.
        """
        try:
            clean_description = self._clean_target_description(description)
            screenshot_path = self._take_screenshot()
            image_b64 = self._image_to_base64(screenshot_path)

            prompt = f"""Look at this screenshot and find: {clean_description}
Return ONLY this JSON, nothing else — no explanation, no extra text:
{{"x": 0.0, "y": 0.0}}
Where x and y are the NORMALIZED position as a fraction of screen width/height,
each between 0.0 and 1.0 (e.g. center of screen is {{"x": 0.5, "y": 0.5}}).
If not found, return: {{"x": null, "y": null}}"""

            model = "moondream" if self.settings.vision_model == "moondream" else "llava"

            response = requests.post(
                f"{self.settings.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1, "num_predict": 60}
                },
                timeout=60
            )

            import os
            os.unlink(screenshot_path)

            if response.status_code != 200:
                return None

            raw = response.json().get("response", "{}")
            x, y = self._parse_coordinates(raw)
            if x is None or y is None:
                return None

            # Bug fixed here (found via more real Mac testing, AFTER the
            # int()-truncation fix above already shipped): the scaling
            # math was correct, but Moondream itself was returning literal
            # (0.0, 0.0) as its ANSWER when it couldn't actually find the
            # element — a well-known degenerate-guess failure mode in
            # vision-language models asked for coordinates (collapsing to
            # the origin instead of honestly returning the null/not-found
            # case it was explicitly instructed to use). No real on-screen
            # element is ever at the literal top-left corner pixel in
            # practice, so treat that exact answer as "not found" rather
            # than proceeding to click it — converts a guaranteed
            # PyAutoGUI fail-safe crash into a clean, retryable
            # "could not find X" result instead.
            if abs(x) < 1e-6 and abs(y) < 1e-6:
                logger.warning(f"Vision returned (0,0) for '{clean_description}' — "
                                f"treating as not-found rather than clicking the corner")
                return None

            pixel_x, pixel_y = self._to_pixel_coords(x, y)

            # Phase 3 (Hands reliability): the same "not found" treatment
            # as the (0,0) check above, extended to any result that lands
            # outside the real screen entirely — e.g. the model returning
            # a value that isn't actually a 0.0-1.0 fraction (so
            # _to_pixel_coords' defensive raw-pixel passthrough kicks in)
            # and produces something like (5000, 3). No real on-screen
            # element can be there, so this is caught here — with a
            # specific, logged reason — rather than passed through to
            # ComputerController.click(), which would also refuse it, but
            # two layers away and without knowing this was a vision
            # answer rather than a bad coordinate from anywhere else.
            width, height = self._get_screen_size()
            if not (0 <= pixel_x <= width) or not (0 <= pixel_y <= height):
                logger.warning(f"Vision returned out-of-bounds pixel "
                                f"({pixel_x}, {pixel_y}) for "
                                f"'{clean_description}' on a {width}x{height} "
                                f"screen — treating as not-found")
                return None

            logger.info(f"Found '{clean_description}' at normalized ({x:.3f}, {y:.3f}) "
                        f"-> pixel ({pixel_x}, {pixel_y})")
            return (pixel_x, pixel_y)

        except Exception as e:
            logger.error(f"Element finding error: {e}")
            return None

    _ACTION_VERB_PREFIXES = (
        "double click on ", "double-click on ", "double click ", "double-click ",
        "right click on ", "right-click on ", "right click ", "right-click ",
        "click on ", "click ", "tap on ", "tap ", "select ", "press ", "choose ",
    )

    @classmethod
    def _clean_target_description(cls, description: str) -> str:
        """
        Strips ONE leading action-verb phrase (see _ACTION_VERB_PREFIXES)
        from a target description before it's sent to the vision model —
        e.g. "click the Visual Studio Code application in the search
        results" becomes "the Visual Studio Code application in the
        search results". Does not otherwise rewrite the description, and
        leaves it unchanged if it doesn't start with a known verb phrase
        (e.g. "play the video", "center button" pass through untouched).
        """
        text = (description or "").strip()
        lowered = text.lower()
        for prefix in cls._ACTION_VERB_PREFIXES:
            if lowered.startswith(prefix):
                stripped = text[len(prefix):].strip()
                return stripped or text
        return text

    @staticmethod
    def _parse_coordinates(raw: str):
        """
        Parses the vision model's response for x/y. Tries strict JSON
        first; falls back to a regex scan if the model added stray text
        around the JSON or truncated it (both seen in real testing —
        "Unterminated string...", "Expecting value..." errors were this).
        """
        try:
            parsed = json.loads(raw)
            x, y = parsed.get("x"), parsed.get("y")
            if x is not None and y is not None:
                return float(x), float(y)
            return None, None
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        import re
        x_match = re.search(r'"?x"?\s*:\s*(-?[\d.]+)', raw)
        y_match = re.search(r'"?y"?\s*:\s*(-?[\d.]+)', raw)
        if x_match and y_match:
            try:
                return float(x_match.group(1)), float(y_match.group(1))
            except ValueError:
                pass
        return None, None

    def _to_pixel_coords(self, x: float, y: float) -> tuple:
        """Scales normalized (0.0-1.0) coordinates to real screen pixels.
        Defensively handles a model returning raw pixels instead (values
        outside 0-1) by passing them through unchanged."""
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            width, height = self._get_screen_size()
            return int(x * width), int(y * height)
        return int(x), int(y)

    @staticmethod
    def _get_screen_size() -> tuple:
        try:
            import pyautogui
            return pyautogui.size()
        except Exception as e:
            logger.warning(f"Could not get screen size, defaulting to 1920x1080: {e}")
            return (1920, 1080)

    def read_text_on_screen(self) -> str:
        """Extract all text visible on screen."""
        return self.read("Read and transcribe all text visible on the screen. Be thorough.")

    def describe_current_state(self) -> str:
        """Get a full description of the current screen state."""
        return self.read(
            "Describe what application is open and what the user can see on screen. "
            "Include any important UI elements, text, or content."
        )

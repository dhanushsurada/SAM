"""
THE HANDS — Browser Agent
Playwright-powered autonomous browser control.
Opens URLs, fills forms, extracts data, navigates pages.
"""

import logging
import json
import threading
from typing import Optional

logger = logging.getLogger("SAM.Browser")


class BrowserAgent:
    def __init__(self):
        self._playwright_ctx = None
        self._browser = None
        self._page = None
        self._started = False
        # Bug fixed here (found via real Mac testing): Playwright's sync API
        # binds its dispatcher to whichever OS thread created it — it is
        # NOT safe to call from a different thread. main.py's input
        # handling spawns a fresh thread per message, so turn 2's browser
        # call could land on a completely different thread than turn 1's —
        # and turn 1's thread has since exited, permanently breaking every
        # future browser call for the rest of the session with
        # "cannot switch to a different thread (which happens to have
        # exited)". This was confirmed in testing: the FIRST turn's
        # multi-step browser use worked flawlessly (same thread throughout
        # that one turn), but the very next separate message's first
        # browser call failed immediately, and every one after that failed
        # identically for the rest of the session.
        self._owner_thread_id = None

    def _start(self):
        current_thread_id = threading.get_ident()

        if self._started and self._owner_thread_id != current_thread_id:
            logger.warning(
                f"Browser called from a different thread (was "
                f"{self._owner_thread_id}, now {current_thread_id}) — "
                f"recreating the browser session on this thread instead "
                f"of staying permanently broken."
            )
            self._force_close()

        if self._started:
            return

        try:
            from playwright.sync_api import sync_playwright
            self._playwright_ctx = sync_playwright().__enter__()
            self._browser = self._playwright_ctx.chromium.launch(
                headless=False  # Visible so user can see what SAM is doing
            )
            self._page = self._browser.new_page()
            self._started = True
            self._owner_thread_id = current_thread_id
            logger.info("Playwright browser started")
        except ImportError:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    def _force_close(self):
        """
        Tears down a browser session that may already be broken (e.g.
        bound to a thread that has exited). Best-effort and swallows
        errors on purpose — closing a cross-thread-bound Playwright object
        can itself raise the exact same thread error we're recovering
        from, and the goal here is recovery, not a clean shutdown. Any
        resources that can't be closed cleanly are abandoned rather than
        left blocking a fresh, working browser from being created.
        """
        try:
            if self._browser:
                self._browser.close()
        except Exception as e:
            logger.debug(f"Old browser close failed (expected if cross-thread): {e}")
        try:
            if self._playwright_ctx:
                self._playwright_ctx.__exit__(None, None, None)
        except Exception as e:
            logger.debug(f"Old playwright context close failed (expected if cross-thread): {e}")

        self._browser = None
        self._page = None
        self._playwright_ctx = None
        self._started = False

    @staticmethod
    def _is_thread_affinity_error(e: Exception) -> bool:
        msg = str(e).lower()
        return "cannot switch to a different thread" in msg or "greenlet" in msg

    def execute(self, url: str = "", task: str = "") -> str:
        """
        Navigate to URL and complete the given task. Returns result as text.

        Second bug fixed here, found by testing the FIRST fix attempt
        before shipping it: the _owner_thread_id check in _start() above
        is a fast-path that catches a thread mismatch proactively WHEN it
        can — but it is NOT reliable on its own. When threads run
        sequentially and don't overlap (the normal case here — turn 1's
        thread fully exits before turn 2's thread is even created), the OS
        frequently reuses the exact same thread ID for the new thread, so
        a simple ID comparison can miss the staleness entirely. Confirmed
        this with a test mirroring the real sequential-thread scenario —
        the ID-only version silently kept using the dead page.

        The actual guarantee comes from here instead: if a call still
        fails with the thread-affinity error message (regardless of why
        the proactive check didn't catch it), tear down and recreate the
        browser and retry the SAME call once, transparently. This is
        correct regardless of thread ID reuse, because it reacts to the
        real failure instead of trying to predict it in advance.
        """
        self._start()

        try:
            return self._do_execute(url, task)
        except Exception as e:
            if self._is_thread_affinity_error(e):
                logger.warning(f"Stale cross-thread browser session ({e}) — "
                                f"recreating and retrying once.")
                self._force_close()
                self._start()
                try:
                    return self._do_execute(url, task)
                except Exception as e2:
                    logger.error(f"Browser error after recreation retry: {e2}", exc_info=True)
                    return f"Browser error: {e2}"
            logger.error(f"Browser error: {e}", exc_info=True)
            return f"Browser error: {e}"

    def _do_execute(self, url: str, task: str) -> str:
        if url:
            logger.info(f"Navigating to: {url}")
            # Reform 7 (Hands reliability, Phase 3): was
            # wait_until="networkidle" here. That waits for 500ms with NO
            # network activity at all -- fine for a static page, but
            # pages that keep a persistent connection open (analytics
            # beacons, websockets, polling) never go idle, so this could
            # silently eat the entire 30s timeout before falling through.
            # YouTube is exactly this kind of page. domcontentloaded
            # fires promptly and reliably instead; _settle() below adds a
            # short, BOUNDED best-effort wait on top for pages that do
            # finish loading data quickly, without blocking on ones that
            # never will.
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._settle()

        if not task:
            return self._get_page_content()

        return self._perform_task(task)

    def _settle(self, timeout_ms: int = 4000):
        """
        Best-effort, bounded wait for the page to go quiet after a
        navigation or a click that may have triggered one (a full page
        load or an SPA-style client-side transition) — reduces the
        "read/click before the page actually finished rendering" race
        that previously showed up as intermittent "No content found" on
        pages with real content. Deliberately NOT the primary gate (see
        _do_execute) — just a capped top-up on top of domcontentloaded,
        so a page that never goes fully idle (YouTube, most SPAs) simply
        proceeds after timeout_ms instead of blocking the task.
        """
        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass  # Never idle, or timed out -- proceed with what's loaded.

    def _perform_task(self, task: str) -> str:
        """Perform a specific task on the current page."""
        task_lower = task.lower()

        if "extract" in task_lower or "get" in task_lower or "find" in task_lower or "read" in task_lower:
            return self._extract_content(task)
        elif "click" in task_lower:
            return self._smart_click(task)
        elif "fill" in task_lower or "type" in task_lower or "enter" in task_lower:
            return self._smart_fill(task)
        elif "scroll" in task_lower:
            self._page.evaluate("window.scrollBy(0, 500)")
            return "Scrolled down"
        else:
            return self._extract_content(task)

    def _extract_content(self, task: str) -> str:
        """Extract text content from the page."""
        try:
            # Get all text from page
            content = self._page.evaluate("""() => {
                return document.body.innerText;
            }""")
            # Truncate to reasonable length
            return content[:3000] if content else "No content found"
        except Exception as e:
            return f"Could not extract content: {e}"

    # Words stripped from a click task before it's tried as a page-text
    # match — verbs and generic filler that would never appear as the
    # actual label of the thing being clicked.
    _CLICK_FILLER_WORDS = {
        "click", "clicking", "select", "selecting", "choose", "choosing",
        "the", "a", "an", "on", "to", "please", "now", "then", "and",
        "first", "top", "result", "results", "item", "option", "link",
        "button", "video", "play", "open", "watch", "titled", "called",
        "named",
    }

    @classmethod
    def _extract_click_targets(cls, task: str) -> list:
        """
        Builds an ordered list of candidate strings to try matching
        against the page's text, most specific first. Replaces the old
        strategy of trying every word longer than 3 characters in
        left-to-right order — on a content-dense page (a YouTube search
        results list, full of recommended/related text) that reliably
        clicked the first coincidental word match rather than the
        actually-requested item, which is the direct, evidenced cause of
        "can reach the search results but has difficulty actually
        clicking/selecting a video."

        Order:
          1. Any quoted phrase in the task ("..." or '...') — the
             clearest possible signal of an exact on-page label/title.
          2. The task with a leading click/select verb and generic
             filler words stripped, kept as ONE phrase — catches a
             title the Brain wrote out without quotes.
          3. Individual remaining significant words (len > 3), longest
             first rather than left-to-right — last-resort fallback,
             kept from the original implementation, but preferring the
             most specific (least likely to coincidentally match
             something else) word first.
        """
        import re
        candidates = []

        for quoted in re.findall(r'"([^"]{3,80})"|\'([^\']{3,80})\'', task):
            phrase = (quoted[0] or quoted[1]).strip()
            if phrase and phrase not in candidates:
                candidates.append(phrase)

        all_words = [w.strip("'\"") for w in re.findall(r"[A-Za-z0-9'-]+", task)]
        all_words = [w for w in all_words if w]
        meaningful = [w for w in all_words if w.lower() not in cls._CLICK_FILLER_WORDS]

        if meaningful:
            phrase = " ".join(meaningful)
            if phrase not in candidates:
                candidates.append(phrase)

        # Last-resort word pool: normally the filler-stripped words above,
        # but a fully generic task ("click the first video result", no
        # title or other distinguishing text at all) filters down to
        # nothing there — falling back to every word minus just the
        # leading verb means something is still attempted, matching what
        # the word-by-word strategy this replaces would at least try,
        # rather than giving up before a single click.
        word_pool = meaningful or [
            w for w in all_words
            if w.lower() not in ("click", "clicking", "select", "selecting",
                                  "choose", "choosing", "the", "a", "an")
        ]
        # Dedup while preserving first-occurrence order before sorting by
        # length: sorting a *set* of same-length words would tie-break
        # using Python's per-process string-hash randomization, making
        # the fallback order non-deterministic between runs for no
        # benefit. A stable sort over an order-preserving list makes the
        # tie-break "whichever word appeared first in the task text" —
        # deterministic and easier to reason about when debugging.
        seen = set()
        ordered_unique = []
        for w in word_pool:
            if len(w) > 3 and w not in seen:
                seen.add(w)
                ordered_unique.append(w)
        for word in sorted(ordered_unique, key=len, reverse=True):
            if word not in candidates:
                candidates.append(word)

        return candidates

    def _smart_click(self, task: str) -> str:
        """
        Find and click an element based on a free-text task description.

        Tries each candidate from _extract_click_targets() in order
        (most specific first) via Playwright's get_by_text(exact=False)
        — a case-insensitive substring match against the page's actual
        text, scoped with .first so a phrase matching several elements
        still resolves to one rather than raising strict-mode ambiguity.

        Verification (Reform 7/9): captures the page URL before and
        after the click, with a bounded settle wait in between so an
        SPA-style transition has a chance to land first. A changed URL
        is real, cheap, reliable evidence the click actually navigated
        somewhere — not just that Playwright's click() call returned.
        Phrasing below is deliberately aligned with the SAME failure
        vocabulary agent/verifier.py already recognizes from the control
        (vision/PyAutoGUI) click path ("could not find", "may not have
        registered") — one Verifier failure-signal list covers both
        click paths, control and browser, with no changes needed there.
        """
        try:
            candidates = self._extract_click_targets(task)
            if not candidates:
                return "Could not find element to click — no clear target in the task description"

            before_url = self._page.url
            for candidate in candidates:
                try:
                    self._page.get_by_text(candidate, exact=False).first.click(timeout=5000)
                except Exception:
                    continue

                self._settle()
                after_url = self._page.url
                if after_url != before_url:
                    return (f"Clicked element matching '{candidate}'; page navigated "
                            f"from {before_url} to {after_url} — consistent with the "
                            f"click taking effect.")
                return (f"Clicked element matching '{candidate}', but the page URL "
                        f"is still {after_url} afterward — the click may not have "
                        f"registered, or this page updates without a URL change.")

            return f"Could not find element to click for: {task}"
        except Exception as e:
            return f"Click error: {e}"

    def _smart_fill(self, task: str) -> str:
        """Fill a form field."""
        try:
            # Try focused element first
            self._page.keyboard.type(task.split("type")[-1].strip())
            return f"Typed in focused field"
        except Exception as e:
            return f"Fill error: {e}"

    def _get_page_content(self) -> str:
        """Get current page title and brief content."""
        title = self._page.title()
        url = self._page.url
        content = self._page.evaluate("() => document.body.innerText")
        return f"Page: {title}\nURL: {url}\n\n{content[:1000]}"

    def screenshot(self, path: str = None) -> str:
        """Take screenshot of browser page."""
        if path is None:
            import tempfile
            path = tempfile.mktemp(suffix=".png")
        self._page.screenshot(path=path)
        return path

    def get_page_url(self) -> str:
        return self._page.url if self._page else ""

    def close(self):
        if self._started:
            try:
                self._browser.close()
                self._playwright_ctx.__exit__(None, None, None)
                self._started = False
            except Exception:
                pass

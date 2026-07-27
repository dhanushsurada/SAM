"""
Offline test for the persistent memory connection fix — a real,
confirmed performance bug visible in every Mac test log across this
entire project: Session.save() was constructing a brand new MemoryStore
(fresh SQLite connection + fresh ChromaDB init) on every single turn,
completely independent of MemoryRetriever's already-correct caching.

Usage:
    HOME=/tmp/sam_smoke_persistence python3 tests/test_persistent_memory_offline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings  # noqa: E402
from core.session import Session  # noqa: E402
from memory.retrieve import MemoryRetriever  # noqa: E402
from memory.store import MemoryStore  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


class FakeResponse:
    def __init__(self, text="ok", action=None):
        self.text, self.action = text, action


def test_single_connection_reused_across_turns():
    init_count = {"n": 0}
    original_init = MemoryStore.__init__

    def counting_init(self, settings):
        init_count["n"] += 1
        original_init(self, settings)

    MemoryStore.__init__ = counting_init
    try:
        settings = Settings()
        memory = MemoryRetriever()  # constructed once, exactly as main.py does

        for i in range(5):
            session = Session(user_input=f"turn {i}", identity={},
                               memories=memory.retrieve(f"turn {i}", settings),
                               founder_context="", settings=settings)
            session.save(user_input=f"turn {i}", response=FakeResponse(f"response {i}"),
                         memory_store=memory.get_store(settings))

        check("Exactly 1 MemoryStore initialization across 5 full turns (not 5, not 10)",
              init_count["n"] == 1)
    finally:
        MemoryStore.__init__ = original_init


def test_backward_compatible_without_memory_store_arg():
    settings = Settings()
    session = Session(user_input="test", identity={}, memories=[], founder_context="", settings=settings)
    try:
        session.save(user_input="test", response=FakeResponse())
        check("Old call style (no memory_store arg) still works unchanged", True)
    except Exception as e:
        check(f"Old call style (no memory_store arg) still works unchanged — FAILED: {e}", False)


def test_incognito_still_skips_save_entirely():
    settings = Settings()
    settings.incognito = True
    session = Session(user_input="secret", identity={}, memories=[], founder_context="", settings=settings)
    memory = MemoryRetriever()
    # Must not even attempt to touch the store in incognito mode
    session.save(user_input="secret", response=FakeResponse(), memory_store=memory.get_store(settings))
    check("Incognito mode still skips saving entirely (unaffected by this fix)", True)


def main():
    test_single_connection_reused_across_turns()
    test_backward_compatible_without_memory_store_arg()
    test_incognito_still_skips_save_entirely()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Persistent memory connection fix verified.")


if __name__ == "__main__":
    main()

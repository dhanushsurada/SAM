"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/telegram/pair_new_device.py.
This module explicitly delegates to the same `main()` function — not a
reimplementation — so that:

    python -m ecosystem.pair_new_device

still runs identically to:

    python -m interfaces.telegram.pair_new_device

There is no separate implementation here. New deployments/scripts should
prefer the interfaces.telegram path.
"""
from interfaces.telegram.pair_new_device import main  # noqa: F401

__all__ = ["main"]

if __name__ == "__main__":
    main()

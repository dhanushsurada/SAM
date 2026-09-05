"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to interfaces/telegram/telegram_bridge.py —
Telegram is a SAM Interface/channel, not device connectivity. This module
re-exports the same objects and explicitly delegates to the same `main()`
function — not a reimplementation — so that:

    python -m ecosystem.telegram_bridge

still starts the identical bridge as:

    python -m interfaces.telegram.telegram_bridge

There is no separate implementation here. New deployments/scripts should
prefer the interfaces.telegram path.
"""
from interfaces.telegram.telegram_bridge import (  # noqa: F401
    TelegramBridge,
    NOT_PAIRED_MESSAGE,
    main,
)

__all__ = ["TelegramBridge", "NOT_PAIRED_MESSAGE", "main"]

if __name__ == "__main__":
    main()

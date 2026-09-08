"""
SAM Runtime — process lifecycle for SAM's standalone entry points.

Phase 3B, Checkpoint 3 (see docs/iqoo/PHASE_3A5_MIGRATION.md for the prior
phase; this phase's own migration doc lands at Checkpoint 7).

SAM currently starts as three independent, uncoordinated processes,
confirmed by the Checkpoint 1 audit:

    main.py                                   the voice/text assistant
    interfaces/api/server.py                  the phone task gateway (FastAPI)
    interfaces/telegram/telegram_bridge.py    the Telegram remote-control bridge

`runtime` does not change what any of the three do, and does not implement
reasoning, planning, memory, or verification (that stays in core/ and
agent/ — Section 20). It only manages *whether they are running*: start,
stop, restart today; status/health join in Checkpoint 4. It is not coupled
to vivo/iQOO, Telegram, or the web UI specifically (Section 19) — those are
just three ProcessSpecs it happens to know about via
runtime.lifecycle.specs.default_specs().
"""

from runtime.health.status import RuntimeStatus
from runtime.lifecycle.manager import SAMRuntime
from runtime.lifecycle.specs import ProcessSpec, default_specs

__all__ = ["SAMRuntime", "ProcessSpec", "default_specs", "RuntimeStatus"]

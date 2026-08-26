"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation (FastAPI app, routes, static-file mount) moved to
interfaces/api/server.py. This module re-exports the same `app` object and
explicitly delegates to the same `main()` function — not a reimplementation
— so that:

    python -m iqoo.server

still starts the identical server (same app, same uvicorn.run() call,
same host/port) as:

    python -m interfaces.api.server

There is no separate implementation here; `app` below IS
interfaces.api.server.app, and `main` below IS interfaces.api.server.main.

New deployments/scripts should prefer `python -m interfaces.api.server`.
The API routes themselves are unchanged either way: /api/iqoo/tasks,
/api/iqoo/health, etc. — this migration only moved Python import paths, not
the HTTP contract.
"""
from interfaces.api.server import app, main  # noqa: F401

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()

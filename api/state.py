"""
Shared engine singletons for the VEDA localhost API (M8-A).

Deliberately has NO fastapi/pydantic import. This module constructs the
same long-lived objects main.py's SAM.__init__ constructs (Settings,
Identity, Brain, ReactLoop, VectorIndex) exactly once for the life of
the process, in the same order, for the same reason main.py does it:
these classes do real I/O in their constructors (Settings resolves
hardware, Identity touches ~/.sam_data, Brain talks to Ollama), so
constructing a fresh set per request would be wasteful and — for
Identity in particular — actively wrong.

Being fastapi-free means everything in here (and in task_runner.py and
uploads.py, which import from here) can be exercised directly by a
plain Python test, the same way the repo's own agent/sovereign tests
already exercise ReactLoop/run_task_with_optional_sovereign_mode,
without needing fastapi/uvicorn installed. Only api/app.py — pure HTTP
glue — actually needs fastapi.
"""

import threading

from config.settings import Settings
from core.brain import Brain
from memory.identity import Identity
from agent.react_loop import ReactLoop
from sovereign.knowledge import VectorIndex
from api.task_runner import TaskManager

settings = Settings()
identity = Identity()
brain = Brain(settings)
react_loop = ReactLoop(settings)
vector_index = VectorIndex(settings)
task_manager = TaskManager(settings, identity, brain, react_loop)

# Presentation-only registry of what's been uploaded through the API, for
# GET /api/documents. The engine has no equivalent concept of its own —
# index_file()/ingest_with_settings() are stateless per call — so this is
# new state the API layer legitimately owns, not a duplication of
# anything that already exists elsewhere.
documents: list = []
documents_lock = threading.Lock()

PRODUCT_NAME = "VEDA — Sovereign Industrial AI Workbench"

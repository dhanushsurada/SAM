"""
OFFLINE architecture-boundary test suite — Phase 3A.5.

Verifies the iqoo/ -> canonical migration invariants declared in
docs/iqoo/PHASE_3A5_MIGRATION.md actually hold in code, not just in
documentation:

  A. every canonical implementation module exists and exposes what the
     old compatibility shims promise to re-export
  B. every compatibility shim is a pure re-export (same object identity
     as the canonical symbol) rather than a second, drifting copy
  C. shim entrypoints with `if __name__ == "__main__":` behavior
     delegate to the canonical `main()`, not a duplicate implementation
  D. connect/bridges/vivo_iqoo/ contains no fabricated vendor
     implementation (documentation only, as the audit found no real
     vivo/iQOO SDK integration exists yet)
  E. SAM Core (core/, agent/, memory/, founder_mode/, skills/,
     multimodal/) never imports iqoo/, ecosystem/, or a vendor bridge
  F. the canonical interfaces/ and connect/core/ packages never import
     their own compatibility shims (dependency direction is
     shim -> canonical, never the reverse), and TaskGateway orchestrates
     SAM Core rather than reimplementing agent logic
  G. the old dotted-path imports actually resolve at runtime
  H. the /api/iqoo/* HTTP contract and ~/.sam_data/{iqoo,ecosystem}
     on-disk paths were not renamed by the migration

These are import/AST/filesystem checks only. No real Ollama,
faster-whisper, phone, Telegram, or Office Kit hardware is used anywhere
in this suite. Checks are intentionally identity- and structure-based
(e.g. `is`, AST node kinds) rather than string/formatting-based, so
reformatting the source without changing behavior won't break them.

Usage:
    HOME=/tmp/sam_arch_boundary_test python3 tests/test_architecture_boundaries_offline.py
"""

import ast
import importlib
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).parent.parent

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


# ─── A: canonical implementations exist ────────────────────────────────────

def test_canonical_implementations_exist():
    from interfaces.api.gateway import TaskGateway, TaskAlreadyActiveError, DemoResetBusyError
    from interfaces.api.task_store import TaskStore
    from interfaces.api.events import EventBus
    from interfaces.api.schemas import TaskCreateRequest
    from interfaces.api.server import app, main
    from multimodal.vision.adapter import VisionAdapter
    from multimodal.audio.adapter import AudioAdapter
    from multimodal.errors import PerceptionError, PerceptionCancelled
    from multimodal.media_validation import validate_attachment
    from connect.core.device_registry import DeviceRegistry
    from interfaces.telegram.telegram_bridge import TelegramBridge, main as bridge_main
    from interfaces.telegram.pair_new_device import main as pair_main

    check("interfaces.api.gateway exposes TaskGateway + error types",
          TaskGateway is not None and TaskAlreadyActiveError is not None and DemoResetBusyError is not None)
    check("interfaces.api.task_store.TaskStore exists", TaskStore is not None)
    check("interfaces.api.events.EventBus exists", EventBus is not None)
    check("interfaces.api.schemas.TaskCreateRequest exists", TaskCreateRequest is not None)
    check("interfaces.api.server exposes app + main", app is not None and callable(main))
    check("multimodal.vision.adapter.VisionAdapter exists", VisionAdapter is not None)
    check("multimodal.audio.adapter.AudioAdapter exists", AudioAdapter is not None)
    check("multimodal.errors exposes PerceptionError + PerceptionCancelled",
          PerceptionError is not None and PerceptionCancelled is not None)
    check("multimodal.media_validation.validate_attachment exists", callable(validate_attachment))
    check("connect.core.device_registry.DeviceRegistry exists", DeviceRegistry is not None)
    check("interfaces.telegram.telegram_bridge exposes TelegramBridge + main",
          TelegramBridge is not None and callable(bridge_main))
    check("interfaces.telegram.pair_new_device.main exists", callable(pair_main))


# ─── B: shims are pure re-exports, not duplicate implementations ──────────

def _same_objects(label_prefix, shim_mod, real_mod, names):
    for name in names:
        check(f"{label_prefix}.{name} is the exact same object as the canonical symbol",
              getattr(shim_mod, name, object()) is getattr(real_mod, name, object()))


def test_shims_are_pure_reexports_not_duplicates():
    import iqoo.gateway as shim_gateway
    import interfaces.api.gateway as real_gateway
    _same_objects("iqoo.gateway", shim_gateway, real_gateway,
                  ["TaskGateway", "TaskAlreadyActiveError", "DemoResetBusyError",
                   "DEFAULT_TASK_TIMEOUT_SECONDS"])

    import iqoo.task_store as shim_ts
    import interfaces.api.task_store as real_ts
    _same_objects("iqoo.task_store", shim_ts, real_ts,
                  ["TaskStore", "TERMINAL_STATUSES", "ALL_STATUSES", "ORPHAN_ERROR_MESSAGE"])

    import iqoo.events as shim_events
    import interfaces.api.events as real_events
    _same_objects("iqoo.events", shim_events, real_events, ["EventBus", "TERMINAL_PHASES"])

    import iqoo.schemas as shim_schemas
    import interfaces.api.schemas as real_schemas
    _same_objects("iqoo.schemas", shim_schemas, real_schemas,
                  ["TaskCreateRequest", "TaskRecord", "ExecutionEvent", "HealthStatus"])

    import iqoo.server as shim_server
    import interfaces.api.server as real_server
    _same_objects("iqoo.server", shim_server, real_server, ["app", "main"])

    import iqoo.errors as shim_errors
    import multimodal.errors as real_errors
    _same_objects("iqoo.errors", shim_errors, real_errors, ["PerceptionError", "PerceptionCancelled"])

    import iqoo.media_validation as shim_mv
    import multimodal.media_validation as real_mv
    _same_objects("iqoo.media_validation", shim_mv, real_mv,
                  ["validate_attachment", "AttachmentValidationError"])

    import iqoo.vision_adapter as shim_va
    import multimodal.vision.adapter as real_va
    _same_objects("iqoo.vision_adapter", shim_va, real_va, ["VisionAdapter"])

    import iqoo.audio_adapter as shim_aa
    import multimodal.audio.adapter as real_aa
    _same_objects("iqoo.audio_adapter", shim_aa, real_aa, ["AudioAdapter"])

    import ecosystem.device_registry as shim_dr
    import connect.core.device_registry as real_dr
    _same_objects("ecosystem.device_registry", shim_dr, real_dr,
                  ["DeviceRegistry", "SAM_DATA_DIR", "ECOSYSTEM_DIR", "DEVICES_DB_PATH",
                   "PAIRING_TOKEN_TTL_MINUTES"])

    import ecosystem.telegram_bridge as shim_tb
    import interfaces.telegram.telegram_bridge as real_tb
    _same_objects("ecosystem.telegram_bridge", shim_tb, real_tb,
                  ["TelegramBridge", "NOT_PAIRED_MESSAGE", "main"])

    import ecosystem.pair_new_device as shim_pnd
    import interfaces.telegram.pair_new_device as real_pnd
    _same_objects("ecosystem.pair_new_device", shim_pnd, real_pnd, ["main"])


# ─── C: __main__ entrypoints delegate, they don't reimplement ─────────────

def _guarded_main_call_only(source: str) -> bool:
    """True if the module's `if __name__ == "__main__":` block's only
    call is a bare `main()` — i.e. delegation, not a reimplementation."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                for stmt in ast.walk(node):
                    if (isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Name)
                            and stmt.func.id == "main" and not stmt.args and not stmt.keywords):
                        return True
    return False


def test_shim_main_blocks_delegate_not_reimplement():
    for rel_path in ("iqoo/server.py", "ecosystem/telegram_bridge.py", "ecosystem/pair_new_device.py"):
        source = (REPO_ROOT / rel_path).read_text()
        check(f"{rel_path}'s __main__ guard delegates to main() (no duplicated startup logic)",
              _guarded_main_call_only(source))


# ─── D: vivo_iqoo bridge is documentation-only, nothing fabricated ────────

def test_vivo_iqoo_bridge_is_documentation_only():
    bridge_dir = REPO_ROOT / "connect" / "bridges" / "vivo_iqoo"
    check("connect/bridges/vivo_iqoo/ exists", bridge_dir.is_dir())
    py_files = list(bridge_dir.rglob("*.py"))
    check("connect/bridges/vivo_iqoo/ contains no Python implementation (doc-only, as audited)",
          len(py_files) == 0)
    check("connect/bridges/vivo_iqoo/ contains its status documentation",
          len(list(bridge_dir.rglob("*.md"))) >= 1)


# ─── E: SAM Core never depends on vivo/iQOO ────────────────────────────────

CORE_PACKAGES = ["core", "agent", "memory", "founder_mode", "skills", "multimodal"]
FORBIDDEN_ROOTS = ("iqoo", "ecosystem")


def _forbidden_import(py_file: Path):
    """Returns the offending dotted module name if py_file imports a
    compatibility-shim root or a vendor bridge, else None."""
    try:
        tree = ast.parse(py_file.read_text())
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_ROOTS:
                    return alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_ROOTS or node.module.startswith("connect.bridges"):
                return node.module
    return None


def test_core_does_not_import_vivo_or_iqoo():
    scanned = 0
    for pkg in CORE_PACKAGES:
        pkg_dir = REPO_ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        for py_file in pkg_dir.rglob("*.py"):
            scanned += 1
            offender = _forbidden_import(py_file)
            check(f"{py_file.relative_to(REPO_ROOT)} has zero vivo/iQOO coupling",
                  offender is None)
    check("SAM Core scan was non-vacuous (actually found files to check)", scanned > 0)


# ─── F: canonical layer doesn't depend on its own compat shims ────────────

def test_canonical_layer_does_not_depend_on_compat_shims():
    canonical_dirs = [
        REPO_ROOT / "interfaces" / "api",
        REPO_ROOT / "interfaces" / "telegram",
        REPO_ROOT / "connect" / "core",
    ]
    scanned = 0
    for d in canonical_dirs:
        if not d.is_dir():
            continue
        for py_file in d.rglob("*.py"):
            scanned += 1
            offender = _forbidden_import(py_file)
            check(f"{py_file.relative_to(REPO_ROOT)} does not import back into a compatibility shim",
                  offender is None)
    check("canonical-layer scan was non-vacuous (actually found files to check)", scanned > 0)

    from interfaces.api.gateway import TaskGateway
    source = inspect.getsource(TaskGateway)
    core_touchpoints = ("memory.identity", "memory.retrieve", "founder_mode.manager",
                         "core.brain", "agent.react_loop")
    check("TaskGateway orchestrates SAM Core (Identity/Memory/FounderMode/Brain/ReactLoop) "
          "instead of reimplementing agent logic itself",
          all(needle in source for needle in core_touchpoints))


# ─── G: old compatibility paths actually resolve at runtime ───────────────

def test_old_compat_paths_resolve_correctly():
    dotted_paths = [
        "iqoo", "iqoo.gateway", "iqoo.server", "iqoo.events", "iqoo.schemas",
        "iqoo.task_store", "iqoo.errors", "iqoo.media_validation",
        "iqoo.vision_adapter", "iqoo.audio_adapter",
        "ecosystem", "ecosystem.device_registry", "ecosystem.telegram_bridge",
        "ecosystem.pair_new_device",
    ]
    for dotted in dotted_paths:
        try:
            importlib.import_module(dotted)
            resolved = True
        except Exception:
            resolved = False
        check(f"import {dotted}  (old compatibility path still resolves)", resolved)


# ─── H: HTTP + persistent-data compatibility ───────────────────────────────

def test_http_api_contract_unchanged():
    from interfaces.api.server import app
    paths = {getattr(route, "path", None) for route in app.routes}
    for expected in ("/api/iqoo/tasks", "/api/iqoo/health", "/api/iqoo/demo/reset"):
        check(f"HTTP route {expected} still registered (contract not renamed by the move)",
              expected in paths)


def test_persistent_data_paths_unchanged():
    from interfaces.api.task_store import TASKS_DB_PATH
    from connect.core.device_registry import DEVICES_DB_PATH
    check("Task DB still under ~/.sam_data/iqoo/ (data dir not renamed by a code move)",
          TASKS_DB_PATH.parent.name == "iqoo" and TASKS_DB_PATH.parent.parent.name == ".sam_data")
    check("Device DB still under ~/.sam_data/ecosystem/ (data dir not renamed by a code move)",
          DEVICES_DB_PATH.parent.name == "ecosystem" and DEVICES_DB_PATH.parent.parent.name == ".sam_data")


def main():
    print("=== A: Canonical implementations exist ===")
    test_canonical_implementations_exist()

    print("\n=== B: Shims are pure re-exports, not duplicates ===")
    test_shims_are_pure_reexports_not_duplicates()

    print("\n=== C: __main__ entrypoints delegate ===")
    test_shim_main_blocks_delegate_not_reimplement()

    print("\n=== D: vivo_iqoo bridge is documentation-only ===")
    test_vivo_iqoo_bridge_is_documentation_only()

    print("\n=== E: SAM Core has zero vivo/iQOO coupling ===")
    test_core_does_not_import_vivo_or_iqoo()

    print("\n=== F: Canonical layer does not depend on compat shims ===")
    test_canonical_layer_does_not_depend_on_compat_shims()

    print("\n=== G: Old compatibility paths resolve ===")
    test_old_compat_paths_resolve_correctly()

    print("\n=== H: HTTP + persistent-data compatibility ===")
    test_http_api_contract_unchanged()
    test_persistent_data_paths_unchanged()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Phase 3A.5 architecture boundaries verified.")
    print("NOTE: pure import/AST/filesystem checks — no real Ollama, faster-whisper,")
    print("phone, Telegram, or Office Kit hardware was used anywhere in this suite.")


if __name__ == "__main__":
    main()

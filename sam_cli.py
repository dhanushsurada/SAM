#!/usr/bin/env python3
"""
SAM CLI — Control, management, and profile portability
Usage: python sam_cli.py [command]

Commands:
  status              Check SAM + Ollama status
  start [name]        Start voice/api/telegram (all three if no name given)
  stop [name]         Stop voice/api/telegram (all three if no name given)
  restart [name]      Restart voice/api/telegram (all three if no name given)
  doctor              Diagnose SAM's runtime environment
  logs                Tail SAM logs
  memory              Show recent memories
  founder             Show Founder Mode decisions + taste (--all for superseded/rejected too)
  founder-review      Confirm or reject LLM auto-captured entries
  skills              List compiled skills
  decision            Add a decision to Founder Mode
  rejection           Add a rejection to Founder Mode
  export              Export Founder Mode to JSON
  export-profile      Package full SAM profile for moving to new system
  import-profile      Restore SAM profile on a new system
  sync-status         Show what's in your current profile
  reset-memory        Wipe memory only (keeps identity + founder mode)
  reset-all           Full reset (keeps nothing — fresh start)
"""

import sys
import json
import shutil
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

SAM_DATA_DIR = Path.home() / ".sam_data"


# ─── Status ───────────────────────────────────────────────────────────────

def cmd_status():
    import requests
    import subprocess

    print("\n── SAM STATUS ──────────────────────────────")

    # Ollama
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"✅ Ollama running")
        print(f"   Models: {', '.join(models)}")
    except Exception:
        print("❌ Ollama not running → start with: ollama serve")

    # SAM process. Prefer the runtime-tracked state (Phase 3B) when it
    # exists: it checks one specific, recorded PID plus a cmdline sanity
    # check, rather than sweeping every process on the system. Only if SAM
    # was started outside `sam start` (e.g. `python main.py` run directly,
    # which has no state file to check against) do we fall back to the
    # original system-wide pgrep — which CAN false-positive on any
    # unrelated process that happens to have "main.py" anywhere in its
    # command line, so that fallback is now labeled as best-effort rather
    # than presented with the same confidence as a verified match.
    from runtime.lifecycle import read_state, is_pid_alive, pid_matches_expected
    voice_state = read_state("voice")
    voice_pid = voice_state.get("pid") if voice_state else None
    if voice_pid and is_pid_alive(voice_pid) and pid_matches_expected(voice_pid, "main.py"):
        print(f"✅ SAM running (PID: {voice_pid})")
    else:
        result = subprocess.run(["pgrep", "-f", "main.py"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ SAM running (PID: {result.stdout.strip()}, best-effort match — not started via `sam start`)")
        else:
            print("❌ SAM not running → python main.py")

    # Data dir
    if SAM_DATA_DIR.exists():
        print(f"✅ Profile at {SAM_DATA_DIR}")
    else:
        print(f"⚠️  No profile yet — will be created on first run")

    # Runtime-managed processes (Phase 3B). Additive only — everything
    # above this point is unchanged from before Phase 3B.
    print()
    _print_runtime_status()

    print("────────────────────────────────────────────\n")


def _print_runtime_status():
    from runtime import RuntimeStatus, SAMRuntime
    icons = {
        RuntimeStatus.READY: "✅",
        RuntimeStatus.DEGRADED: "⚠️ ",
        RuntimeStatus.STOPPED: "❌",
        RuntimeStatus.FAILED: "❌",
        RuntimeStatus.STARTING: "⏳",
        RuntimeStatus.STOPPING: "⏳",
    }
    rt = SAMRuntime()
    for name in rt.process_names:
        status = rt.status(name)
        icon = icons.get(status, "?")
        if status == RuntimeStatus.FAILED:
            detail = rt.health(name).get("last_failure", "")
            print(f"{icon} {name}: {status.value} — {detail}")
        elif status == RuntimeStatus.STOPPED:
            print(f"{icon} {name}: not running → sam start {name}")
        else:
            print(f"{icon} {name}: {status.value}")


# ─── Runtime (Phase 3B) ─────────────────────────────────────────────────

def _print_lifecycle_result(result):
    if getattr(result, "already_running", False):
        print(f"⚠️  {result.name}: already running (pid {result.pid})")
    elif getattr(result, "already_stopped", False):
        print(f"⭕ {result.name}: already stopped")
    elif result.ok:
        pid_part = f" (pid {result.pid})" if getattr(result, "pid", None) else ""
        print(f"✅ {result.name}: {result.message}" if result.message else f"✅ {result.name}: ok{pid_part}")
    else:
        print(f"❌ {result.name}: {result.message}")


def cmd_start(name=None):
    from runtime import SAMRuntime
    rt = SAMRuntime()
    if name:
        _print_lifecycle_result(rt.start(name))
    else:
        for result in rt.start_all().values():
            _print_lifecycle_result(result)


def cmd_stop(name=None):
    from runtime import SAMRuntime
    rt = SAMRuntime()
    if name:
        _print_lifecycle_result(rt.stop(name))
    else:
        for result in rt.stop_all().values():
            _print_lifecycle_result(result)


def cmd_restart(name=None):
    from runtime import SAMRuntime
    rt = SAMRuntime()
    names = [name] if name else rt.process_names
    for n in names:
        result = rt.restart(n)
        if result.start_result:
            _print_lifecycle_result(result.start_result)
        else:
            print(f"❌ {n}: {result.message}")


def cmd_doctor():
    """Foundation for `sam doctor` (Phase 3B Section 13, Checkpoint 5).
    Each check reports PASS/WARN/FAIL/UNVERIFIED honestly — a module
    importing successfully is not treated as proof the capability behind
    it actually works, per Section 13's explicit instruction."""
    import importlib.util
    import socket

    checks = []

    def record(label, status, detail=""):
        checks.append(status)
        icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "UNVERIFIED": "❓"}[status]
        line = f"{icon} [{status:10s}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)

    print("\n── SAM DOCTOR ───────────────────────────────")

    record("Python version", "PASS" if sys.version_info >= (3, 9) else "WARN", sys.version.split()[0])

    try:
        from config.settings import Settings
        settings = Settings()
        record("Configuration loads", "PASS")
    except Exception as e:
        settings = None
        record("Configuration loads", "FAIL", str(e))

    if SAM_DATA_DIR.exists():
        try:
            probe = SAM_DATA_DIR / ".doctor_write_test"
            probe.write_text("ok")
            probe.unlink()
            record("~/.sam_data writable", "PASS", str(SAM_DATA_DIR))
        except OSError as e:
            record("~/.sam_data writable", "FAIL", str(e))
    else:
        record("~/.sam_data exists", "WARN", "will be created on first run")

    for module_name, label in [
        ("fastapi", "fastapi (api process)"),
        ("uvicorn", "uvicorn (api process)"),
        ("playwright", "playwright (browser automation)"),
        ("faster_whisper", "faster-whisper (speech-to-text)"),
        ("telegram", "python-telegram-bot (telegram bridge)"),
    ]:
        found = importlib.util.find_spec(module_name) is not None
        record(f"{label} importable", "PASS" if found else "WARN",
               "" if found else "not installed — import check only, not a functionality check")

    # Ollama: installed/importable says nothing about running, and running
    # says nothing about whether the configured model is pulled — Section
    # 13 explicitly wants these told apart rather than collapsed together.
    import requests
    ollama_host = getattr(settings, "ollama_host", "http://localhost:11434") if settings else "http://localhost:11434"
    try:
        r = requests.get(f"{ollama_host}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        record("Ollama running", "PASS", f"{len(models)} model(s) pulled")
    except Exception:
        record("Ollama running", "FAIL", f"not reachable at {ollama_host} — start with: ollama serve")

    try:
        from runtime import SAMRuntime, RuntimeStatus
        rt = SAMRuntime()
    except Exception as e:
        rt = None
        record("runtime package loads", "FAIL", str(e))

    if rt is not None:
        api_port = settings.api_port if settings else 8420
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            port_free = s.connect_ex(("127.0.0.1", api_port)) != 0
        if rt.is_running("api"):
            record(f"Port {api_port}", "PASS", "in use by SAM's own api process")
        elif port_free:
            record(f"Port {api_port} free", "PASS")
        else:
            record(f"Port {api_port} free", "WARN", "something other than SAM is already using it")

        for name in rt.process_names:
            status = rt.status(name)
            label = f"runtime: {name}"
            if status == RuntimeStatus.READY:
                record(label, "PASS", "READY")
            elif status == RuntimeStatus.STOPPED:
                record(label, "PASS", "STOPPED (not currently running)")
            elif status in (RuntimeStatus.STARTING, RuntimeStatus.STOPPING):
                record(label, "WARN", status.value)
            else:  # DEGRADED, FAILED
                record(label, "FAIL", status.value)

    if settings is not None:
        token = getattr(settings, "telegram_bot_token", "")
        record("Telegram bot token configured", "PASS" if token else "WARN",
               "" if token else "optional — the telegram process won't start without one")

    record("Vision/STT/TTS model files actually downloaded", "UNVERIFIED",
           "checked only that the libraries import, not that model weights are present")
    record("OS-level permission grants (mic, camera, accessibility)", "UNVERIFIED",
           "not checkable from the CLI")

    passes = checks.count("PASS")
    warns = checks.count("WARN")
    fails = checks.count("FAIL")
    unverified = checks.count("UNVERIFIED")
    print(f"\n{passes} pass, {warns} warn, {fails} fail, {unverified} unverified ({len(checks)} checks)")
    print("────────────────────────────────────────────\n")


# ─── Logs ─────────────────────────────────────────────────────────────────

def cmd_logs(lines: int = 50):
    import subprocess
    log_path = SAM_DATA_DIR / "logs" / "sam.log"
    if not log_path.exists():
        print("No logs yet.")
        return
    subprocess.run(["tail", f"-{lines}", str(log_path)])


# ─── Memory ───────────────────────────────────────────────────────────────

def cmd_memory(limit: int = 10):
    db_path = SAM_DATA_DIR / "memory" / "episodic.db"
    if not db_path.exists():
        print("No memory yet. Run SAM first.")
        return

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT timestamp, user_input, response FROM episodes ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()

    if not rows:
        print("No episodes yet.")
        return

    print(f"\n── RECENT MEMORY ({len(rows)} episodes) ──────────")
    for ts, user, resp in rows:
        print(f"\n[{ts[:19]}]")
        print(f"You: {user[:120]}")
        print(f"SAM: {resp[:120]}")
    print()


# ─── Founder Mode ─────────────────────────────────────────────────────────

def _conf_tag(conf) -> str:
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return ""
    if c >= 0.8:
        return "high"
    elif c >= 0.5:
        return "moderate"
    else:
        return "low/guess"


def cmd_founder(show_all: bool = False):
    db_path = SAM_DATA_DIR / "founder_mode" / "founder_mode.db"
    if not db_path.exists():
        print("No Founder Mode data yet.")
        return

    status_filter = "" if show_all else "WHERE (status IS NULL OR status = 'active')"

    with sqlite3.connect(db_path) as conn:
        decisions = conn.execute(
            f"SELECT timestamp, category, decision, reasoning, confidence, source, status FROM decisions "
            f"{status_filter} ORDER BY id DESC LIMIT 20"
        ).fetchall()
        taste = conn.execute(
            f"SELECT domain, preference, confidence, source, status FROM taste_profile "
            f"{status_filter} ORDER BY updated_at DESC"
        ).fetchall()
        rejections = conn.execute(
            f"SELECT timestamp, category, what_was_rejected, why, confidence, source, status FROM rejections "
            f"{status_filter} ORDER BY id DESC LIMIT 10"
        ).fetchall()

    print(f"\n── DECISIONS ({len(decisions)}) ───────────────────────")
    for ts, cat, dec, reason, conf, source, status in decisions:
        tag = f" [{_conf_tag(conf)} conf, {source or 'manual'}]" if source else ""
        status_note = f" ({status})" if status and status != "active" else ""
        print(f"\n[{ts[:19]}] [{cat}]{tag}{status_note}")
        print(f"  {dec}")
        print(f"  Because: {reason}")

    print(f"\n── TASTE PROFILE ({len(taste)}) ──────────────────────")
    for domain, pref, conf, source, status in taste:
        tag = f" [{_conf_tag(conf)} conf, {source or 'manual'}]" if source else ""
        status_note = f" ({status})" if status and status != "active" else ""
        print(f"  [{domain}] {pref}{tag}{status_note}")

    print(f"\n── REJECTIONS ({len(rejections)}) ────────────────────")
    for ts, cat, what, why, conf, source, status in rejections:
        tag = f" [{_conf_tag(conf)} conf, {source or 'manual'}]" if source else ""
        status_note = f" ({status})" if status and status != "active" else ""
        print(f"\n[{ts[:19]}] [{cat}]{tag}{status_note}")
        print(f"  Rejected: {what[:100]}")
        print(f"  Because: {why[:100]}")
    print(f"\n(Run 'founder --all' to include superseded/rejected entries)")
    print()


def cmd_devices():
    from connect.core.device_registry import DeviceRegistry
    registry = DeviceRegistry()
    registry.cleanup_expired_tokens()
    devices = registry.list_devices()

    if not devices:
        print("No trusted devices. Run 'python -m interfaces.telegram.pair_new_device' to pair one.")
        return

    print(f"\n── TRUSTED DEVICES ({len(devices)}) ──────────────────")
    for d in devices:
        last_active = d["last_active"][:19] if d["last_active"] else "never"
        print(f"  [{d['id']}] {d['device_name']} ({d['channel']}) — "
              f"paired {d['paired_at'][:10]}, last active {last_active}")
    print()


def cmd_revoke_device(device_id: int):
    from connect.core.device_registry import DeviceRegistry
    registry = DeviceRegistry()
    if registry.revoke(device_id):
        print(f"Device {device_id} revoked — it can no longer send SAM commands.")
    else:
        print(f"No trusted device with id {device_id} found.")



def cmd_founder_review():
    """Walk through LLM-auto-captured entries below full confidence and
    let the user confirm (bump to 1.0) or reject (exclude from context)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from founder_mode.manager import FounderModeManager
    mgr = FounderModeManager()

    captures = mgr.list_llm_captures()
    if not captures:
        print("Nothing to review — no unconfirmed LLM auto-captures.")
        return

    print(f"\n── FOUNDER MODE REVIEW ({len(captures)} to review) ──")
    print("For each: [y] confirm  [n] reject  [s] skip  [q] quit\n")

    for c in captures:
        conf_pct = f"{float(c['confidence']) * 100:.0f}%" if c["confidence"] is not None else "?"
        print(f"[{c['table']}] ({conf_pct} confidence)")
        print(f"  {c['label'][:150]}")
        choice = input("  y/n/s/q: ").strip().lower()

        if choice == "q":
            break
        elif choice == "y":
            mgr.confirm_capture(c["table"], c["id"])
            print("  ✅ Confirmed.\n")
        elif choice == "n":
            mgr.reject_capture(c["table"], c["id"])
            print("  ❌ Rejected — excluded from Founder Mode context.\n")
        else:
            print("  ⏭️  Skipped.\n")


# ─── Skills ───────────────────────────────────────────────────────────────

def cmd_skills():
    """List compiled skills.

    NOTE: found while testing Phase 3B's CLI integration (Checkpoint 5) —
    this function was referenced by the 'skills' subparser and the
    commands dispatch dict but was never actually defined anywhere in the
    codebase (confirmed via `git show HEAD:sam_cli.py` — absent since the
    initial "import existing SAM main branch state" commit). Because the
    commands dict is built unconditionally at the top of main(), this
    meant EVERY sam_cli.py command crashed with NameError before dispatch
    ever ran, including the new Phase 3B commands. Pre-existing and
    unrelated to Phase 3A.5/3B — flagged here and in the Checkpoint 5
    report rather than silently absorbed. This is a minimal fix (list the
    same skills/compiled directory cmd_sync_status already reports a count
    for), not a redesign."""
    skills_dir = SAM_DATA_DIR / "skills" / "compiled"
    if not skills_dir.exists():
        print("No compiled skills yet.")
        return
    skill_files = sorted(skills_dir.glob("*.json"))
    if not skill_files:
        print("No compiled skills yet.")
        return
    print(f"\n── COMPILED SKILLS ({len(skill_files)}) ─────────────────")
    for f in skill_files:
        print(f"  {f.stem}")
    print()


def cmd_license():
    from licensing.license_manager import LicenseManager, LicenseStatus
    mgr = LicenseManager()
    status, message, lic = mgr.check()

    print(f"\n── LICENSE STATUS ──────────────────────")
    print(f"  Status: {status}")
    print(f"  {message}")
    if lic:
        print(f"  Edition: {lic.product_edition}")
        print(f"  Issued: {lic.issue_date[:10]}")
        print(f"  {'Lifetime (never expires)' if lic.is_lifetime else f'Expires: {lic.expiry_date[:10]}'}")
    if status == LicenseStatus.NO_LICENSE:
        print(f"\n  Running unlicensed — this is fine for now (non-blocking, per current settings).")
        print(f"  Install one with: python sam_cli.py activate <license_file.json>")
    print()


def cmd_activate(license_file: str):
    from licensing.license_manager import LicenseManager
    mgr = LicenseManager()
    ok, message = mgr.install_license(license_file)
    print(f"\n{'✅' if ok else '❌'} {message}\n")



    db_path = SAM_DATA_DIR / "skills" / "skills.db"
    if not db_path.exists():
        print("No compiled skills yet.")
        return

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT skill_name, task_pattern, success_count FROM skill_candidates WHERE compiled=1"
        ).fetchall()

    if not rows:
        print("No compiled skills yet. Skills compile after 3 successful completions.")
        return

    print(f"\n── COMPILED SKILLS ({len(rows)}) ─────────────────────")
    for name, pattern, uses in rows:
        print(f"\n  {name}")
        print(f"  Pattern: {pattern}")
        print(f"  Uses: {uses}")
    print()


# ─── Founder Mode Actions ─────────────────────────────────────────────────

def cmd_decision(decision: str, reasoning: str, category: str = "general"):
    sys.path.insert(0, str(Path(__file__).parent))
    from founder_mode.manager import FounderModeManager
    FounderModeManager().capture_decision(decision, reasoning, category)
    print(f"✅ Decision saved: {decision[:80]}")


def cmd_rejection(what: str, why: str, category: str = "general"):
    sys.path.insert(0, str(Path(__file__).parent))
    from founder_mode.manager import FounderModeManager
    FounderModeManager().capture_rejection(what, why, category)
    print(f"✅ Rejection saved: {what[:80]}")


def cmd_export():
    sys.path.insert(0, str(Path(__file__).parent))
    from founder_mode.manager import FounderModeManager
    path = FounderModeManager().export()
    print(f"✅ Exported to: {path}")


# ─── Profile Portability ──────────────────────────────────────────────────

def cmd_export_profile():
    """Package full ~/.sam_data into a portable zip."""
    if not SAM_DATA_DIR.exists():
        print("No profile found. Run SAM first to create one.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_name = f"sam_profile_{timestamp}"
    export_path = Path.home() / f"{export_name}.zip"

    print(f"Packaging profile from {SAM_DATA_DIR}...")
    shutil.make_archive(str(Path.home() / export_name), "zip", SAM_DATA_DIR)

    size_mb = export_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Profile exported: {export_path}")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"\nTo move to a new system:")
    print(f"  1. Copy {export_path.name} to the new machine")
    print(f"  2. Run: python sam_cli.py import-profile {export_path.name}")


def cmd_import_profile(zip_path: str):
    """Restore a SAM profile from a zip on a new system."""
    zip_file = Path(zip_path)
    if not zip_file.exists():
        print(f"File not found: {zip_path}")
        return

    if SAM_DATA_DIR.exists():
        # Backup existing before overwriting
        backup = Path(str(SAM_DATA_DIR) + f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.move(str(SAM_DATA_DIR), str(backup))
        print(f"Existing profile backed up to: {backup}")

    SAM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(zip_path, str(SAM_DATA_DIR))

    print(f"\n✅ Profile imported from {zip_path}")
    print(f"   SAM now knows you. Run: python main.py")


def cmd_sync_status():
    """Show what's in the current profile."""
    if not SAM_DATA_DIR.exists():
        print("No profile yet.")
        return

    print(f"\n── PROFILE STATUS ──────────────────────────")
    print(f"Location: {SAM_DATA_DIR}")

    # Identity
    identity_path = SAM_DATA_DIR / "identity.json"
    if identity_path.exists():
        with open(identity_path) as f:
            identity = json.load(f)
        print(f"\n✅ Identity: {identity.get('name', 'Unknown')}")
        print(f"   Assistant name: {identity.get('assistant_name', 'SAM')}")
    else:
        print("\n❌ No identity file")

    # Memory
    db_path = SAM_DATA_DIR / "memory" / "episodic.db"
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        print(f"\n✅ Episodic memory: {count} conversations")
    else:
        print("\n❌ No episodic memory")

    # ChromaDB
    chroma_path = SAM_DATA_DIR / "memory" / "chroma"
    if chroma_path.exists():
        print(f"✅ Semantic memory: present")
    else:
        print("❌ No semantic memory")

    # Founder Mode
    fm_db = SAM_DATA_DIR / "founder_mode" / "founder_mode.db"
    if fm_db.exists():
        with sqlite3.connect(fm_db) as conn:
            d_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            r_count = conn.execute("SELECT COUNT(*) FROM rejections").fetchone()[0]
            t_count = conn.execute("SELECT COUNT(*) FROM taste_profile").fetchone()[0]
        print(f"\n✅ Founder Mode:")
        print(f"   {d_count} decisions | {r_count} rejections | {t_count} taste entries")
    else:
        print("\n❌ No Founder Mode data")

    # Skills
    skills_dir = SAM_DATA_DIR / "skills" / "compiled"
    if skills_dir.exists():
        skill_count = len(list(skills_dir.glob("*.json")))
        print(f"\n✅ Compiled skills: {skill_count}")
    else:
        print("\n❌ No compiled skills")

    # Size
    total_size = sum(f.stat().st_size for f in SAM_DATA_DIR.rglob("*") if f.is_file())
    print(f"\n   Total profile size: {total_size / (1024*1024):.1f} MB")
    print("────────────────────────────────────────────\n")


# ─── Reset ────────────────────────────────────────────────────────────────

def cmd_reset_memory():
    """Wipe memory only. Keeps identity and Founder Mode."""
    confirm = input("Wipe all memory? Identity and Founder Mode kept. (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        return

    db_path = SAM_DATA_DIR / "memory" / "episodic.db"
    chroma_path = SAM_DATA_DIR / "memory" / "chroma"

    if db_path.exists():
        db_path.unlink()
        print("✅ Episodic memory wiped")

    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        print("✅ Semantic memory wiped")

    print("Memory reset. Founder Mode and identity intact.")


def cmd_reset_all():
    """Full reset — wipes everything in ~/.sam_data."""
    confirm = input("⚠️  FULL RESET — wipes ALL data including Founder Mode. Type 'RESET' to confirm: ")
    if confirm != "RESET":
        print("Cancelled.")
        return

    backup = Path(str(SAM_DATA_DIR) + f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.move(str(SAM_DATA_DIR), str(backup))
    print(f"✅ Full reset done. Backup at: {backup}")
    print("SAM will start fresh on next run.")


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAM CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status")

    for cmd_name in ("start", "stop", "restart"):
        p = subparsers.add_parser(cmd_name)
        p.add_argument("name", nargs="?", choices=["voice", "api", "telegram"], default=None,
                       help="Which process (default: all three)")
    subparsers.add_parser("doctor")

    founder_p = subparsers.add_parser("founder")
    founder_p.add_argument("--all", action="store_true", dest="show_all",
                            help="Include superseded/rejected entries")
    subparsers.add_parser("founder-review")
    subparsers.add_parser("devices")
    revoke_p = subparsers.add_parser("revoke-device")
    revoke_p.add_argument("device_id", type=int)
    subparsers.add_parser("skills")
    subparsers.add_parser("export")
    subparsers.add_parser("export-profile")
    subparsers.add_parser("sync-status")
    subparsers.add_parser("reset-memory")
    subparsers.add_parser("reset-all")

    subparsers.add_parser("license")
    activate_p = subparsers.add_parser("activate")
    activate_p.add_argument("license_file")

    logs_p = subparsers.add_parser("logs")
    logs_p.add_argument("--lines", type=int, default=50)

    mem_p = subparsers.add_parser("memory")
    mem_p.add_argument("--limit", type=int, default=10)

    dec_p = subparsers.add_parser("decision")
    dec_p.add_argument("decision")
    dec_p.add_argument("reasoning")
    dec_p.add_argument("--category", default="general")

    rej_p = subparsers.add_parser("rejection")
    rej_p.add_argument("what")
    rej_p.add_argument("why")
    rej_p.add_argument("--category", default="general")

    imp_p = subparsers.add_parser("import-profile")
    imp_p.add_argument("zip_path")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "doctor": cmd_doctor,
        "skills": cmd_skills,
        "export": cmd_export,
        "export-profile": cmd_export_profile,
        "sync-status": cmd_sync_status,
        "reset-memory": cmd_reset_memory,
        "reset-all": cmd_reset_all,
        "founder-review": cmd_founder_review,
        "devices": cmd_devices,
        "license": cmd_license,
    }

    if args.command in commands:
        commands[args.command]()
    elif args.command in ("start", "stop", "restart"):
        {"start": cmd_start, "stop": cmd_stop, "restart": cmd_restart}[args.command](args.name)
    elif args.command == "activate":
        cmd_activate(args.license_file)
    elif args.command == "revoke-device":
        cmd_revoke_device(args.device_id)
    elif args.command == "founder":
        cmd_founder(show_all=getattr(args, "show_all", False))
    elif args.command == "logs":
        cmd_logs(args.lines)
    elif args.command == "memory":
        cmd_memory(args.limit)
    elif args.command == "decision":
        cmd_decision(args.decision, args.reasoning, args.category)
    elif args.command == "rejection":
        cmd_rejection(args.what, args.why, args.category)
    elif args.command == "import-profile":
        cmd_import_profile(args.zip_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

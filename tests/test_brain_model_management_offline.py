"""
OFFLINE test suite — local Brain/model management (core/model_manager.py),
its TaskGateway integration, its HTTP contract and the desktop client
contract.

Covers, with a fake Ollama (no real Ollama, no network, nothing from the
user's own installation):

  A. discovery parsing (names, sizes, details, capabilities, context length)
  B. empty model list
  C. Ollama unavailable (unreachable, HTTP error, unreadable body)
  D. active model retrieval: selected / fallback / neither
  E. status stays in step with Brain._ensure_model() (drift guard)
  F. compatibility is conservative and never "compatible"
  G. valid selection: applied, explicit, persisted across a restart
  H. name normalisation ("qwen3" -> the installed "qwen3:latest")
  I. invalid selection fails cleanly and changes nothing (not installed,
     empty, embedding-only, metadata unreadable, Ollama down, save failure)
  J. the RUNTIME Brain actually receives the selected model (real Brain,
     real planner), and pinned overrides are reported, not silently followed
  K. state consistency across settings / manager / gateway
  L. TaskGateway: refused while a task is running or queued, atomic with the
     worker, no Ollama traffic when refused
  M. HTTP contract: routes exist; every refusal has its own status
  N. schema <-> manager <-> TypeScript contract, and no backend field the
     desktop UI never reads
  O. desktop product structure: the demo Models page is gone, Brain / Tasks /
     Hands are built pages, browser is a Hands entry rather than a section

These checks are import / AST / text based where the real thing would need
FastAPI or a JS toolchain, so they run in a bare Python environment; the
FastAPI routes themselves are exercised by the desktop build and the manual
Mac checklist in docs/BRAIN_MODEL_SELECTION_AND_DESKTOP.md.

Usage (script mode isolates HOME automatically):
    python3 tests/test_brain_model_management_offline.py
"""

import ast
import json
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from unittest.mock import MagicMock, patch

if __name__ == "__main__":
    # SAM_DATA_DIR and the task ledger path are computed from $HOME at import
    # time; pin them to a scratch directory before anything imports them so a
    # bare `python3 tests/...` can never touch the real ~/.sam_data.
    os.environ["HOME"] = tempfile.mkdtemp(prefix="sam_brain_model_test_")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import config.settings as settings_module  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.brain import Brain  # noqa: E402
from core.session import Session  # noqa: E402
from core import model_manager as mm_module  # noqa: E402
from core.model_manager import (  # noqa: E402
    COMPAT_INCOMPATIBLE, COMPAT_UNKNOWN, LocalModel, ModelIncompatibleError,
    ModelManager, ModelManagerError, ModelMetadataError, ModelNotInstalledError,
    ModelPersistError, OllamaUnavailableError, canonical_name, classify,
    resolve_installed_name,
)

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")
    if not condition and "pytest" in sys.modules:
        # Script mode records every failure and keeps going; under pytest a
        # failed check must fail its test, not just print.
        raise AssertionError(label)


# ─── Fake Ollama ───────────────────────────────────────────────────────────

def _resp(status=200, payload=None, bad_json=False):
    r = MagicMock()
    r.status_code = status
    r.text = json.dumps(payload) if payload is not None else ""
    if bad_json:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = payload if payload is not None else {}
    return r


class FakeOllama:
    """Routes requests.get/post by URL. `models` maps a name to
    {"size", "digest", "details", "show"}, where "show" is the /api/show body,
    an int (HTTP status to fail with) or an Exception to raise."""

    def __init__(self, models=None, reachable=True, tags_status=200, tags_bad_json=False):
        self.models = models if models is not None else {}
        self.reachable = reachable
        self.tags_status = tags_status
        self.tags_bad_json = tags_bad_json
        self.calls = []          # (method, path, json)
        self.chat_reply = {"text": "ok", "action": None, "action_payload": None}

    def _path(self, url):
        return url.split("11434", 1)[-1] if "11434" in url else url

    def get(self, url, timeout=None, **kw):
        self.calls.append(("GET", self._path(url), None))
        if not self.reachable:
            raise ConnectionError("connection refused")
        if self.tags_bad_json:
            return _resp(self.tags_status, bad_json=True)
        entries = []
        for name, m in self.models.items():
            entries.append({"name": name, "model": name, "size": m.get("size"),
                            "digest": m.get("digest", name), "details": m.get("details", {})})
        return _resp(self.tags_status, {"models": entries})

    def post(self, url, json=None, timeout=None, **kw):  # noqa: A002 - mirrors requests
        path = self._path(url)
        self.calls.append(("POST", path, json))
        if not self.reachable:
            raise ConnectionError("connection refused")
        if path.endswith("/api/show"):
            show = self.models[json["model"]].get("show", {})
            if isinstance(show, Exception):
                raise show
            if isinstance(show, int):
                return _resp(show, {"error": "boom"})
            return _resp(200, show)
        if path.endswith("/api/chat"):
            return _resp(200, {"message": {"content": globals()["json"].dumps(self.chat_reply)}})
        if path.endswith("/api/generate"):
            return _resp(200, {"response": globals()["json"].dumps({"steps": [{"description": "do it"}]})})
        raise AssertionError(f"unexpected POST {path}")

    def paths(self, method=None):
        return [p for m, p, _ in self.calls if method in (None, m)]

    def chat_models(self):
        return [j["model"] for m, p, j in self.calls if p.endswith("/api/chat")]

    @contextmanager
    def active(self):
        with patch("requests.get", self.get), patch("requests.post", self.post):
            yield self


def _model(size=1_000_000_000, params="8B", quant="Q4_K_M", family="qwen3",
           caps=("completion", "tools"), ctx=32768, arch=None, show=None):
    arch = arch or family
    return {
        "size": size, "digest": f"sha-{family}-{params}",
        "details": {"family": family, "parameter_size": params, "quantization_level": quant},
        "show": show if show is not None else {
            "capabilities": list(caps) if caps is not None else None,
            "model_info": {"general.architecture": arch, f"{arch}.context_length": ctx},
        },
    }


def standard_models():
    return {
        "qwen2.5:14b": _model(8_988_124_069, "14.8B", family="qwen2", ctx=32768),
        "qwen2.5:7b": _model(4_683_087_332, "7.6B", family="qwen2", ctx=32768),
        "qwen3:8b": _model(5_200_000_000, "8.2B", family="qwen3",
                           caps=("completion", "tools", "thinking"), ctx=40960),
        "nomic-embed-text:latest": _model(274_302_450, "137M", "F16", family="nomic-bert",
                                          caps=("embedding",), ctx=2048),
        "moondream:latest": _model(1_700_000_000, "1.4B", family="phi2",
                                   caps=("completion", "vision"), ctx=2048),
    }


@contextmanager
def scratch_settings(primary="qwen2.5:14b", fallback="qwen2.5:7b", explicit=False):
    """A real Settings() whose persistence goes to a scratch directory (the
    same technique tests/test_model_selection_offline.py uses)."""
    data_dir = Path(tempfile.mkdtemp())
    with patch.object(settings_module, "SAM_DATA_DIR", data_dir):
        s = Settings()
        s.primary_model, s.fallback_model, s.model_explicitly_set = primary, fallback, explicit
        s.planner_model = s.reflection_model = s.founder_mode_classifier_model = None
        s.embedding_model, s.vision_model = "nomic-embed-text", "moondream"
        s.model_context_length = 8192
        yield s, data_dir


# ─── A/B/C/D: discovery, empty, unavailable, active ───────────────────────

def test_discovery_parsing():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        status = ModelManager(s).status()
    by_name = {m["name"]: m for m in status["models"]}
    check("discovery lists every installed model, dynamically (5 fake models -> 5 rows)",
          set(by_name) == set(standard_models()))
    q = by_name["qwen2.5:14b"]
    check("size, parameter size, quantisation and family come from /api/tags details",
          q["size_bytes"] == 8_988_124_069 and q["parameter_size"] == "14.8B"
          and q["quantization"] == "Q4_K_M" and q["family"] == "qwen2")
    check("capabilities and context length come from /api/show",
          q["capabilities"] == ["completion", "tools"] and q["context_length"] == 32768)
    check("provider is ollama and the endpoint is the configured one",
          status["provider"] == "ollama" and status["ollama_host"] == "http://localhost:11434")
    check("no model name is hardcoded: an unfamiliar name is listed like any other",
          "qwen3:8b" in by_name and by_name["qwen3:8b"]["is_selected"] is False)


def test_discovery_metadata_shapes_are_tolerated():
    models = {
        "a:1": {"size": None, "details": {}, "show": {}},                      # nothing reported
        "b:1": {"size": True, "details": {"family": ""}, "show": {"capabilities": "oops",
                "model_info": {"general.architecture": "x", "x.context_length": True}}},
    }
    fake = FakeOllama(models)
    with scratch_settings() as (s, _), fake.active():
        status = ModelManager(s).status()
    a, b = status["models"]
    check("a model with no metadata at all still lists (fields None, compatibility unknown)",
          a["size_bytes"] is None and a["capabilities"] is None and a["context_length"] is None
          and a["compatibility"] == COMPAT_UNKNOWN)
    check("malformed metadata (bool size, string capabilities, bool context) is ignored, not trusted",
          b["size_bytes"] is None and b["capabilities"] is None and b["context_length"] is None
          and b["family"] is None)


def test_empty_model_list():
    fake = FakeOllama({})
    with scratch_settings() as (s, _), fake.active():
        status = ModelManager(s).status()
    check("empty list is a normal, non-error state: status unavailable, models []",
          status["status"] == "unavailable" and status["models"] == [] and status["active_model"] is None)
    check("empty list explains what to do", "ollama pull" in (status["detail"] or ""))


def test_ollama_unavailable():
    for label, fake in (
        ("unreachable", FakeOllama(reachable=False)),
        ("HTTP 500", FakeOllama(standard_models(), tags_status=500)),
        ("unreadable body", FakeOllama(standard_models(), tags_bad_json=True)),
    ):
        with scratch_settings() as (s, _), fake.active():
            manager = ModelManager(s)
            status = manager.status()
            try:
                manager.list_models()
                raised = False
            except OllamaUnavailableError:
                raised = True
        check(f"Ollama {label}: status() reports unavailable instead of raising",
              status["status"] == "unavailable" and status["models"] == []
              and status["active_model"] is None and status["detail"])
        check(f"Ollama {label}: list_models() raises the specific OllamaUnavailableError", raised)
        check(f"Ollama {label}: the configured selection is still reported",
              status["selected_model"] == "qwen2.5:14b" and status["fallback_model"] == "qwen2.5:7b")


def test_active_model_resolution():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        st = ModelManager(s).status()
    check("selected installed -> active is the selected model, source 'selected', status ready",
          st["active_model"] == "qwen2.5:14b" and st["active_source"] == "selected"
          and st["status"] == "ready" and st["detail"] is None)

    models = standard_models()
    del models["qwen2.5:14b"]
    fake = FakeOllama(models)
    with scratch_settings() as (s, _), fake.active():
        st = ModelManager(s).status()
    check("selected missing, fallback installed -> active is the fallback, source 'fallback'",
          st["active_model"] == "qwen2.5:7b" and st["active_source"] == "fallback")
    check("...and the detail says the selected model isn't installed",
          st["status"] == "ready" and "isn't installed" in st["detail"])

    del models["qwen2.5:7b"]
    fake = FakeOllama(models)
    with scratch_settings() as (s, _), fake.active():
        st = ModelManager(s).status()
    check("neither installed -> unavailable, no active model, but the installed models are still "
          "returned so the user can choose one",
          st["status"] == "unavailable" and st["active_model"] is None and st["active_source"] is None
          and len(st["models"]) == 3 and "Choose an installed model" in st["detail"])
    check("exactly the selected/fallback flags reflect config even when neither is installed",
          not any(m["is_selected"] or m["is_fallback"] or m["is_active"] for m in st["models"]))


def test_status_stays_in_step_with_brain_ensure_model():
    """resolve_active() re-states Brain._ensure_model()'s rule so status can
    be built from one /api/tags call. Pin the two together."""
    scenarios = {
        "selected installed": ["qwen2.5:14b", "qwen2.5:7b"],
        "only fallback installed": ["qwen2.5:7b", "qwen3:8b"],
        "neither installed": ["qwen3:8b"],
        "nothing installed": [],
    }
    for label, installed in scenarios.items():
        fake = FakeOllama({n: _model() for n in installed})
        with scratch_settings() as (s, _), fake.active():
            expected = ModelManager(s).resolve_active(installed)
            try:
                actual = Brain(s)._ensure_model()
            except RuntimeError:
                actual = None
        check(f"resolve_active == Brain._ensure_model() when {label} ({expected})", expected == actual)


# ─── F: compatibility ─────────────────────────────────────────────────────

def test_compatibility_is_conservative():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        by_name = {m["name"]: m for m in ModelManager(s).status()["models"]}

    emb = by_name["nomic-embed-text:latest"]
    check("SAM's own configured embedding model is incompatible (read from Settings, not a name list)",
          emb["compatibility"] == COMPAT_INCOMPATIBLE and "embedding model" in emb["compatibility_reason"])
    check("a chat model is 'unknown', never 'compatible' — SAM can't verify its JSON action format",
          by_name["qwen2.5:14b"]["compatibility"] == COMPAT_UNKNOWN
          and "hasn't verified" in by_name["qwen2.5:14b"]["compatibility_reason"])
    check("the compatibility vocabulary has no 'compatible' member at all",
          {m["compatibility"] for m in by_name.values()} <= {COMPAT_UNKNOWN, COMPAT_INCOMPATIBLE}
          and not hasattr(mm_module, "COMPAT_COMPATIBLE"))
    check("a thinking-capable model carries a specific warning",
          any("Reasoning model" in n for n in by_name["qwen3:8b"]["notes"]))
    check("SAM's configured vision model is flagged, not silently offered as a Brain",
          any("vision model" in n for n in by_name["moondream:latest"]["notes"])
          and by_name["moondream:latest"]["compatibility"] == COMPAT_UNKNOWN)
    check("context below SAM's configured num_ctx is flagged",
          any("context limit (2048)" in n for n in by_name["moondream:latest"]["notes"]))

    with scratch_settings() as (s, _):
        c, reason, _ = classify(s, "some-unconfigured-embedder:latest", ["embedding"], 512)
        check("an embedding-only model is incompatible by its reported capabilities alone",
              c == COMPAT_INCOMPATIBLE and "no text-generation" in reason)
        c, reason, notes = classify(s, "mystery:1b", None, None)
        check("capabilities not reported (older Ollama) -> unknown, and it says why",
              c == COMPAT_UNKNOWN and "didn't report" in reason and notes == [])


def test_listing_degrades_per_model_but_selection_does_not():
    models = standard_models()
    models["qwen3:8b"]["show"] = 500
    fake = FakeOllama(models)
    with scratch_settings() as (s, _), fake.active():
        manager = ModelManager(s)
        by_name = {m["name"]: m for m in manager.status()["models"]}
        try:
            manager.validate_selection("qwen3:8b")
            refused = False
        except ModelMetadataError:
            refused = True
    check("a model whose /api/show fails is still listed, capabilities None, compatibility unknown",
          "qwen3:8b" in by_name and by_name["qwen3:8b"]["capabilities"] is None
          and by_name["qwen3:8b"]["compatibility"] == COMPAT_UNKNOWN)
    check("...but selecting it is refused with ModelMetadataError (never selects on a guess)", refused)


def test_metadata_is_cached_by_digest():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        manager = ModelManager(s)
        manager.status()
        first = fake.paths("POST").count("/api/show")
        manager.status()
        second = fake.paths("POST").count("/api/show")
    check("a second status() re-uses cached /api/show results (no extra metadata calls)",
          first == 5 and second == first)


# ─── G/H: valid selection ─────────────────────────────────────────────────

def test_valid_selection_applies_and_persists():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, data_dir), fake.active():
        manager = ModelManager(s)
        status = manager.select("qwen3:8b")
        check("select() sets settings.primary_model", s.primary_model == "qwen3:8b")
        check("select() marks the choice explicit (RAM auto-selection can no longer overwrite it)",
              s.model_explicitly_set is True)
        check("the returned status reflects the change immediately",
              status["selected_model"] == "qwen3:8b" and status["active_model"] == "qwen3:8b"
              and status["user_selected"] is True and status["status"] == "ready")
        check("the previous primary is not touched: fallback unchanged", s.fallback_model == "qwen2.5:7b")
        check("choice written to settings.yaml", (data_dir / "settings.yaml").exists())
        s2 = Settings()  # brand-new instance, simulating a restart
    check("the selection survives a simulated restart (model + explicit flag)",
          s2.primary_model == "qwen3:8b" and s2.model_explicitly_set is True)


def test_selecting_the_current_model_is_a_noop_write():
    fake = FakeOllama(standard_models())
    with scratch_settings(explicit=True) as (s, data_dir), fake.active():
        with patch.object(Settings, "_persist_model_choice") as persist:
            ModelManager(s).select("qwen2.5:14b")
    check("re-selecting the already-selected, already-explicit model writes nothing", not persist.called)


def test_selection_normalises_to_the_installed_spelling():
    models = {"qwen3:latest": _model(), "qwen2.5:7b": _model()}
    fake = FakeOllama(models)
    with scratch_settings() as (s, _), fake.active():
        ModelManager(s).select("qwen3")
        active = ModelManager(s).status()["active_model"]
    check("selecting 'qwen3' stores the installed spelling 'qwen3:latest'", s.primary_model == "qwen3:latest")
    check("...so Brain's exact-name matching resolves it as active (no silent fallback)",
          active == "qwen3:latest")
    check("canonical_name / resolve_installed_name agree on the :latest rule",
          canonical_name("qwen3") == "qwen3:latest" and canonical_name("hf.co/x/y:Q4") == "hf.co/x/y:Q4"
          and resolve_installed_name("qwen3", ["qwen3:latest"]) == "qwen3:latest"
          and resolve_installed_name("qwen3:8b", ["qwen3:latest"]) is None
          and resolve_installed_name("", ["a"]) is None)


# ─── I: invalid selection ─────────────────────────────────────────────────

def _assert_unchanged(s, data_dir, label):
    check(f"{label}: primary_model unchanged", s.primary_model == "qwen2.5:14b")
    check(f"{label}: not marked explicit", s.model_explicitly_set is False)
    check(f"{label}: nothing written to disk", not (data_dir / "settings.yaml").exists())


def _select_expecting(manager, name, exc):
    try:
        manager.select(name)
    except exc as e:
        return e
    except Exception as e:  # wrong type
        return e
    return None


def test_invalid_selections_fail_cleanly_and_change_nothing():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, data_dir), fake.active():
        manager = ModelManager(s)

        e = _select_expecting(manager, "no-such-model:7b", ModelNotInstalledError)
        check("not installed -> ModelNotInstalledError with the pull command",
              isinstance(e, ModelNotInstalledError) and "ollama pull no-such-model:7b" in str(e))
        _assert_unchanged(s, data_dir, "not installed")

        e = _select_expecting(manager, "   ", ModelNotInstalledError)
        check("blank name -> ModelNotInstalledError", isinstance(e, ModelNotInstalledError))

        e = _select_expecting(manager, "nomic-embed-text", ModelIncompatibleError)
        check("SAM's embedding model can't be selected: ModelIncompatibleError",
              isinstance(e, ModelIncompatibleError) and "can't be used as SAM's Brain" in str(e))
        _assert_unchanged(s, data_dir, "embedding model")

    models = standard_models()
    models["other-embedder:1"] = _model(caps=("embedding",))
    fake = FakeOllama(models)
    with scratch_settings() as (s, data_dir), fake.active():
        e = _select_expecting(ModelManager(s), "other-embedder:1", ModelIncompatibleError)
        check("an unconfigured embedding-only model is refused on its reported capabilities",
              isinstance(e, ModelIncompatibleError))
        _assert_unchanged(s, data_dir, "embedding-only by capability")

    models = standard_models()
    models["qwen3:8b"]["show"] = ConnectionError("dropped")
    fake = FakeOllama(models)
    with scratch_settings() as (s, data_dir), fake.active():
        e = _select_expecting(ModelManager(s), "qwen3:8b", ModelMetadataError)
        check("metadata request failing -> ModelMetadataError", isinstance(e, ModelMetadataError))
        _assert_unchanged(s, data_dir, "metadata failure")

    fake = FakeOllama(reachable=False)
    with scratch_settings() as (s, data_dir), fake.active():
        e = _select_expecting(ModelManager(s), "qwen3:8b", OllamaUnavailableError)
        check("Ollama unreachable -> OllamaUnavailableError", isinstance(e, OllamaUnavailableError))
        _assert_unchanged(s, data_dir, "Ollama unavailable")

    check("every expected failure is a ModelManagerError (one base to catch, real bugs still surface)",
          all(issubclass(c, ModelManagerError) for c in (
              OllamaUnavailableError, ModelNotInstalledError, ModelMetadataError,
              ModelIncompatibleError, ModelPersistError)))


def test_save_failure_rolls_back_the_runtime_setting():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, data_dir), fake.active():
        blocker = Path(tempfile.mkdtemp()) / "not-a-directory"
        blocker.write_text("a regular file where the settings directory should be")
        with patch.object(settings_module, "SAM_DATA_DIR", blocker):
            e = _select_expecting(ModelManager(s), "qwen3:8b", ModelPersistError)
    check("a settings write failure surfaces as ModelPersistError", isinstance(e, ModelPersistError))
    check("...and the runtime setting is rolled back, so runtime and disk can't disagree",
          s.primary_model == "qwen2.5:14b" and s.model_explicitly_set is False)


# ─── G3: the CLI "model" command shares the same core ────────────────────

def test_cli_model_command_only_claims_model_names():
    import main
    import memory.identity as identity_module
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, data_dir), fake.active(), \
         patch.object(identity_module, "IDENTITY_PATH", Path(tempfile.mkdtemp()) / "identity.json"):
        sam = main.SAM(start_in_text_mode=True)
        sam.settings.primary_model, sam.settings.model_explicitly_set = "qwen2.5:14b", False
        check("a sentence that merely starts with 'model' is left for the Brain, not read as a model name",
              sam._handle_command("model the data flow for a login page") is False)
        check("...and nothing was changed by it", sam.settings.primary_model == "qwen2.5:14b"
              and not (data_dir / "settings.yaml").exists())
        check("'model qwen3:8b' is handled as the command", sam._handle_command("model qwen3:8b") is True)
        sam.settings.incognito = True       # the voice loop's runtime-only "incognito" command
        sam._handle_command("model qwen2.5:7b")
        saved = _read_yaml(data_dir / "settings.yaml")
        check("...through the shared path: applied, explicit and persisted",
              sam.settings.primary_model == "qwen2.5:7b" and saved["primary_model"] == "qwen2.5:7b"
              and saved["model_explicitly_set"] is True)
        check("...and the runtime-only incognito flag did not leak into the file",
              saved.get("incognito", False) is False)
        check("SAM's embedding model is refused by the CLI as well",
              sam._handle_command("model nomic-embed-text") is True and sam.settings.primary_model == "qwen2.5:7b")


# ─── G2: persistence is targeted, atomic and leaks no runtime state ───────

def _read_yaml(path):
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def test_persistence_writes_only_the_model_keys():
    import yaml
    with scratch_settings() as (s, data_dir):
        user_file = data_dir / "settings.yaml"
        user_file.write_text(yaml.dump({"user_name": "Tester", "temperature": 0.9,
                                        "primary_model": "qwen2.5:14b",
                                        "sam_settings_schema_version": 1}))
        s = Settings()                       # loads the user's file
        s.incognito = True                   # the voice loop's runtime-only "incognito" command
        s.apply_model_choice(primary="qwen3:8b", fallback="qwen2.5:7b")
        saved = _read_yaml(user_file)
        check("the chosen models and the explicit flag are written",
              saved["primary_model"] == "qwen3:8b" and saved["fallback_model"] == "qwen2.5:7b"
              and saved["model_explicitly_set"] is True)
        check("the rest of the user's file is preserved exactly",
              saved["user_name"] == "Tester" and saved["temperature"] == 0.9)
        check("runtime-only state is NOT persisted (incognito toggled in memory never reaches disk)",
              "incognito" not in saved)
        check("nothing else is frozen into the file (no full-settings dump)",
              set(saved) == {"user_name", "temperature", "primary_model", "fallback_model",
                             "model_explicitly_set", "sam_settings_schema_version"})
        check("the write is atomic: no temp file left behind",
              [p.name for p in data_dir.iterdir()] == ["settings.yaml"])
        restarted = Settings()
        check("a restart sees the choice, and incognito is back to its configured value",
              restarted.primary_model == "qwen3:8b" and restarted.model_explicitly_set is True
              and restarted.incognito is False)


def test_persistence_carries_the_repo_config_when_there_is_no_user_file():
    """The loader reads the user's settings.yaml OR config/settings.yaml,
    never both. Creating a user file with only the model keys would silently
    stop the repo's values applying, so the repo file is the starting point."""
    with scratch_settings() as (s, data_dir):
        check("precondition: no user settings file yet", not (data_dir / "settings.yaml").exists())
        s.apply_model_choice(primary="qwen3:8b")
        saved = _read_yaml(data_dir / "settings.yaml")
        repo = _read_yaml(settings_module.CONFIG_PATH)
        check("every value from config/settings.yaml is carried over unchanged",
              all(saved[k] == v for k, v in repo.items() if k != "primary_model"))
        check("plus the model choice", saved["primary_model"] == "qwen3:8b"
              and saved["model_explicitly_set"] is True)
        check("and nothing else", set(saved) == set(repo) | {"primary_model", "model_explicitly_set", "sam_settings_schema_version"})


def test_fallback_only_choice_is_not_an_explicit_primary():
    with scratch_settings() as (s, data_dir):
        s.apply_model_choice(fallback="qwen3:8b")
        saved = _read_yaml(data_dir / "settings.yaml")
        check("choosing only a fallback leaves the primary un-pinned (RAM auto-selection still applies)",
              s.model_explicitly_set is False and "model_explicitly_set" not in saved
              and s.fallback_model == "qwen3:8b" and saved["fallback_model"] == "qwen3:8b")
    with scratch_settings() as (s, data_dir):
        s.apply_model_choice()
        check("choosing nothing writes nothing", not (data_dir / "settings.yaml").exists())


# ─── J: the runtime actually receives the selected model ──────────────────

def _session(s):
    return Session(user_input="say hi", identity={"assistant_name": "SAM"}, memories=[],
                   founder_context="", settings=s)


def test_runtime_brain_receives_the_selected_model():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        brain = Brain(s)                      # ONE Settings object, shared, as in TaskGateway/main.py
        manager = ModelManager(s, brain)
        brain.process(_session(s))
        check("before selection the Brain talks to the default model",
              fake.chat_models() == ["qwen2.5:14b"])

        manager.select("qwen3:8b")
        brain.process(_session(s))
        check("after selecting, the very next Brain request goes to the selected model",
              fake.chat_models()[-1] == "qwen3:8b")
        check("Brain records what it actually used", brain._current_model == "qwen3:8b")
        check("status reports the model Brain last used",
              manager.status()["last_used_model"] == "qwen3:8b")

        manager.select("qwen2.5:14b")
        brain.process(_session(s))
        check("switching back works and is used immediately",
              fake.chat_models()[-1] == "qwen2.5:14b")
        check("no restart, no re-construction of Brain was needed", brain.settings is s)


def test_planner_and_pinned_overrides():
    from agent import planner
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        manager = ModelManager(s, Brain(s))
        manager.select("qwen3:8b")
        planner.decompose("do a thing", s)
        gen = [j["model"] for m, p, j in fake.calls if p.endswith("/api/generate")]
        check("the planner (which reads primary_model per call) follows the selection", gen == ["qwen3:8b"])

        s.planner_model = "qwen2.5:7b"
        planner.decompose("do a thing", s)
        gen = [j["model"] for m, p, j in fake.calls if p.endswith("/api/generate")]
        check("a planner explicitly pinned to another model keeps it (documented behaviour)",
              gen[-1] == "qwen2.5:7b")
        check("status reports the pinned override so the UI can't imply one model runs everything",
              manager.status()["overrides"] == {"planner": "qwen2.5:7b"})
    with scratch_settings() as (s, _):
        check("with nothing pinned, overrides is empty", ModelManager(s).pinned_overrides() == {})


# ─── K: consistency ───────────────────────────────────────────────────────

def test_state_is_consistent_everywhere():
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        brain = Brain(s)
        manager = ModelManager(s, brain)
        st = manager.select("qwen3:8b")
        models = st["models"]
        check("exactly one model is flagged selected, one active, at most one fallback",
              sum(m["is_selected"] for m in models) == 1 and sum(m["is_active"] for m in models) == 1
              and sum(m["is_fallback"] for m in models) == 1)
        flagged = next(m for m in models if m["is_selected"])
        check("settings, status.selected_model, the flagged row and Brain's own resolution all agree",
              s.primary_model == st["selected_model"] == flagged["name"] == st["active_model"]
              == brain._ensure_model() == "qwen3:8b")
        check("the fallback is untouched and still flagged",
              st["fallback_model"] == "qwen2.5:7b"
              and next(m for m in models if m["is_fallback"])["name"] == "qwen2.5:7b")
    keys = {f.name for f in fields(LocalModel)}
    check("LocalModel.to_dict() has exactly LocalModel's fields", set(LocalModel("x").to_dict()) == keys)


# ─── L: TaskGateway ───────────────────────────────────────────────────────

@contextmanager
def isolated_ledger():
    """TaskGateway's task ledger path is fixed at import time from $HOME;
    point it at a scratch directory so no run of this file (pytest included)
    writes to the real ~/.sam_data/iqoo/tasks.db."""
    import interfaces.api.task_store as task_store_module
    tmp = Path(tempfile.mkdtemp())
    with patch.object(task_store_module, "IQOO_DIR", tmp), \
         patch.object(task_store_module, "TASKS_DB_PATH", tmp / "tasks.db"):
        yield tmp


@dataclass
class FakeBrainResponse:
    text: str
    action: str = None
    action_payload: dict = None


def make_mocked_gateway(settings):
    """Same construction pattern as the iQOO offline suites (independent
    per-file copy, per repo convention)."""
    with patch("memory.identity.Identity") as MockIdentity, \
         patch("memory.retrieve.MemoryRetriever") as MockMemory, \
         patch("founder_mode.manager.FounderModeManager") as MockFounder, \
         patch("core.brain.Brain") as MockBrain, \
         patch("agent.react_loop.ReactLoop") as MockReactLoop, \
         patch("interfaces.api.gateway.VisionAdapter") as MockVision, \
         patch("interfaces.api.gateway.AudioAdapter") as MockAudio:
        MockIdentity.return_value.load.return_value = {}
        MockMemory.return_value.retrieve.return_value = []
        MockMemory.return_value.get_store.return_value = None
        MockFounder.return_value.get_context.return_value = ""
        MockFounder.return_value.capture_if_relevant.return_value = None
        MockBrain.return_value._check_ollama.return_value = True
        MockBrain.return_value._current_model = None
        MockVision.return_value.model_available.return_value = True
        MockAudio.return_value.whisper_installed.return_value = True
        settings.incognito = True
        from interfaces.api.gateway import TaskGateway
        gateway = TaskGateway(settings=settings)
        return gateway, MockBrain, MockBrain.return_value


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_gateway_wires_one_shared_settings_object():
    fake = FakeOllama(standard_models())
    with isolated_ledger(), scratch_settings() as (s, _), fake.active():
        gateway, MockBrain, _ = make_mocked_gateway(s)
        try:
            check("Brain is constructed with the SAME Settings object the manager mutates "
                  "(no second copy of 'the active model')",
                  MockBrain.call_args[0][0] is s and gateway.model_manager.settings is s)
        finally:
            gateway.shutdown()


def test_gateway_status_and_select():
    fake = FakeOllama(standard_models())
    with isolated_ledger(), scratch_settings() as (s, _), fake.active():
        gateway, _, mock_brain = make_mocked_gateway(s)
        try:
            st = gateway.get_brain_status()
            check("gateway status adds busy=False when idle", st["busy"] is False)
            check("gateway status is JSON-serialisable (a MagicMock Brain leaks nothing)",
                  json.dumps(st) and st["last_used_model"] is None)

            st = gateway.select_model("qwen3:8b")
            check("gateway.select_model applies the model and returns fresh status",
                  s.primary_model == "qwen3:8b" and st["selected_model"] == "qwen3:8b"
                  and st["active_model"] == "qwen3:8b" and st["busy"] is False)
        finally:
            gateway.shutdown()


def test_gateway_refuses_while_a_task_runs():
    from interfaces.api.gateway import BrainBusyError
    fake = FakeOllama(standard_models())
    with isolated_ledger(), scratch_settings() as (s, data_dir), fake.active():
        gateway, _, mock_brain = make_mocked_gateway(s)
        try:
            release = threading.Event()

            def slow_process(session):
                release.wait(10)
                return FakeBrainResponse(text="done", action=None)

            mock_brain.process.side_effect = slow_process
            task_id = gateway.submit_task("do something slow")
            started = wait_until(lambda: gateway._active_task_id == task_id)
            check("precondition: the worker picked the task up", started)
            check("status reports busy=True while a task runs", gateway.get_brain_status()["busy"] is True)

            fake.calls.clear()
            try:
                gateway.select_model("qwen3:8b")
                err = None
            except BrainBusyError as e:
                err = e
            except Exception as e:
                err = e
            check("select_model raises BrainBusyError while a task is active", isinstance(err, BrainBusyError))
            check("the refusal is immediate: no Ollama traffic at all", fake.calls == [])
            check("...and nothing changed (runtime or disk)",
                  s.primary_model == "qwen2.5:14b" and not (data_dir / "settings.yaml").exists())

            release.set()
            done = wait_until(lambda: (gateway.get_task(task_id) or {}).get("status") == "completed")
            wait_until(lambda: gateway._active_task_id is None)
            check("precondition: the task completed and the worker is idle", done)
            gateway.select_model("qwen3:8b")
            check("once the task has finished, the same selection succeeds", s.primary_model == "qwen3:8b")
        finally:
            release.set()
            gateway.shutdown()


def test_gateway_queued_task_also_blocks_and_race_is_closed():
    from interfaces.api.gateway import BrainBusyError
    fake = FakeOllama(standard_models())

    with isolated_ledger(), scratch_settings() as (s, _), fake.active():
        gateway, _, _ = make_mocked_gateway(s)
        gateway.shutdown()
        gateway._worker.join(3)              # worker gone, so a queued item stays queued
        gateway._queue.put("queued-not-started")
        check("a queued (not yet started) task counts as busy", gateway.get_brain_status()["busy"] is True)
        fake.calls.clear()
        try:
            gateway.select_model("qwen3:8b")
            err = None
        except BrainBusyError as e:
            err = e
        check("...and blocks a switch, with no Ollama traffic", isinstance(err, BrainBusyError)
              and fake.calls == [] and s.primary_model == "qwen2.5:14b")

    with isolated_ledger(), scratch_settings() as (s, _), fake.active():
        gateway, _, _ = make_mocked_gateway(s)
        try:
            original = gateway.model_manager.validate_selection

            def validate_then_a_task_starts(name):
                result = original(name)
                with gateway._active_lock:      # a task becomes active during the slow half
                    gateway._active_task_id = "raced-in"
                return result

            gateway.model_manager.validate_selection = validate_then_a_task_starts
            try:
                gateway.select_model("qwen3:8b")
                err = None
            except BrainBusyError as e:
                err = e
            check("a task that starts between validation and apply is caught by the re-check under the lock",
                  isinstance(err, BrainBusyError))
            check("...and the model was NOT switched", s.primary_model == "qwen2.5:14b")
            gateway._active_task_id = None
        finally:
            gateway.shutdown()


def test_gateway_failures_change_nothing():
    fake = FakeOllama(standard_models())
    with isolated_ledger(), scratch_settings() as (s, data_dir), fake.active():
        gateway, _, _ = make_mocked_gateway(s)
        try:
            try:
                gateway.select_model("not-installed:1")
                err = None
            except ModelNotInstalledError as e:
                err = e
            check("gateway surfaces ModelNotInstalledError unchanged", isinstance(err, ModelNotInstalledError))
            check("...with no state change", s.primary_model == "qwen2.5:14b"
                  and not (data_dir / "settings.yaml").exists())
        finally:
            gateway.shutdown()
    down = FakeOllama(reachable=False)
    with isolated_ledger(), scratch_settings() as (s, _), down.active():
        gateway, _, _ = make_mocked_gateway(s)
        try:
            st = gateway.get_brain_status()
            check("gateway status with Ollama down is a normal response (unavailable, busy=False)",
                  st["status"] == "unavailable" and st["busy"] is False)
        finally:
            gateway.shutdown()


# ─── M: HTTP contract (AST — FastAPI itself isn't needed) ─────────────────

SERVER_SRC = (REPO_ROOT / "interfaces" / "api" / "server.py").read_text()


def _route_table(tree):
    routes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"
                        and dec.args and isinstance(dec.args[0], ast.Constant)):
                    routes[(dec.func.attr.upper(), dec.args[0].value)] = node
    return routes


def test_http_contract():
    tree = ast.parse(SERVER_SRC)
    routes = _route_table(tree)
    check("GET /api/models is registered", ("GET", "/api/models") in routes)
    check("POST /api/models/select is registered", ("POST", "/api/models/select") in routes)
    check("the /api/iqoo/* contract is untouched (tasks, health, demo reset still registered)",
          all(k in routes for k in (("POST", "/api/iqoo/tasks"), ("GET", "/api/iqoo/health"),
                                    ("POST", "/api/iqoo/demo/reset"))))
    check("no model route lives under /api/iqoo (SAM Core, not phone-task API)",
          not any("model" in path for _, path in routes if path.startswith("/api/iqoo")))

    handler = routes[("POST", "/api/models/select")]
    mapping = {}
    for node in ast.walk(handler):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "HTTPException"):
                    code = next(k.value.value for k in sub.keywords if k.arg == "status_code")
                    mapping[ast.unparse(node.type)] = code
    expected = {"BrainBusyError": 409, "ModelNotInstalledError": 404, "ModelIncompatibleError": 422,
                "ModelMetadataError": 502, "OllamaUnavailableError": 503, "ModelManagerError": 500}
    check("each refusal has its own HTTP status: busy 409, not installed 404, incompatible 422, "
          "metadata 502, Ollama down 503, save failure 500", mapping == expected)
    try_node = next(n for n in handler.body if isinstance(n, ast.Try))
    order = [ast.unparse(h.type) for h in try_node.handlers]
    check("the catch-all ModelManagerError handler comes last (subclasses aren't shadowed)",
          order[-1] == "ModelManagerError")
    check("GET /api/models never turns an expected state into a 5xx (no except/raise in the handler)",
          not any(isinstance(n, (ast.Try, ast.Raise)) for n in ast.walk(routes[("GET", "/api/models")])))


# ─── N: schema <-> manager <-> TypeScript ─────────────────────────────────

SCHEMAS_SRC = (REPO_ROOT / "interfaces" / "api" / "schemas.py").read_text()
DESKTOP_SRC = REPO_ROOT / "interfaces" / "desktop" / "src"


def _pydantic_fields(class_name):
    tree = ast.parse(SCHEMAS_SRC)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.target.id: ast.unparse(n.annotation) for n in node.body
                    if isinstance(n, ast.AnnAssign)}
    raise AssertionError(f"{class_name} not found in schemas.py")


def _ts_interface_fields(source, name):
    m = re.search(r"export interface " + name + r"\s*\{(.*?)\n\}", source, re.S)
    assert m, f"interface {name} not found in types.ts"
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return {f.group(1): f.group(2).strip() for f in
            re.finditer(r"^\s*(\w+)\??:\s*([^;]+);", body, re.M)}


def _ts_literal_values(type_str):
    return set(re.findall(r'"([^"]+)"', type_str))


def _py_literal_values(annotation):
    return set(re.findall(r"'([^']+)'", annotation)) if "Literal" in annotation else set()


def test_schema_manager_and_typescript_contract():
    types_ts = (DESKTOP_SRC / "api" / "types.ts").read_text()

    for cls in ("ModelInfo", "BrainStatus", "ModelSelectRequest"):
        py, ts = _pydantic_fields(cls), _ts_interface_fields(types_ts, cls)
        check(f"{cls}: schemas.py and types.ts declare exactly the same fields",
              set(py) == set(ts))

    py_info = _pydantic_fields("ModelInfo")
    check("ModelInfo fields == LocalModel.to_dict() keys (manager cannot drift from the schema)",
          set(py_info) == set(LocalModel("x").to_dict()))

    py_status = _pydantic_fields("BrainStatus")
    fake = FakeOllama(standard_models())
    with scratch_settings() as (s, _), fake.active():
        ready = ModelManager(s).status()
    with scratch_settings() as (s, _), FakeOllama(reachable=False).active():
        down = ModelManager(s).status()
    gateway_keys = {"busy"}  # added by TaskGateway.get_brain_status(), not the manager
    check("BrainStatus fields == manager status keys + gateway's 'busy' (ready branch)",
          set(py_status) == set(ready) | gateway_keys)
    check("...and the Ollama-down branch returns the same key set (no branch-specific fields)",
          set(down) == set(ready))

    ts_info = _ts_interface_fields(types_ts, "ModelInfo")
    ts_status = _ts_interface_fields(types_ts, "BrainStatus")
    check("compatibility literal values match between Python and TypeScript",
          _py_literal_values(py_info["compatibility"]) == _ts_literal_values(ts_info["compatibility"])
          == {COMPAT_UNKNOWN, COMPAT_INCOMPATIBLE})
    check("status / active_source literal values match between Python and TypeScript",
          _py_literal_values(py_status["status"]) == _ts_literal_values(ts_status["status"]) == {"ready", "unavailable"}
          and _py_literal_values(py_status["active_source"]) == _ts_literal_values(ts_status["active_source"])
          == {"selected", "fallback"})


def _frontend_sources_except_types():
    out = []
    for p in DESKTOP_SRC.rglob("*"):
        if p.suffix in (".ts", ".tsx") and p.name not in ("types.ts", "react-shim.d.ts") \
                and p.relative_to(DESKTOP_SRC).as_posix() != "api/types.ts":
            out.append(p.read_text())
    return "\n".join(out)


def test_every_backend_field_is_consumed_by_the_desktop_ui():
    """'Do not create a backend response field that is never consumed.'"""
    src = _frontend_sources_except_types()
    for cls in ("ModelInfo", "BrainStatus"):
        for name in _pydantic_fields(cls):
            check(f"{cls}.{name} is read by the desktop UI",
                  re.search(r"\.\s*" + name + r"\b", src) is not None)


def test_desktop_client_matches_the_server_routes():
    client = (DESKTOP_SRC / "api" / "client.ts").read_text()
    routes = _route_table(ast.parse(SERVER_SRC))
    check("client.ts requests GET /api/models (getBrainStatus)",
          re.search(r"getBrainStatus[^{]*\{[^}]*?\"/models\"", client, re.S) is not None
          and ("GET", "/api/models") in routes)
    check("client.ts POSTs the selection to /api/models/select with {model}",
          re.search(r"selectModel[^{]*\{.*?\"/models/select\".*?method:\s*\"POST\".*?JSON\.stringify\(\{\s*model", client, re.S)
          is not None and ("POST", "/api/models/select") in routes)
    check("the task/iQOO client still targets /api/iqoo",
          'const BASE = "/api/iqoo"' in client)
    brain_service = (DESKTOP_SRC / "services" / "brain.ts").read_text()
    check("the Brain service seam exposes exactly the two real calls",
          "getBrainStatus" in brain_service and "selectModel" in brain_service)


# ─── O: desktop product structure ─────────────────────────────────────────

def test_desktop_product_structure():
    routes_ts = (DESKTOP_SRC / "app" / "routes.ts").read_text()
    router_tsx = (DESKTOP_SRC / "app" / "router.tsx").read_text()
    check("the demo Models page (hardcoded qwen list, mode=demo) is gone",
          not (DESKTOP_SRC / "features" / "models").exists())
    for path in ("/", "/chat", "/tasks", "/brain", "/hands", "/iqoo"):
        check(f"route {path} exists and has a built page (no PLANNED stub)",
              f'path: "{path}"' in routes_ts and f'"{path}":' in router_tsx)
    check("Brain is a first-class page, not folded under 'System'",
          re.search(r'path: "/brain".*?group: "(\w+)"', routes_ts, re.S).group(1) != "system")
    brain_page = (DESKTOP_SRC / "features" / "brain" / "BrainPage.tsx").read_text()
    check("the Brain page is LIVE, not DEMO",
          'mode="live"' in brain_page and 'mode="demo"' not in brain_page)
    hands = (DESKTOP_SRC / "features" / "hands" / "capabilities.ts").read_text()
    ids = re.findall(r'id:\s*"([\w-]+)"', hands)
    check("Hands lists desktop control, vision, terminal and verification alongside the browser "
          "(browser is one entry among several)",
          {"desktop-control", "vision", "browser", "terminal", "verification"} <= set(ids)
          and ids.count("browser") == 1)
    check("Office Kit is listed as not implemented rather than implied to work",
          re.search(r'id:\s*"office-kit".*?availability:\s*"not-implemented"', hands, re.S) is not None)
    check("no browser-specific UI was added outside the Hands page",
          not list((DESKTOP_SRC / "features").rglob("*[Bb]rowser*")))


TESTS = [
    test_discovery_parsing, test_discovery_metadata_shapes_are_tolerated, test_empty_model_list,
    test_ollama_unavailable, test_active_model_resolution, test_status_stays_in_step_with_brain_ensure_model,
    test_compatibility_is_conservative, test_listing_degrades_per_model_but_selection_does_not,
    test_metadata_is_cached_by_digest, test_valid_selection_applies_and_persists,
    test_selecting_the_current_model_is_a_noop_write, test_selection_normalises_to_the_installed_spelling,
    test_persistence_writes_only_the_model_keys, test_persistence_carries_the_repo_config_when_there_is_no_user_file,
    test_fallback_only_choice_is_not_an_explicit_primary, test_cli_model_command_only_claims_model_names,
    test_invalid_selections_fail_cleanly_and_change_nothing, test_save_failure_rolls_back_the_runtime_setting,
    test_runtime_brain_receives_the_selected_model, test_planner_and_pinned_overrides,
    test_state_is_consistent_everywhere, test_gateway_wires_one_shared_settings_object,
    test_gateway_status_and_select, test_gateway_refuses_while_a_task_runs,
    test_gateway_queued_task_also_blocks_and_race_is_closed, test_gateway_failures_change_nothing,
    test_http_contract, test_schema_manager_and_typescript_contract,
    test_every_backend_field_is_consumed_by_the_desktop_ui, test_desktop_client_matches_the_server_routes,
    test_desktop_product_structure,
]


def main():
    for t in TESTS:
        print(f"\n=== {t.__name__} ===")
        t()
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Brain/model management verified (fake Ollama, no network, no real installation used).")


if __name__ == "__main__":
    main()

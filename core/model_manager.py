"""
SAM Core — local Brain model management.

Turns "which model is SAM thinking with?" into something that can be asked
and changed at runtime, without a second source of truth:

    Ollama /api/tags, /api/show      (what is installed, and what it can do)
            |
      discovery + compatibility      (this module; read-only)
            |
       selection (validated)         (this module -> Settings.apply_model_choice)
            |
    Settings.primary_model           (THE source of truth, unchanged)
            |
       Brain._ensure_model()         (already reads it on every request)

Nothing here replaces Brain: core/brain.py still resolves primary -> fallback
per request from the same Settings object. Switching is therefore just
"validate, then set Settings.primary_model" -- every consumer that already
reads that field (Brain, planner, reflection, Founder Mode classifier, memory
extraction) follows on its next call. The module has no dependency on
interfaces/ or FastAPI, so the desktop API, the CLI and the tests share one
implementation.

Terms used precisely (they are not synonyms):
  installed          present in Ollama (/api/tags)
  selected           Settings.primary_model -- what the user asked for
  fallback           Settings.fallback_model -- used when selected is missing
  active             what Brain._ensure_model() would use for the next
                     request (selected if installed, else fallback if
                     installed, else nothing)
  compatible         see "Compatibility" below -- deliberately never claimed

Compatibility is conservative on purpose. SAM's Brain talks to /api/chat with
format=json and expects {"text", "action", "action_payload"} back. Whether a
given model reliably produces that cannot be known from Ollama metadata, so
this module only ever says:
  incompatible  provably unusable as a Brain (an embedding-only model, or the
                model SAM itself is configured to use for embeddings)
  unknown       everything else -- chat-capable as far as Ollama can tell, but
                not verified against SAM's JSON action format
There is intentionally no "compatible" value: nothing in this repository can
verify one, and a false positive is worse than an honest "unknown".
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("SAM.ModelManager")

PROVIDER = "ollama"

COMPAT_UNKNOWN = "unknown"
COMPAT_INCOMPATIBLE = "incompatible"

TAGS_TIMEOUT_S = 5
SHOW_TIMEOUT_S = 5

# Settings fields that pin a subsystem to its own model. They default to
# None ("use primary_model"); when set they do NOT follow a Brain switch, so
# the status reports them rather than letting the UI imply one model runs
# everything.
_PINNABLE = (
    ("planner", "planner_model"),
    ("reflection", "reflection_model"),
    ("founder_classifier", "founder_mode_classifier_model"),
)


# ─── Errors ────────────────────────────────────────────────────────────────
# One base class so callers can catch "any expected model-management failure"
# without swallowing real bugs. Each subclass maps to a distinct, actionable
# outcome (the API layer turns them into distinct HTTP statuses).

class ModelManagerError(Exception):
    """Base class for every expected model-management failure."""


class OllamaUnavailableError(ModelManagerError):
    """Ollama can't be reached, or answered with something unusable."""


class ModelNotInstalledError(ModelManagerError):
    """The requested model isn't installed in Ollama."""


class ModelMetadataError(ModelManagerError):
    """Ollama is up and the model is installed, but its metadata couldn't
    be read -- selection refuses rather than guessing."""


class ModelIncompatibleError(ModelManagerError):
    """The model is provably unusable as SAM's Brain."""


class ModelPersistError(ModelManagerError):
    """The choice couldn't be written to ~/.sam_data/settings.yaml. The
    in-memory setting has been rolled back (Settings.apply_model_choice)."""


# ─── Name handling ─────────────────────────────────────────────────────────

def canonical_name(name: str) -> str:
    """Ollama treats "qwen3" and "qwen3:latest" as the same model. Brain's
    own matching is an exact string compare against /api/tags, so the name
    stored in Settings must be the installed spelling -- see
    resolve_installed_name()."""
    name = (name or "").strip()
    if name and ":" not in name.rsplit("/", 1)[-1]:
        return name + ":latest"
    return name


def same_model(a: str, b: str) -> bool:
    return canonical_name(a) == canonical_name(b)


def resolve_installed_name(requested: str, installed: List[str]) -> Optional[str]:
    """The installed spelling of `requested`, or None if it isn't installed."""
    requested = (requested or "").strip()
    if not requested:
        return None
    if requested in installed:
        return requested
    for candidate in installed:
        if same_model(candidate, requested):
            return candidate
    return None


def auxiliary_role(settings, name: str) -> Optional[str]:
    """"embedding" or "vision" when `name` is a model SAM itself is
    configured to use for that job (read from Settings, not from any
    hardcoded list of names), else None. A typical install pulls both next
    to the chat model, so they always show up in /api/tags."""
    for role, attr in (("embedding", "embedding_model"),
                       ("vision", "vision_model"),
                       ("vision", "sovereign_vision_model")):
        configured = getattr(settings, attr, None)
        if configured and same_model(configured, name):
            return role
    return None


# ─── Compatibility ─────────────────────────────────────────────────────────

def classify(settings, name: str, capabilities: Optional[List[str]],
             context_length: Optional[int]) -> Tuple[str, str, List[str]]:
    """
    Returns (compatibility, reason, notes). Pure -- no I/O.

    `capabilities` is Ollama's own list from /api/show ("completion",
    "tools", "vision", "thinking", "embedding", ...), or None when it wasn't
    reported (older Ollama, or metadata unavailable). Native tool calling is
    NOT required: Brain never sends Ollama a `tools` field, it asks for a JSON
    object in the prompt. Vision is NOT required either: screen reading uses
    the separate vision_model.
    """
    notes: List[str] = []
    role = auxiliary_role(settings, name)

    if role == "embedding":
        return (COMPAT_INCOMPATIBLE,
                "Configured as SAM's embedding model, which can't generate replies.", notes)
    if capabilities is not None and "completion" not in capabilities:
        return (COMPAT_INCOMPATIBLE,
                "Ollama reports no text-generation capability (embedding-only model).", notes)

    if role == "vision":
        notes.append("Configured as SAM's vision model; not validated as a Brain.")
    if capabilities is not None and "thinking" in capabilities:
        notes.append("Reasoning model: its thinking tokens count against max_tokens, "
                     "and SAM's JSON action format is unverified with it.")
    configured_ctx = getattr(settings, "model_context_length", None)
    if context_length is not None and configured_ctx and context_length < configured_ctx:
        notes.append(f"Model's context limit ({context_length}) is below SAM's "
                     f"configured context ({configured_ctx}).")

    if capabilities is None:
        reason = ("Ollama didn't report this model's capabilities, and SAM hasn't "
                  "verified it with its JSON action format.")
    else:
        reason = "Chat-capable per Ollama; SAM hasn't verified it with its JSON action format."
    return COMPAT_UNKNOWN, reason, notes


@dataclass
class LocalModel:
    """One installed model, as shown to the user. Everything here comes from
    Ollama or Settings -- nothing is inferred from the model's name."""
    name: str
    size_bytes: Optional[int] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    capabilities: Optional[List[str]] = None
    context_length: Optional[int] = None
    compatibility: str = COMPAT_UNKNOWN
    compatibility_reason: str = ""
    notes: List[str] = field(default_factory=list)
    is_selected: bool = False
    is_fallback: bool = False
    is_active: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Manager ───────────────────────────────────────────────────────────────

class ModelManager:
    """
    Read/select operations over the same Settings object Brain holds.

    `brain` is optional and used only to report the model Brain last sent a
    request to. Selection is split into validate_selection() (network, no
    side effects) and apply_selection() (mutates Settings) so a caller that
    must serialize against running work -- interfaces/api/gateway.py does --
    can keep its lock held only around the fast half.
    """

    def __init__(self, settings, brain=None):
        self.settings = settings
        self.brain = brain
        # /api/show results keyed by (name, digest): a model's digest changes
        # when it is re-pulled, so a hit is never stale, and repeated status
        # calls don't re-query every model.
        self._show_cache: Dict[Tuple[str, str], dict] = {}

    # -- Ollama access -----------------------------------------------------

    def _host(self) -> str:
        return str(self.settings.ollama_host).rstrip("/")

    def _fetch_tags(self) -> List[dict]:
        host = self._host()
        try:
            r = requests.get(f"{host}/api/tags", timeout=TAGS_TIMEOUT_S)
        except Exception as e:
            raise OllamaUnavailableError(
                f"Ollama isn't reachable at {host}. Start it with: ollama serve") from e
        if r.status_code != 200:
            raise OllamaUnavailableError(
                f"Ollama at {host} answered HTTP {r.status_code} when listing models.")
        try:
            models = r.json().get("models", [])
        except Exception as e:
            raise OllamaUnavailableError(
                f"Ollama at {host} returned a model list SAM couldn't read.") from e
        return [m for m in models if isinstance(m, dict) and (m.get("name") or m.get("model"))]

    @staticmethod
    def _tag_name(entry: dict) -> str:
        return entry.get("name") or entry.get("model")

    def _fetch_show(self, name: str, digest: str = "") -> dict:
        key = (name, digest or "")
        if digest and key in self._show_cache:
            return self._show_cache[key]
        try:
            # "name" is the pre-"model" spelling older Ollama versions expect.
            r = requests.post(f"{self._host()}/api/show",
                              json={"model": name, "name": name}, timeout=SHOW_TIMEOUT_S)
        except Exception as e:
            raise ModelMetadataError(f"Couldn't read metadata for '{name}': {e}") from e
        if r.status_code != 200:
            raise ModelMetadataError(
                f"Ollama couldn't describe '{name}' (HTTP {r.status_code}).")
        try:
            data = r.json()
        except Exception as e:
            raise ModelMetadataError(f"Ollama returned unreadable metadata for '{name}'.") from e
        if not isinstance(data, dict):
            raise ModelMetadataError(f"Ollama returned unreadable metadata for '{name}'.")
        if digest:
            self._show_cache[key] = data
        return data

    @staticmethod
    def _parse_show(data: dict) -> Tuple[Optional[List[str]], Optional[int]]:
        caps = data.get("capabilities")
        capabilities = [str(c) for c in caps] if isinstance(caps, list) else None
        context_length = None
        info = data.get("model_info")
        if isinstance(info, dict):
            arch = info.get("general.architecture")
            value = info.get(f"{arch}.context_length") if arch else None
            if isinstance(value, int) and not isinstance(value, bool):
                context_length = value
        return capabilities, context_length

    # -- Reading -----------------------------------------------------------

    def resolve_active(self, installed_names: List[str]) -> Optional[str]:
        """Mirrors Brain._ensure_model()'s rule exactly (exact-name match:
        selected, then fallback, else nothing) so status can't disagree with
        what a request would actually do. tests/test_brain_model_management_
        offline.py pins the two together."""
        if self.settings.primary_model in installed_names:
            return self.settings.primary_model
        if self.settings.fallback_model in installed_names:
            return self.settings.fallback_model
        return None

    def list_models(self) -> List[LocalModel]:
        """Every installed model with metadata and compatibility. A model
        whose /api/show fails is still listed (capabilities None) -- listing
        degrades per model, selection does not. Raises OllamaUnavailableError."""
        tags = self._fetch_tags()
        names = [self._tag_name(t) for t in tags]
        active = self.resolve_active(names)
        models: List[LocalModel] = []
        for entry in tags:
            name = self._tag_name(entry)
            details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
            capabilities = context_length = None
            try:
                capabilities, context_length = self._parse_show(
                    self._fetch_show(name, str(entry.get("digest") or "")))
            except ModelMetadataError as e:
                logger.debug(f"Metadata unavailable for {name}: {e}")
            compat, reason, notes = classify(self.settings, name, capabilities, context_length)
            size = entry.get("size")
            models.append(LocalModel(
                name=name,
                size_bytes=size if isinstance(size, int) and not isinstance(size, bool) else None,
                parameter_size=details.get("parameter_size") or None,
                quantization=details.get("quantization_level") or None,
                family=details.get("family") or None,
                capabilities=capabilities,
                context_length=context_length,
                compatibility=compat,
                compatibility_reason=reason,
                notes=notes,
                is_selected=(name == self.settings.primary_model),
                is_fallback=(name == self.settings.fallback_model),
                is_active=(name == active),
            ))
        return models

    def pinned_overrides(self) -> Dict[str, str]:
        """Subsystems configured with their own model (they ignore a Brain switch)."""
        pinned = {}
        for label, attr in _PINNABLE:
            value = getattr(self.settings, attr, None)
            if isinstance(value, str) and value:
                pinned[label] = value
        return pinned

    def status(self) -> dict:
        """The complete Brain state as a plain dict. Never raises for an
        expected condition: Ollama being down or no usable model installed is
        reported as status="unavailable" with a detail, because that is a
        normal state to show, not a server fault."""
        s = self.settings
        last_used = getattr(self.brain, "_current_model", None) if self.brain is not None else None
        out = {
            "provider": PROVIDER,
            "ollama_host": str(s.ollama_host),
            "selected_model": s.primary_model,
            "fallback_model": s.fallback_model,
            "user_selected": bool(s.model_explicitly_set),
            "last_used_model": last_used if isinstance(last_used, str) else None,
            "overrides": self.pinned_overrides(),
        }
        try:
            models = self.list_models()
        except OllamaUnavailableError as e:
            return {**out, "status": "unavailable", "detail": str(e),
                    "active_model": None, "active_source": None, "models": []}

        active = next((m.name for m in models if m.is_active), None)
        detail = None
        if active is None:
            status = "unavailable"
            if not models:
                detail = "No models are installed in Ollama. Install one with: ollama pull <model>"
            else:
                detail = (f"Neither the selected model ({s.primary_model}) nor the fallback "
                          f"({s.fallback_model}) is installed. Choose an installed model below.")
        else:
            status = "ready"
            if active != s.primary_model:
                detail = (f"The selected model ({s.primary_model}) isn't installed, "
                          f"so SAM is using the fallback ({active}).")
        return {**out, "status": status, "detail": detail, "active_model": active,
                "active_source": None if active is None
                else ("selected" if active == s.primary_model else "fallback"),
                "models": [m.to_dict() for m in models]}

    # -- Selecting ---------------------------------------------------------

    def validate_selection(self, requested: str) -> str:
        """Everything that can be checked without changing anything. Returns
        the installed spelling of the model to store. Raises
        OllamaUnavailableError, ModelNotInstalledError, ModelMetadataError or
        ModelIncompatibleError -- never selects on a guess."""
        requested = (requested or "").strip()
        tags = self._fetch_tags()
        installed = [self._tag_name(t) for t in tags]
        name = resolve_installed_name(requested, installed)
        if name is None:
            raise ModelNotInstalledError(
                f"'{requested}' isn't installed in Ollama. Install it with: ollama pull {requested}"
                if requested else "Choose a model to select.")
        entry = next(t for t in tags if self._tag_name(t) == name)
        capabilities, context_length = self._parse_show(
            self._fetch_show(name, str(entry.get("digest") or "")))
        compat, reason, _ = classify(self.settings, name, capabilities, context_length)
        if compat == COMPAT_INCOMPATIBLE:
            raise ModelIncompatibleError(f"'{name}' can't be used as SAM's Brain: {reason}")
        return name

    def apply_selection(self, name: str) -> None:
        """Make an already-validated installed model the Brain and persist it.
        Fast (a settings write); callers that serialize against running tasks
        hold their lock around this call only."""
        if name == self.settings.primary_model and self.settings.model_explicitly_set:
            return
        try:
            self.settings.apply_model_choice(primary=name)
        except Exception as e:
            raise ModelPersistError(f"Couldn't save the model choice: {e}") from e
        logger.info(f"Brain model selected: {name}")

    def select(self, requested: str) -> dict:
        """validate + apply + fresh status. For callers with no concurrency
        concern of their own (CLI, tests)."""
        name = self.validate_selection(requested)
        self.apply_selection(name)
        return self.status()

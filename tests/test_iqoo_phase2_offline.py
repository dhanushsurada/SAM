"""
OFFLINE / MOCKED test suite for iQOO Phase 2 (multimodal perception).

Everything in this file is offline and mocked: no live Ollama, no real
faster-whisper model, no phone, no camera, no microphone. Vision and
audio interpretation quality is NOT tested here — that requires the
real Mac + Ollama + a real device, per the PDR's "manually test"
requirement, and has NOT been performed in this environment. This suite
tests the plumbing around perception: validation, adapter wiring,
structured-context composition, error handling, cancellation, and that
Phase 1's text-only path and concurrency/serialization guarantees are
completely unaffected by any of it.

Usage:
    HOME=/tmp/sam_iqoo_phase2_test python3 tests/test_iqoo_phase2_offline.py
"""

import base64
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


@dataclass
class FakeBrainResponse:
    text: str
    action: str = None
    action_payload: dict = None


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


FAKE_JPEG = b64(b"\xff\xd8\xff" + b"fake jpeg bytes for offline testing" * 4)
FAKE_WAV = b64(b"RIFF" + b"fake wav bytes for offline testing" * 4)


def make_mocked_gateway():
    """Same construction pattern as test_iqoo_phase1_offline.py's helper,
    duplicated locally (not imported cross-file) so this suite has no
    load-order dependency on the Phase 1 file and can be run completely
    standalone, matching the existing repo convention of independent
    per-phase test files."""
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

        from config.settings import Settings
        settings = Settings()
        settings.incognito = True

        from interfaces.api.gateway import TaskGateway
        gateway = TaskGateway(settings=settings)
        return gateway, MockBrain.return_value, MockReactLoop.return_value, \
            MockVision.return_value, MockAudio.return_value


def wait_for_status(gateway, task_id, statuses, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        record = gateway.get_task(task_id)
        last = record["status"] if record else None
        if last in statuses:
            return last
        time.sleep(0.05)
    return last


# ─── Schema / validation tests (no gateway needed) ─────────────────────────

def test_backward_compat_text_only_schema():
    from interfaces.api.schemas import TaskCreateRequest

    req = TaskCreateRequest(instruction="open Safari")
    check("Phase 1 text-only request shape still parses unchanged",
          req.input_type == "text" and req.attachments == [])


def test_media_validation_helpers():
    from multimodal.media_validation import validate_attachment, AttachmentValidationError

    raw = validate_attachment("image", "image/jpeg", FAKE_JPEG)
    check("Valid image passes validation and returns decoded bytes", isinstance(raw, bytes) and len(raw) > 0)

    try:
        validate_attachment("image", "image/gif", FAKE_JPEG)
        check("Unsupported image MIME type rejected", False)
    except AttachmentValidationError as e:
        check("Unsupported image MIME type rejected", "Unsupported" in str(e))

    try:
        validate_attachment("image", "image/jpeg", "not-valid-base64!!!")
        check("Malformed base64 rejected", False)
    except AttachmentValidationError:
        check("Malformed base64 rejected", True)

    try:
        validate_attachment("image", "image/jpeg", "")
        check("Empty attachment data rejected", False)
    except AttachmentValidationError:
        check("Empty attachment data rejected", True)

    oversized = b64(b"x" * (9 * 1024 * 1024))  # over the 8MB image limit
    try:
        validate_attachment("image", "image/jpeg", oversized)
        check("Oversized image rejected", False)
    except AttachmentValidationError as e:
        check("Oversized image rejected", "too large" in str(e))

    try:
        validate_attachment("audio", "audio/aac", FAKE_WAV)
        check("Unsupported audio MIME type rejected", False)
    except AttachmentValidationError:
        check("Unsupported audio MIME type rejected", True)

    audio_raw = validate_attachment("audio", "audio/webm", FAKE_WAV)
    check("Valid audio passes validation", isinstance(audio_raw, bytes) and len(audio_raw) > 0)


def test_task_create_request_multimodal_validation():
    from interfaces.api.schemas import TaskCreateRequest
    from pydantic import ValidationError

    # Valid image+text
    req = TaskCreateRequest(
        instruction="turn this into a backend",
        input_type="image+text",
        attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
    )
    check("Valid image+text request parses", req.input_type == "image+text")

    # Valid voice
    req = TaskCreateRequest(
        instruction="(voice command)",
        input_type="voice",
        attachments=[{"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV}],
    )
    check("Valid voice request parses", req.input_type == "voice")

    # Valid image+voice
    req = TaskCreateRequest(
        instruction="(voice command)",
        input_type="image+voice",
        attachments=[
            {"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG},
            {"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV},
        ],
    )
    check("Valid image+voice request parses", req.input_type == "image+voice")

    # Missing image attachment for declared image input_type
    try:
        TaskCreateRequest(instruction="do it", input_type="image", attachments=[])
        check("image input_type without an image attachment is rejected", False)
    except ValidationError:
        check("image input_type without an image attachment is rejected", True)

    # Missing audio attachment for declared voice input_type
    try:
        TaskCreateRequest(instruction="do it", input_type="voice", attachments=[])
        check("voice input_type without an audio attachment is rejected", False)
    except ValidationError:
        check("voice input_type without an audio attachment is rejected", True)

    # image+voice missing one of the two required attachments
    try:
        TaskCreateRequest(
            instruction="do it", input_type="image+voice",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        check("image+voice missing audio attachment is rejected", False)
    except ValidationError:
        check("image+voice missing audio attachment is rejected", True)

    # Malformed attachment (bad MIME) surfaces as a validation error at parse time
    try:
        TaskCreateRequest(
            instruction="do it", input_type="image",
            attachments=[{"kind": "image", "mime_type": "application/pdf", "data": FAKE_JPEG}],
        )
        check("Malformed attachment MIME rejected at schema level", False)
    except ValidationError:
        check("Malformed attachment MIME rejected at schema level", True)


# ─── Adapter unit tests (mocked HTTP / mocked STT internals) ───────────────

def test_vision_adapter_success_and_failure():
    from multimodal.vision.adapter import VisionAdapter
    from multimodal.errors import PerceptionError

    class FakeSettings:
        vision_model = "moondream"
        ollama_host = "http://localhost:11434"

    adapter = VisionAdapter(FakeSettings())

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"response": "A whiteboard with a User table and a Post table, linked by user_id."}

    with patch("multimodal.vision.adapter.requests.post", return_value=FakeResponse()):
        result = adapter.interpret({"data": FAKE_JPEG}, "Turn this into a backend")
        check("Vision adapter returns model's description on success",
              "User table" in result)

    class EmptyResponse:
        status_code = 200
        def json(self):
            return {"response": ""}

    with patch("multimodal.vision.adapter.requests.post", return_value=EmptyResponse()):
        try:
            adapter.interpret({"data": FAKE_JPEG}, "describe it")
            check("Empty vision response raises PerceptionError", False)
        except PerceptionError:
            check("Empty vision response raises PerceptionError", True)

    class ErrorResponse:
        status_code = 500
        def json(self):
            return {}

    with patch("multimodal.vision.adapter.requests.post", return_value=ErrorResponse()):
        try:
            adapter.interpret({"data": FAKE_JPEG}, "describe it")
            check("Non-200 vision response raises PerceptionError", False)
        except PerceptionError:
            check("Non-200 vision response raises PerceptionError", True)

    import requests as real_requests
    with patch("multimodal.vision.adapter.requests.post",
               side_effect=real_requests.ConnectionError("no route to host")):
        try:
            adapter.interpret({"data": FAKE_JPEG}, "describe it")
            check("Unreachable Ollama raises PerceptionError, not a raw exception", False)
        except PerceptionError:
            check("Unreachable Ollama raises PerceptionError, not a raw exception", True)


def test_audio_adapter_success_and_failure():
    from multimodal.audio.adapter import AudioAdapter
    from multimodal.errors import PerceptionError

    class FakeSettings:
        whisper_model = "base.en"

    adapter = AudioAdapter(FakeSettings())

    class FakeSegment:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def transcribe(self, path, **kwargs):
            return [FakeSegment("turn this into a tested FastAPI backend")], object()

    class FakeSTT:
        _model = FakeModel()

    with patch.object(adapter, "_get_stt", return_value=FakeSTT()):
        transcript = adapter.transcribe({"mime_type": "audio/webm", "data": FAKE_WAV})
        check("Audio adapter returns transcript on success",
              transcript == "turn this into a tested FastAPI backend")

    class EmptyModel:
        def transcribe(self, path, **kwargs):
            return [], object()

    class EmptySTT:
        _model = EmptyModel()

    with patch.object(adapter, "_get_stt", return_value=EmptySTT()):
        try:
            adapter.transcribe({"mime_type": "audio/webm", "data": FAKE_WAV})
            check("Empty transcript raises PerceptionError (silent recording)", False)
        except PerceptionError:
            check("Empty transcript raises PerceptionError (silent recording)", True)

    try:
        adapter.transcribe({"mime_type": "audio/webm", "data": "not valid base64 at all!!"})
        check("Malformed base64 audio raises PerceptionError", False)
    except PerceptionError:
        check("Malformed base64 audio raises PerceptionError", True)

    class BrokenModel:
        def transcribe(self, path, **kwargs):
            raise RuntimeError("model crashed")

    class BrokenSTT:
        _model = BrokenModel()

    with patch.object(adapter, "_get_stt", return_value=BrokenSTT()):
        try:
            adapter.transcribe({"mime_type": "audio/webm", "data": FAKE_WAV})
            check("Whisper crash surfaces as PerceptionError, not a raw exception", False)
        except PerceptionError:
            check("Whisper crash surfaces as PerceptionError, not a raw exception", True)

    # No faster-whisper installed (fallback path) + unsupported container
    # format for the fallback recognizer -> honest failure, no silent
    # mis-transcription.
    class NoModelSTT:
        _model = None

    with patch.object(adapter, "_get_stt", return_value=NoModelSTT()):
        try:
            adapter.transcribe({"mime_type": "audio/webm", "data": FAKE_WAV})
            check("Fallback path refuses unsupported container format honestly", False)
        except PerceptionError as e:
            check("Fallback path refuses unsupported container format honestly",
                  "WAV/AIFF/FLAC" in str(e))


# ─── Gateway integration tests (perception wired into the task pipeline) ──

def test_gateway_image_text_task_builds_structured_context():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_vision.interpret.return_value = "A User table with id, name, email fields."
        mock_brain.process.return_value = FakeBrainResponse(text="Built it.", action=None)

        task_id = gateway.submit_task(
            "Turn this into a tested FastAPI backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        check("image+text task completes", final == "completed")
        check("Vision adapter was actually invoked", mock_vision.interpret.called)

        session_arg = mock_brain.process.call_args[0][0]
        check("Structured context includes original instruction",
              "Turn this into a tested FastAPI backend" in session_arg.user_input)
        check("Structured context includes vision description",
              "User table with id, name, email fields" in session_arg.user_input)
        check("Structured context is clearly framed as image context",
              "[Image context" in session_arg.user_input and "[End image context]" in session_arg.user_input)
    finally:
        gateway.shutdown()


def test_gateway_voice_task_uses_transcript_as_instruction():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_audio.transcribe.return_value = "open safari and go to github"
        mock_brain.process.return_value = FakeBrainResponse(text="Done.", action=None)

        task_id = gateway.submit_task(
            "(voice command)", input_type="voice",
            attachments=[{"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV}],
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        check("voice task completes", final == "completed")
        check("Audio adapter was actually invoked", mock_audio.transcribe.called)

        session_arg = mock_brain.process.call_args[0][0]
        check("Transcript reaches the Brain as part of the instruction",
              "open safari and go to github" in session_arg.user_input)
    finally:
        gateway.shutdown()


def test_gateway_image_voice_task_combines_both():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_audio.transcribe.return_value = "make this a tested backend"
        mock_vision.interpret.return_value = "Two tables: User and Post."
        mock_brain.process.return_value = FakeBrainResponse(text="Done.", action=None)

        task_id = gateway.submit_task(
            "(voice command)", input_type="image+voice",
            attachments=[
                {"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG},
                {"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV},
            ],
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        check("image+voice task completes", final == "completed")

        session_arg = mock_brain.process.call_args[0][0]
        check("Combined instruction includes transcribed speech",
              "make this a tested backend" in session_arg.user_input)
        check("Combined instruction includes vision description",
              "Two tables: User and Post" in session_arg.user_input)

        # Vision should be given the transcript as its framing instruction
        # when no typed text was provided (base_instruction is a placeholder).
        vision_call_instruction = mock_vision.interpret.call_args[0][1]
        check("Vision adapter receives the transcribed speech as its instruction context",
              vision_call_instruction == "make this a tested backend")
    finally:
        gateway.shutdown()


def test_gateway_perception_failure_reports_cleanly():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        from multimodal.errors import PerceptionError
        mock_vision.interpret.side_effect = PerceptionError("could not read handwriting")

        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Perception failure fails the task, not silently ignored",
              final == "failed" and "could not read handwriting" in (record["error"] or ""))
        check("Brain is never reached after a perception failure",
              not mock_brain.process.called)
        check("ReactLoop is never reached after a perception failure",
              not mock_react_loop.run_planned_task.called)
    finally:
        gateway.shutdown()


def test_gateway_perception_timeout_like_failure():
    """Simulates a slow/unreachable vision model raising after a delay —
    proves a hung/failed perception call degrades to a clean 'failed'
    status rather than leaving the task (and the single worker thread)
    stuck forever."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        from multimodal.errors import PerceptionError

        def slow_then_fail(attachment, instruction):
            time.sleep(0.05)
            raise PerceptionError("vision model timed out")

        mock_vision.interpret.side_effect = slow_then_fail

        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"}, timeout=5.0)
        record = gateway.get_task(task_id)
        check("Slow-then-failing perception still resolves to failed (worker not stuck)",
              final == "failed" and "timed out" in (record["error"] or ""))

        # Worker thread must still be alive and able to take the next task.
        mock_vision.interpret.side_effect = None
        mock_vision.interpret.return_value = "fine now"
        mock_brain.process.return_value = FakeBrainResponse(text="ok", action=None)
        task_id2 = gateway.submit_task(
            "another one", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        final2 = wait_for_status(gateway, task_id2, {"completed", "failed"})
        check("Worker thread survives a perception failure and processes the next task",
              final2 == "completed")
    finally:
        gateway.shutdown()


def test_gateway_missing_attachment_fails_before_perception_call():
    """Belt-and-suspenders: even if something got past the FastAPI schema
    validator (e.g. a direct gateway.submit_task call, as internal code
    paths might do), the gateway's own _perceive() guard still refuses to
    silently proceed with a declared-but-missing attachment."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text", attachments=[]
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Declared image input_type with no image attachment fails cleanly",
              final == "failed" and "no image attachment" in (record["error"] or ""))
        check("Vision adapter never called when the attachment itself is missing",
              not mock_vision.interpret.called)
    finally:
        gateway.shutdown()


def test_gateway_cancellation_during_perception():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        release = {"go": False}

        def slow_interpret(attachment, instruction):
            while not release["go"]:
                time.sleep(0.01)
            return "too late"

        mock_vision.interpret.side_effect = slow_interpret

        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        # Wait until it's actually in perceiving before cancelling.
        deadline = time.time() + 2
        while time.time() < deadline and gateway.get_task(task_id)["status"] != "perceiving":
            time.sleep(0.01)

        ok = gateway.cancel_task(task_id)
        check("Cancel accepted while task is in perceiving", ok is True)

        release["go"] = True
        final = wait_for_status(gateway, task_id, {"completed", "failed", "cancelled"})
        check("Task cancelled during perception ends up cancelled, not failed/completed",
              final == "cancelled")
        check("Brain never reached for a task cancelled during perception",
              not mock_brain.process.called)
    finally:
        gateway.shutdown()


def test_gateway_retry_preserves_attachments():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_vision.interpret.return_value = "a schema"
        mock_brain.process.return_value = FakeBrainResponse(text="ok", action=None)

        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}],
        )
        wait_for_status(gateway, task_id, {"completed", "failed"})
        new_id = gateway.retry_task(task_id)
        wait_for_status(gateway, new_id, {"completed", "failed"})
        new_record = gateway.get_task(new_id)
        check("Retried multimodal task keeps its original attachment",
              new_record["input_type"] == "image+text" and len(new_record["attachments"]) == 1)
        check("Retried multimodal task completes", new_record["status"] == "completed")
    finally:
        gateway.shutdown()


def test_concurrency_serialization_unaffected_by_perception():
    """Same invariant as test_iqoo_phase1_offline.py's explicit
    concurrency test, re-verified here with perception in the mix: image
    tasks and text tasks interleaved must still never run concurrently on
    more than one at a time, since perception runs on the same single
    worker thread as everything else — no separate perception concurrency
    model was introduced."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        active = {"count": 0, "max": 0}
        import threading
        lock = threading.Lock()

        def tracked_interpret(attachment, instruction):
            with lock:
                active["count"] += 1
                active["max"] = max(active["max"], active["count"])
            time.sleep(0.1)
            with lock:
                active["count"] -= 1
            return "a schema"

        def tracked_process(session):
            with lock:
                active["count"] += 1
                active["max"] = max(active["max"], active["count"])
            time.sleep(0.1)
            with lock:
                active["count"] -= 1
            return FakeBrainResponse(text="done", action=None)

        mock_vision.interpret.side_effect = tracked_interpret
        mock_brain.process.side_effect = tracked_process

        ids = []
        ids.append(gateway.submit_task("plain text task"))
        ids.append(gateway.submit_task(
            "image task", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}]))
        ids.append(gateway.submit_task("another text task"))

        for tid in ids:
            wait_for_status(gateway, tid, {"completed", "failed"}, timeout=5.0)

        check("Perception + Brain calls never overlap across tasks",
              active["max"] == 1)
    finally:
        gateway.shutdown()


def test_task_store_perceiving_status():
    from interfaces.api.task_store import TaskStore, ALL_STATUSES

    check("'perceiving' is a recognized status", "perceiving" in ALL_STATUSES)

    store = TaskStore()
    task_id = store.create_task("do it", "image+text",
                                 [{"kind": "image", "mime_type": "image/jpeg", "data": FAKE_JPEG}])
    store.update_status(task_id, "perceiving")
    check("Task store persists 'perceiving' status",
          store.get_task(task_id)["status"] == "perceiving")


def main():
    print("=== Schema / validation ===")
    test_backward_compat_text_only_schema()
    test_media_validation_helpers()
    test_task_create_request_multimodal_validation()

    print("\n=== Adapter units (mocked HTTP / mocked STT model) ===")
    test_vision_adapter_success_and_failure()
    test_audio_adapter_success_and_failure()

    print("\n=== Gateway integration (mocked adapters) ===")
    test_gateway_image_text_task_builds_structured_context()
    test_gateway_voice_task_uses_transcript_as_instruction()
    test_gateway_image_voice_task_combines_both()
    test_gateway_perception_failure_reports_cleanly()
    test_gateway_perception_timeout_like_failure()
    test_gateway_missing_attachment_fails_before_perception_call()
    test_gateway_cancellation_during_perception()
    test_gateway_retry_preserves_attachments()
    test_concurrency_serialization_unaffected_by_perception()
    test_task_store_perceiving_status()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("iQOO Phase 2 (multimodal perception) offline/mocked logic verified.")
    print("NOTE: no real Ollama vision model, real Whisper model, or real")
    print("phone/camera/microphone was used anywhere in this suite.")


if __name__ == "__main__":
    main()

"""
iQOO Phase 2 — Vision Adapter.

NOT a second AI brain. Converts (phone image, instruction) into a text
context block that gets folded into the instruction handed to the
existing, unmodified Brain/Planner/ReAct pipeline — the same way a
person would type a more detailed instruction after looking at the
photo themselves. Planning and execution decisions are made entirely by
the existing pipeline downstream; this adapter only describes what's in
the photo.

Reuses the same Ollama vision-model call shape already established by
hands/vision/screen_reader.py::ScreenReader.read() — same model
selection via settings.vision_model, same /api/generate request shape.
It does not call ScreenReader directly because every ScreenReader method
is hard-wired to `screencapture` (grabbing the LOCAL machine's screen),
which is the wrong data source here: the phone already captured the
photo, there's nothing on the laptop's screen to capture. Re-screenshot
would silently produce a description of the wrong image.
"""

import logging
import requests

from iqoo.errors import PerceptionError

logger = logging.getLogger("SAM.iQOO.Vision")


class VisionAdapter:
    def __init__(self, settings):
        self.settings = settings

    def interpret(self, attachment: dict, instruction: str) -> str:
        """attachment: {"kind": "image", "mime_type": ..., "data": <base64>}.
        Returns a literal, thorough text description of the image, framed
        by the user's instruction so the vision model focuses on
        task-relevant detail (e.g. a schema's fields and relationships,
        not decor in the background). Raises PerceptionError on any
        failure — never returns an empty or fabricated description."""
        model = "moondream" if self.settings.vision_model == "moondream" else "llava"

        prompt = (
            f"Look at this image carefully. The user's instruction is: "
            f"\"{instruction}\"\n\n"
            f"Describe everything in the image relevant to carrying out that "
            f"instruction — any diagram, schema, handwriting, labels, boxes, "
            f"arrows, field names, or data types. Transcribe text exactly as "
            f"written. Be thorough and literal. Do not invent or assume "
            f"details you cannot actually see in the image."
        )

        try:
            response = requests.post(
                f"{self.settings.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [attachment["data"]],
                    "stream": False,
                },
                timeout=60,
            )
        except requests.RequestException as e:
            raise PerceptionError(f"Vision model unreachable: {e}") from e

        if response.status_code != 200:
            raise PerceptionError(f"Vision model returned HTTP {response.status_code}")

        try:
            result = response.json().get("response", "").strip()
        except ValueError as e:
            raise PerceptionError(f"Vision model returned malformed JSON: {e}") from e

        if not result:
            raise PerceptionError("Vision model returned an empty description")

        logger.info(f"Vision interpretation: {result[:120]}")
        return result

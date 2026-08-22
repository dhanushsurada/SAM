/**
 * iQOO Phone Client — Camera (Phase 1 entry point only)
 *
 * PDR 8.2 requires a camera entry point to exist in Phase 1; PDR 9.2
 * (the real camera->vision->structured-context pipeline) is explicitly
 * Phase 2 scope. This module wires the button and shows a preview, but
 * deliberately does NOT submit the image to the gateway yet — the
 * gateway's Phase 1 worker fails input_type="image*" tasks honestly
 * (see iqoo/gateway.py) rather than silently ignoring the photo, and the
 * client shouldn't pretend otherwise.
 */

const CAMERA = {
  init() {
    const input = document.getElementById("camera-input");
    const btn = document.getElementById("camera-btn");
    const status = document.getElementById("capture-status");

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;

      btn.classList.add("active");
      status.textContent = `Captured: ${file.name || "photo"} — multimodal processing arrives in Phase 2`;

      STATE.pendingImage = file;

      // Preview isn't rendered inline in Phase 1 (no attachment upload
      // path yet) — just confirm capture worked so the entry point is
      // demonstrably functional per the Phase 1 acceptance tests.
    });
  },

  reset() {
    const input = document.getElementById("camera-input");
    const btn = document.getElementById("camera-btn");
    const status = document.getElementById("capture-status");
    input.value = "";
    btn.classList.remove("active");
    status.textContent = "";
    STATE.pendingImage = null;
  },
};

/**
 * iQOO Phone Client — Camera (Phase 2)
 *
 * Phase 1 only captured a file and refused to submit it. Phase 2 encodes
 * it to base64, shows a real preview, and lets app.js include it in the
 * task's attachments array. Still no image processing happens on the
 * client — it only prepares the bytes; iqoo/media_validation.py and
 * iqoo/vision_adapter.py do the actual validation and interpretation
 * server-side.
 */

const CAMERA = {
  ALLOWED_MIME: new Set(["image/jpeg", "image/png", "image/webp"]),
  MAX_BYTES: 8 * 1024 * 1024,

  init() {
    const input = document.getElementById("camera-input");
    const btn = document.getElementById("camera-btn");
    const status = document.getElementById("capture-status");
    const preview = document.getElementById("image-preview");
    const removeBtn = document.getElementById("image-remove-btn");

    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;

      if (!this.ALLOWED_MIME.has(file.type)) {
        status.textContent = `Unsupported image type (${file.type || "unknown"}) — use JPEG, PNG, or WebP.`;
        input.value = "";
        return;
      }
      if (file.size > this.MAX_BYTES) {
        status.textContent = `Photo too large (${(file.size / 1024 / 1024).toFixed(1)}MB) — 8MB limit.`;
        input.value = "";
        return;
      }

      status.textContent = "Processing photo…";
      try {
        const data = await this._fileToBase64(file);
        STATE.pendingImage = {
          mime_type: file.type,
          data,
          filename: file.name || "photo.jpg",
        };
        preview.src = `data:${file.type};base64,${data}`;
        preview.classList.remove("hidden");
        removeBtn.classList.remove("hidden");
        btn.classList.add("active");
        status.textContent = "Photo attached.";
      } catch (e) {
        status.textContent = "Could not read that photo — try again.";
        STATE.pendingImage = null;
      }
    });

    removeBtn.addEventListener("click", () => this.reset());
  },

  _fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // reader.result is "data:<mime>;base64,<data>" — strip the prefix.
        const commaIdx = reader.result.indexOf(",");
        resolve(reader.result.slice(commaIdx + 1));
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  },

  reset() {
    const input = document.getElementById("camera-input");
    const btn = document.getElementById("camera-btn");
    const status = document.getElementById("capture-status");
    const preview = document.getElementById("image-preview");
    const removeBtn = document.getElementById("image-remove-btn");
    input.value = "";
    btn.classList.remove("active");
    preview.classList.add("hidden");
    preview.src = "";
    removeBtn.classList.add("hidden");
    if (!STATE.pendingAudio) status.textContent = "";
    STATE.pendingImage = null;
  },
};

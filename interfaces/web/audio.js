/**
 * iQOO Phone Client — Audio Recording (Phase 2)
 *
 * Distinct from voice.js: voice.js is browser SpeechRecognition
 * dictation INTO the text box (client-side, instant, no server
 * round-trip). This module records a real audio file with
 * MediaRecorder and attaches it to the task so SAM's own server-side
 * Whisper pipeline (multimodal/audio/adapter.py) transcribes it — the actual
 * PDR 9.4 flow. The long-press-to-record button and the dictation
 * button are separate controls; the UI clarifies which is which via
 * their icons/labels in index.html.
 */

const AUDIO_REC = {
  ALLOWED_MIME: ["audio/webm", "audio/ogg", "audio/mp4"],
  MAX_BYTES: 15 * 1024 * 1024,

  _recorder: null,
  _chunks: [],
  _mimeType: null,
  _startedAt: 0,

  init() {
    const btn = document.getElementById("record-btn");
    const status = document.getElementById("capture-status");
    const removeBtn = document.getElementById("audio-remove-btn");
    const indicator = document.getElementById("recording-indicator");

    if (!navigator.mediaDevices || !window.MediaRecorder) {
      btn.addEventListener("click", () => {
        status.textContent = "Audio recording not supported in this browser.";
      });
      return;
    }

    btn.addEventListener("click", async () => {
      if (this._recorder && this._recorder.state === "recording") {
        this._recorder.stop();
        return;
      }
      await this._startRecording(btn, status, indicator);
    });

    removeBtn.addEventListener("click", () => this.reset());
  },

  async _startRecording(btn, status, indicator) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = this.ALLOWED_MIME.find((m) => MediaRecorder.isTypeSupported(m)) || "";
      this._mimeType = mimeType || "audio/webm";
      this._recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      this._chunks = [];
      this._startedAt = Date.now();

      this._recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this._chunks.push(e.data);
      };

      this._recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        indicator.classList.add("hidden");
        btn.classList.remove("active");
        this._finalizeRecording(status);
      };

      this._recorder.start();
      btn.classList.add("active");
      indicator.classList.remove("hidden");
      status.textContent = "Recording… tap again to stop.";
    } catch (e) {
      status.textContent = "Microphone access denied or unavailable.";
    }
  },

  async _finalizeRecording(status) {
    const blob = new Blob(this._chunks, { type: this._mimeType });
    const durationSec = (Date.now() - this._startedAt) / 1000;

    if (blob.size === 0) {
      status.textContent = "No audio captured — try again.";
      return;
    }
    if (blob.size > this.MAX_BYTES) {
      status.textContent = `Recording too large (${(blob.size / 1024 / 1024).toFixed(1)}MB) — 15MB limit.`;
      return;
    }

    try {
      const data = await this._blobToBase64(blob);
      STATE.pendingAudio = {
        mime_type: this._mimeType,
        data,
        filename: "voice_note",
        durationSec,
      };
      document.getElementById("audio-remove-btn").classList.remove("hidden");
      status.textContent = `Voice note recorded (${durationSec.toFixed(1)}s).`;
    } catch (e) {
      status.textContent = "Could not process the recording — try again.";
    }
  },

  _blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const commaIdx = reader.result.indexOf(",");
        resolve(reader.result.slice(commaIdx + 1));
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  },

  reset() {
    const status = document.getElementById("capture-status");
    const removeBtn = document.getElementById("audio-remove-btn");
    const btn = document.getElementById("record-btn");
    const indicator = document.getElementById("recording-indicator");
    if (this._recorder && this._recorder.state === "recording") {
      this._recorder.stop();
    }
    btn.classList.remove("active");
    indicator.classList.add("hidden");
    removeBtn.classList.add("hidden");
    if (!STATE.pendingImage) status.textContent = "";
    STATE.pendingAudio = null;
  },
};

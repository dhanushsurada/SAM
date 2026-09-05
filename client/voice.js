/**
 * iQOO Phone Client — Voice (Phase 1 entry point)
 *
 * Uses the browser's built-in SpeechRecognition (Web Speech API) where
 * available — free, no dependency, works on most mobile Chrome/Safari
 * builds — to fill the text box. This is genuinely functional in Phase
 * 1, not just a stub, but it's push-to-talk browser dictation, not
 * SAM's own Whisper STT pipeline; per PDR 9.4, real phone-mic ->
 * server-side STT is Phase 2 scope. If the API is unavailable, this
 * fails safely to the text fallback (PDR 9.4 requirement) with a clear
 * message instead of a silently dead button.
 */

const VOICE = {
  _recognition: null,
  _listening: false,

  init() {
    const btn = document.getElementById("voice-btn");
    const status = document.getElementById("capture-status");
    const textarea = document.getElementById("instruction");

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      btn.addEventListener("click", () => {
        status.textContent = "Voice input not supported in this browser — use text instead.";
      });
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    this._recognition = recognition;

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      textarea.value = textarea.value ? `${textarea.value} ${transcript}` : transcript;
      status.textContent = "Voice captured.";
    };

    recognition.onerror = (event) => {
      status.textContent = `Voice input failed (${event.error}) — use text instead.`;
      this._setListening(false, btn);
    };

    recognition.onend = () => this._setListening(false, btn);

    btn.addEventListener("click", () => {
      if (this._listening) {
        recognition.stop();
        return;
      }
      status.textContent = "Listening…";
      this._setListening(true, btn);
      try {
        recognition.start();
      } catch (e) {
        // start() throws if called twice in quick succession — harmless
        status.textContent = "Try again.";
        this._setListening(false, btn);
      }
    });
  },

  _setListening(on, btn) {
    this._listening = on;
    btn.classList.toggle("active", on);
  },
};

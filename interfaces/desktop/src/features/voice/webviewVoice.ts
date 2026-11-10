/**
 * The web view's own speech synthesis (window.speechSynthesis), used only as
 * a fallback when SAM's voice (Kokoro/Piper, via POST /api/speech) can't
 * return audio: nothing installed yet, or tts_engine set to "system". It is
 * the operating system's voice, not SAM's, which is why it is the fallback
 * and not the default.
 */

export interface UtteranceLike {
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
}

export interface SynthLike {
  speak(utterance: UtteranceLike): void;
  cancel(): void;
}

/** Returns a speak function, or undefined when this web view has no speech
 * synthesis at all. The returned promise resolves when speech ends or is
 * aborted, and rejects only on a real synthesis error. */
export function createWebviewVoice(
  synth: SynthLike | undefined,
  makeUtterance: ((text: string) => UtteranceLike) | undefined,
): ((text: string, signal: AbortSignal) => Promise<void>) | undefined {
  if (!synth || !makeUtterance) return undefined;
  return (text, signal) =>
    new Promise<void>((resolve, reject) => {
      if (signal.aborted) return resolve();
      const utterance = makeUtterance(text);
      const onAbort = () => {
        try {
          synth.cancel();
        } catch {
          // Nothing speaking.
        }
        resolve();
      };
      signal.addEventListener("abort", onAbort, { once: true });
      utterance.onend = () => {
        signal.removeEventListener("abort", onAbort);
        resolve();
      };
      utterance.onerror = (event) => {
        signal.removeEventListener("abort", onAbort);
        // cancel() reports "canceled"/"interrupted": that is a stop, not a failure.
        if (event.error === "canceled" || event.error === "interrupted") return resolve();
        reject(new Error(`Speech synthesis failed: ${event.error ?? "unknown error"}`));
      };
      synth.speak(utterance);
    });
}

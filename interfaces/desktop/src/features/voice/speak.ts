/**
 * Say one reply out loud, choosing the voice. SAM's own voice comes first
 * (POST /api/speech returns audio rendered by Kokoro or Piper). When the
 * server says it can't, this falls back to the web view's voice; when the
 * user turned speech off, it stays silent. A failure to speak never fails
 * the conversation: the reply is already on screen.
 *
 * Statuses from the endpoint (interfaces/api/server.py render_speech):
 *   409 speech is turned off    -> silent
 *   422 nothing to say          -> silent
 *   501 no engine can return audio, or any other failure -> web view voice
 */

export type SpeakOutcome =
  | "played" // SAM's own voice
  | "fallback" // the web view's voice
  | "silent" // speech is off, or nothing to say
  | "stopped" // the user stopped it
  | "unavailable"; // nothing could speak

export interface SpeakResult {
  outcome: SpeakOutcome;
  /** Something worth telling the user, shown quietly (not an error). */
  notice?: string;
}

export interface SpeakDeps {
  synthesize(text: string, signal: AbortSignal): Promise<ArrayBuffer>;
  play(data: ArrayBuffer): Promise<void>;
  /** The web view's own voice; undefined when it has none. */
  webviewSpeak?: (text: string, signal: AbortSignal) => Promise<void>;
  /** Audio is about to be heard (ends the "preparing" wait). */
  onAudioStart?: () => void;
  /** Words for the notices; injected so this module stays text-free. */
  notices?: { fallback?: string; unavailable?: string };
}

function statusOf(error: unknown): number | undefined {
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status: unknown }).status;
    return typeof status === "number" ? status : undefined;
  }
  return undefined;
}

export async function speakReply(text: string, deps: SpeakDeps, signal: AbortSignal): Promise<SpeakResult> {
  try {
    const audio = await deps.synthesize(text, signal);
    if (signal.aborted) return { outcome: "stopped" };
    deps.onAudioStart?.();
    await deps.play(audio);
    return { outcome: signal.aborted ? "stopped" : "played" };
  } catch (error) {
    if (signal.aborted) return { outcome: "stopped" }; // the user's Stop, not a failure
    const status = statusOf(error);
    if (status === 409 || status === 422) return { outcome: "silent" };
    return speakInWebview(text, deps, signal, status === 501);
  }
}

async function speakInWebview(
  text: string,
  deps: SpeakDeps,
  signal: AbortSignal,
  engineMissing: boolean,
): Promise<SpeakResult> {
  const unavailable: SpeakResult = { outcome: "unavailable", notice: deps.notices?.unavailable };
  if (!deps.webviewSpeak) return unavailable;
  try {
    deps.onAudioStart?.();
    await deps.webviewSpeak(text, signal);
    if (signal.aborted) return { outcome: "stopped" };
    return { outcome: "fallback", notice: engineMissing ? deps.notices?.fallback : undefined };
  } catch {
    return signal.aborted ? { outcome: "stopped" } : unavailable;
  }
}

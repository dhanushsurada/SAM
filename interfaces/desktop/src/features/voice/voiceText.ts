/**
 * The words the voice controls show, kept apart from the components so they
 * can be tested. Each line says what is happening now and, when it matters,
 * what the user can do about it.
 */

import type { VoiceState } from "./voiceMachine.ts";

export interface StatusContext {
  /** Phase of the running voice task ("perceiving", "planning", …). */
  phase?: string | null;
  /** The running task's latest progress message. */
  taskMessage?: string | null;
  /** The current step has been taking long enough that the first-use
   * download is the likely reason. */
  slow?: boolean;
}

export function statusText(state: VoiceState, ctx: StatusContext = {}): string {
  switch (state.kind) {
    case "idle":
      return "";
    case "starting":
      return "Opening the microphone… allow access if asked.";
    case "listening":
      return "Listening… click the mic again to send. Esc cancels.";
    case "sending":
      return "Sending your voice message…";
    case "working":
      if (ctx.phase === "perceiving") {
        return ctx.slow
          ? "Still transcribing… the first time, SAM downloads its speech model, which can take a few minutes."
          : "Transcribing your voice…";
      }
      return ctx.taskMessage || "Working on it…";
    case "speaking":
      if (state.preparing) {
        return ctx.slow
          ? "Still preparing SAM's voice… the first time, SAM downloads its voice model, which can take a few minutes."
          : "Preparing SAM's voice…";
      }
      return "Speaking… click Stop to silence SAM.";
    case "error":
      return state.message;
  }
}

/** The mic button's accessible name: what pressing it does right now. */
export function micLabel(state: VoiceState): string {
  switch (state.kind) {
    case "idle":
      return "Talk to SAM";
    case "error":
      return "Try again";
    case "starting":
      return "Cancel";
    case "listening":
      return "Send voice message";
    case "sending":
    case "working":
      return "Stop";
    case "speaking":
      return "Stop speaking";
  }
}

/** One or two words for the always-visible indicator: the state, not the
 * instructions (statusText has those). */
export function shortStatus(state: VoiceState): string {
  switch (state.kind) {
    case "idle":
      return "";
    case "starting":
      return "Opening mic";
    case "listening":
      return "Listening";
    case "sending":
      return "Sending";
    case "working":
      return "Working";
    case "speaking":
      return state.preparing ? "Preparing voice" : "Speaking";
    case "error":
      return "Voice problem";
  }
}

/** Shown while the mic cannot be used at all. */
export const SPEECH_INPUT_MISSING =
  "Voice input needs SAM's speech-to-text engine. Open Diagnostics and install “speech-input”.";
export const NO_MICROPHONE_API = "This app's web view can't use the microphone.";
export const NO_RECORDER_API = "This app's web view can't record audio.";
/** Shown when SAM's own voice couldn't speak. It does not claim the voice is
 * missing: it may be installed but failed (a first-use model download that
 * had no network), which SAM retries on its own after a minute. */
export const FALLBACK_VOICE_NOTICE =
  "Using this device's local voice because SAM's own voice isn't available right now. If it isn't installed, add “speech-output” in Diagnostics.";
export const NO_VOICE_NOTICE = "SAM couldn't speak this reply (no voice is available here). It is on screen.";

/** The recording was made but could not be sent, or turned into data to send. */
export const SEND_FAILED = "Couldn't send your voice message. Check that SAM is running, then try again.";
export const READ_FAILED = "Couldn't read the recording. Try again.";

/** What the web view offers for voice input; see micUnavailableReason. */
export interface VoiceEnvironment {
  hasMicrophoneApi: boolean;
  hasRecorderApi: boolean;
}

/** Why the mic button can't be used at all right now, or null when it can.
 * `whisperAvailable` is the gateway's own report (health.whisper_available);
 * null means it hasn't said, which does not block: if the gateway is down,
 * sending the message says so. */
export function micUnavailableReason(env: VoiceEnvironment, whisperAvailable: boolean | null): string | null {
  if (!env.hasMicrophoneApi) return NO_MICROPHONE_API;
  if (!env.hasRecorderApi) return NO_RECORDER_API;
  if (whisperAvailable === false) return SPEECH_INPUT_MISSING;
  return null;
}

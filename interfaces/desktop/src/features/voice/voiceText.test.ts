import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FALLBACK_VOICE_NOTICE,
  micLabel,
  micUnavailableReason,
  NO_MICROPHONE_API,
  NO_RECORDER_API,
  shortStatus,
  SPEECH_INPUT_MISSING,
  statusText,
} from "./voiceText.ts";
import type { VoiceState } from "./voiceMachine.ts";

test("idle shows no status line", () => {
  assert.equal(statusText({ kind: "idle" }), "");
});

test("each state says what is happening and what the user can do", () => {
  assert.match(statusText({ kind: "starting" }), /microphone/i);
  assert.match(statusText({ kind: "listening" }), /click the mic again to send/i);
  assert.match(statusText({ kind: "listening" }), /Esc/);
  assert.match(statusText({ kind: "sending" }), /sending/i);
  assert.match(statusText({ kind: "speaking", taskId: "t", preparing: false }), /Stop/);
});

test("a voice task still transcribing says so, and explains a long wait as the first-use download", () => {
  const working: VoiceState = { kind: "working", taskId: "t" };
  assert.equal(statusText(working, { phase: "perceiving" }), "Transcribing your voice…");
  const slow = statusText(working, { phase: "perceiving", slow: true });
  assert.match(slow, /first time/i);
  assert.match(slow, /speech model/i);
});

test("once past transcription the task's own progress message is shown", () => {
  const working: VoiceState = { kind: "working", taskId: "t" };
  assert.equal(statusText(working, { phase: "planning", taskMessage: "Planning the steps" }), "Planning the steps");
  assert.equal(statusText(working, { phase: "planning" }), "Working on it…");
  assert.equal(statusText(working, { phase: "planning", taskMessage: "Executing", slow: true }), "Executing");
});

test("while SAM's voice is being prepared, a long wait is explained as the first-use download", () => {
  const preparing: VoiceState = { kind: "speaking", taskId: "t", preparing: true };
  assert.equal(statusText(preparing), "Preparing SAM's voice…");
  assert.match(statusText(preparing, { slow: true }), /voice model/i);
});

test("an error shows its message", () => {
  assert.equal(statusText({ kind: "error", message: "No microphone was found." }), "No microphone was found.");
});

test("the mic button is named for what pressing it does", () => {
  const labels = [
    micLabel({ kind: "idle" }),
    micLabel({ kind: "error", message: "x" }),
    micLabel({ kind: "starting" }),
    micLabel({ kind: "listening" }),
    micLabel({ kind: "sending" }),
    micLabel({ kind: "working", taskId: "t" }),
    micLabel({ kind: "speaking", taskId: "t", preparing: false }),
  ];
  assert.deepEqual(labels, [
    "Talk to SAM",
    "Try again",
    "Cancel",
    "Send voice message",
    "Stop",
    "Stop",
    "Stop speaking",
  ]);
});

test("the mic is unavailable for the first thing that is missing, and says what", () => {
  const full = { hasMicrophoneApi: true, hasRecorderApi: true };
  assert.equal(micUnavailableReason(full, true), null);
  assert.equal(micUnavailableReason({ ...full, hasMicrophoneApi: false }, true), NO_MICROPHONE_API);
  assert.equal(micUnavailableReason({ ...full, hasRecorderApi: false }, true), NO_RECORDER_API);
  assert.equal(micUnavailableReason(full, false), SPEECH_INPUT_MISSING);
  // the web view's limits come first: installing speech-to-text would not help
  assert.equal(micUnavailableReason({ hasMicrophoneApi: false, hasRecorderApi: false }, false), NO_MICROPHONE_API);
});

test("until the gateway reports on speech-to-text, the mic is not blocked", () => {
  assert.equal(micUnavailableReason({ hasMicrophoneApi: true, hasRecorderApi: true }, null), null);
});

test("the local fallback-voice notice says what is used and how to get SAM's voice", () => {
  // SAM's voice can be installed and still fail (a first-use download with no
  // network); telling that user to "install" it would be wrong.
  assert.match(FALLBACK_VOICE_NOTICE, /^Using this device's local voice/);
  assert.match(FALLBACK_VOICE_NOTICE, /isn't available right now/);
  assert.match(FALLBACK_VOICE_NOTICE, /If it isn't installed, add “speech-output” in Diagnostics\.$/);
});

test("the always-visible indicator names the state in a word or two, and is empty when idle", () => {
  assert.deepEqual(
    [
      shortStatus({ kind: "idle" }),
      shortStatus({ kind: "starting" }),
      shortStatus({ kind: "listening" }),
      shortStatus({ kind: "sending" }),
      shortStatus({ kind: "working", taskId: "t" }),
      shortStatus({ kind: "speaking", taskId: "t", preparing: true }),
      shortStatus({ kind: "speaking", taskId: "t", preparing: false }),
      shortStatus({ kind: "error", message: "x" }),
    ],
    ["", "Opening mic", "Listening", "Sending", "Working", "Preparing voice", "Speaking", "Voice problem"],
  );
});

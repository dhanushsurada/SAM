import { test } from "node:test";
import assert from "node:assert/strict";
import { IDLE, isBusy, isCapturing, shouldStopOnQuickAssistantEscape, voiceReducer } from "./voiceMachine.ts";
import type { VoiceEvent, VoiceState } from "./voiceMachine.ts";

const WORKING: VoiceState = { kind: "working", taskId: "t1" };
const SPEAKING: VoiceState = { kind: "speaking", taskId: "t1", preparing: true };
const ERROR: VoiceState = { kind: "error", message: "boom" };

const EVERY_STATE: Record<string, VoiceState> = {
  idle: IDLE,
  starting: { kind: "starting" },
  listening: { kind: "listening" },
  sending: { kind: "sending" },
  working: WORKING,
  speaking: SPEAKING,
  error: ERROR,
};

test("a whole conversation: talk, work, speak, back to idle", () => {
  let state: VoiceState = IDLE;
  const step = (event: VoiceEvent, expected: VoiceState) => {
    state = voiceReducer(state, event);
    assert.deepEqual(state, expected, `after ${event.type}`);
  };
  step({ type: "PRESS" }, { kind: "starting" });
  step({ type: "STARTED" }, { kind: "listening" });
  step({ type: "PRESS" }, { kind: "sending" });
  step({ type: "SUBMITTED", taskId: "t1" }, WORKING);
  step({ type: "TASK_FINISHED", taskId: "t1", speak: true }, SPEAKING);
  step({ type: "AUDIO_STARTED" }, { kind: "speaking", taskId: "t1", preparing: false });
  step({ type: "SPEECH_ENDED" }, IDLE);
});

test("a task with nothing to say (or speech off) goes straight back to idle", () => {
  assert.deepEqual(voiceReducer(WORKING, { type: "TASK_FINISHED", taskId: "t1", speak: false }), IDLE);
});

test("a finish for a different task is ignored", () => {
  const next = voiceReducer(WORKING, { type: "TASK_FINISHED", taskId: "older-task", speak: true });
  assert.equal(next, WORKING);
  assert.equal(voiceReducer(IDLE, { type: "TASK_FINISHED", taskId: "t1", speak: true }), IDLE);
});

test("pressing the mic again while the microphone is opening cancels, and a late STARTED is then ignored", () => {
  const cancelled = voiceReducer({ kind: "starting" }, { type: "PRESS" });
  assert.deepEqual(cancelled, IDLE);
  assert.equal(voiceReducer(cancelled, { type: "STARTED" }), cancelled);
  assert.equal(voiceReducer(cancelled, { type: "START_FAILED", message: "late" }), cancelled);
});

test("the recorder stopping by itself moves listening to sending, and is harmless once the user already sent", () => {
  assert.deepEqual(voiceReducer({ kind: "listening" }, { type: "RECORDING_ENDED" }), { kind: "sending" });
  const sending: VoiceState = { kind: "sending" };
  assert.equal(voiceReducer(sending, { type: "RECORDING_ENDED" }), sending);
});

test("the mic button does nothing while sending, working or speaking: Stop is the way out", () => {
  for (const name of ["sending", "working", "speaking"]) {
    const state = EVERY_STATE[name];
    assert.equal(voiceReducer(state, { type: "PRESS" }), state, name);
  }
});

test("STOP leaves every state for idle", () => {
  for (const [name, state] of Object.entries(EVERY_STATE)) {
    assert.deepEqual(voiceReducer(state, { type: "STOP" }), IDLE, name);
  }
  assert.equal(voiceReducer(IDLE, { type: "STOP" }), IDLE);
});

test("failures become an error, and pressing the mic retries", () => {
  assert.deepEqual(voiceReducer({ kind: "starting" }, { type: "START_FAILED", message: "no mic" }), {
    kind: "error",
    message: "no mic",
  });
  for (const from of ["listening", "sending"]) {
    assert.deepEqual(voiceReducer(EVERY_STATE[from], { type: "RECORDING_FAILED", message: "empty" }), {
      kind: "error",
      message: "empty",
    });
  }
  assert.deepEqual(voiceReducer({ kind: "sending" }, { type: "SUBMIT_FAILED", message: "rejected" }), {
    kind: "error",
    message: "rejected",
  });
  assert.deepEqual(voiceReducer(ERROR, { type: "PRESS" }), { kind: "starting" });
  assert.deepEqual(voiceReducer(ERROR, { type: "DISMISS" }), IDLE);
});

test("failures and dismissals that arrive in the wrong state change nothing", () => {
  assert.equal(voiceReducer(IDLE, { type: "SUBMIT_FAILED", message: "x" }), IDLE);
  assert.equal(voiceReducer(WORKING, { type: "SUBMIT_FAILED", message: "x" }), WORKING);
  assert.equal(voiceReducer(EVERY_STATE.listening, { type: "START_FAILED", message: "x" }), EVERY_STATE.listening);
  assert.equal(voiceReducer(WORKING, { type: "RECORDING_FAILED", message: "x" }), WORKING);
  assert.equal(voiceReducer(WORKING, { type: "DISMISS" }), WORKING);
  assert.equal(voiceReducer(IDLE, { type: "SUBMITTED", taskId: "t9" }), IDLE);
});

test("audio and speech events only matter while speaking", () => {
  const playing: VoiceState = { kind: "speaking", taskId: "t1", preparing: false };
  assert.equal(voiceReducer(playing, { type: "AUDIO_STARTED" }), playing);
  assert.equal(voiceReducer(IDLE, { type: "SPEECH_ENDED" }), IDLE);
  // a stale end of an old reply, arriving in the middle of a new conversation
  for (const name of ["starting", "listening", "sending", "working", "error"]) {
    assert.equal(voiceReducer(EVERY_STATE[name], { type: "SPEECH_ENDED" }), EVERY_STATE[name], name);
    assert.equal(voiceReducer(EVERY_STATE[name], { type: "AUDIO_STARTED" }), EVERY_STATE[name], name);
  }
  assert.equal(voiceReducer(WORKING, { type: "AUDIO_STARTED" }), WORKING);
  assert.deepEqual(voiceReducer(playing, { type: "SPEECH_ENDED" }), IDLE);
});

test("isCapturing is true only while the microphone is open or opening", () => {
  const capturing = Object.entries(EVERY_STATE).filter(([, state]) => isCapturing(state)).map(([name]) => name);
  assert.deepEqual(capturing, ["starting", "listening"]);
});

test("isBusy is true for everything Stop would end, and false for idle and error", () => {
  const busy = Object.entries(EVERY_STATE).filter(([, state]) => isBusy(state)).map(([name]) => name);
  assert.deepEqual(busy, ["starting", "listening", "sending", "working", "speaking"]);
});

test("Quick Assistant Escape stops capture and speech but preserves an accepted task", () => {
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.starting), true);
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.listening), true);
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.sending), true);
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.speaking), true);
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.working), false);
  assert.equal(shouldStopOnQuickAssistantEscape(EVERY_STATE.idle), false);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { createVoiceController } from "./voiceController.ts";
import type { VoiceControllerDeps, VoiceTaskRequest } from "./voiceController.ts";
import { RecordingCancelled, RecordingError } from "./recorder.ts";
import type { Recording, RecordingResult } from "./recorder.ts";
import type { SpeakResult } from "./speak.ts";
import type { VoiceState } from "./voiceMachine.ts";
import { READ_FAILED, SEND_FAILED } from "./voiceText.ts";
import { VOICE_PLACEHOLDER } from "./taskLabel.ts";

// ─── a controllable world ────────────────────────────────────────────────

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

class FakeRecording implements Recording {
  finished: Promise<RecordingResult>;
  private done = deferred<RecordingResult>();
  stops = 0;
  cancels = 0;
  constructor() {
    this.finished = this.done.promise;
  }
  stop() {
    this.stops++;
  }
  cancel() {
    this.cancels++;
    this.done.reject(new RecordingCancelled());
  }
  /** The recorder delivers its audio. */
  deliver(mimeType = "audio/webm") {
    this.done.resolve({ blob: new Blob([new Uint8Array(3000)], { type: mimeType }), mimeType, durationMs: 1800 });
  }
  fail(message: string) {
    this.done.reject(new RecordingError(message));
  }
}

interface SpeakCall {
  text: string;
  signal: AbortSignal;
  audioStarts(): void;
  finish(result?: SpeakResult): void;
  fail(error: unknown): void;
}

function world(options: {
  encode?: VoiceControllerDeps["encode"];
  submit?: VoiceControllerDeps["submit"];
  unlockAudio?: VoiceControllerDeps["unlockAudio"];
} = {}) {
  const recordings: FakeRecording[] = [];
  const startGate: { current: ReturnType<typeof deferred<void>> | null } = { current: null };
  const startSignals: AbortSignal[] = [];
  const submitted: VoiceTaskRequest[] = [];
  const cancelledTasks: string[] = [];
  const speakCalls: SpeakCall[] = [];
  const notices: string[] = [];
  const audio = { unlocks: 0, stops: 0 };
  let startFailure: Error | null = null;
  const submitGate: { current: ReturnType<typeof deferred<string | null>> | null } = { current: null };

  const deps: VoiceControllerDeps = {
    async startRecording(signal) {
      startSignals.push(signal);
      if (startGate.current) await startGate.current.promise;
      if (startFailure) throw startFailure;
      const recording = new FakeRecording();
      recordings.push(recording);
      return recording;
    },
    encode: options.encode ?? (async () => "BASE64"),
    submit:
      options.submit ??
      (async (request) => {
        submitted.push(request);
        if (submitGate.current) return submitGate.current.promise;
        return `task-${submitted.length}`;
      }),
    async cancelTask(taskId) {
      cancelledTasks.push(taskId);
    },
    speak(text, signal, onAudioStart) {
      const done = deferred<SpeakResult>();
      speakCalls.push({
        text,
        signal,
        audioStarts: onAudioStart,
        finish: (result = { outcome: "played" }) => done.resolve(result),
        fail: (error) => done.reject(error),
      });
      return done.promise;
    },
    unlockAudio: options.unlockAudio ?? (() => {
      audio.unlocks++;
    }),
    stopAudio: () => {
      audio.stops++;
    },
    onNotice: (text) => notices.push(text),
  };

  const controller = createVoiceController(deps);
  const seen: VoiceState[] = [];
  controller.subscribe(() => seen.push(controller.getState()));

  return {
    controller,
    recordings,
    startGate,
    startSignals,
    failNextStart(error: Error) {
      startFailure = error;
    },
    submitted,
    submitGate,
    cancelledTasks,
    speakCalls,
    notices,
    audio,
    seen,
    kinds: () => seen.map((state) => state.kind),
    state: () => controller.getState(),
  };
}

/** Press, let the microphone open, and arrive in "listening". */
async function listen(w: ReturnType<typeof world>) {
  w.controller.press();
  await flush();
  assert.equal(w.state().kind, "listening");
  return w.recordings[w.recordings.length - 1];
}

/** Talk, send, and arrive in "working" on task-1. */
async function sendMessage(w: ReturnType<typeof world>) {
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.deepEqual(w.state(), { kind: "working", taskId: "task-1" });
  return recording;
}

const completed = { task_id: "task-1", status: "completed", result_text: "It is 3 pm.", error: null };

// ─── the whole conversation ──────────────────────────────────────────────

test("talk, send, wait, hear the answer: every step, in order", async () => {
  const w = world();
  assert.equal(w.state().kind, "idle");

  w.controller.press();
  assert.equal(w.state().kind, "starting");
  await flush();
  assert.equal(w.state().kind, "listening");
  const recording = w.recordings[0];

  w.controller.press();
  assert.equal(w.state().kind, "sending");
  assert.equal(recording.stops, 1, "the recorder is told to stop and flush");
  recording.deliver("audio/webm");
  await flush();
  assert.deepEqual(w.state(), { kind: "working", taskId: "task-1" });

  assert.deepEqual(w.submitted, [
    {
      instruction: VOICE_PLACEHOLDER,
      input_type: "voice",
      attachments: [{ kind: "audio", mime_type: "audio/webm", data: "BASE64", filename: "voice-message" }],
    },
  ]);

  w.controller.taskFinished(completed, true);
  assert.deepEqual(w.state(), { kind: "speaking", taskId: "task-1", preparing: true });
  assert.equal(w.speakCalls.length, 1);
  assert.equal(w.speakCalls[0].text, "It is 3 pm.");

  w.speakCalls[0].audioStarts();
  assert.deepEqual(w.state(), { kind: "speaking", taskId: "task-1", preparing: false });

  w.speakCalls[0].finish();
  await flush();
  assert.equal(w.state().kind, "idle");
  assert.deepEqual(w.kinds(), ["starting", "listening", "sending", "working", "speaking", "speaking", "idle"]);
});

test("every press unlocks audio inside the click, before anything asynchronous", () => {
  const w = world();
  w.controller.press();
  assert.equal(w.audio.unlocks, 1);
  w.controller.press();
  assert.equal(w.audio.unlocks, 2);
});

test("subscribers hear about changes only, and can unsubscribe", async () => {
  const w = world();
  let calls = 0;
  const unsubscribe = w.controller.subscribe(() => calls++);
  w.controller.dismissError(); // nothing to dismiss: no change
  w.controller.stop(); // nothing to stop: no change
  assert.equal(calls, 0);
  w.controller.press();
  assert.equal(calls, 1);
  unsubscribe();
  await flush();
  assert.equal(calls, 1);
});

// ─── pressing Stop ───────────────────────────────────────────────────────

test("pressing again before the microphone has opened cancels, and the late microphone is released", async () => {
  const w = world();
  w.startGate.current = deferred<void>(); // the permission prompt is open
  w.controller.press();
  assert.equal(w.state().kind, "starting");
  w.controller.press();
  assert.equal(w.state().kind, "idle");
  assert.equal(w.startSignals[0].aborted, true, "the pending start is told to give up");

  w.startGate.current.resolve(); // ...and then the user clicks Allow
  await flush();
  assert.equal(w.state().kind, "idle");
  assert.equal(w.recordings[0].cancels, 1, "the recording that opened late is cancelled, releasing the microphone");
});

test("Esc or Stop while listening throws the recording away and sends nothing", async () => {
  const w = world();
  const recording = await listen(w);
  w.controller.stop();
  await flush();
  assert.equal(w.state().kind, "idle");
  assert.equal(recording.cancels, 1);
  assert.equal(w.submitted.length, 0);
  assert.equal(w.cancelledTasks.length, 0);
  assert.equal(w.audio.stops >= 1, true);
});

test("Stop while the message is being sent withdraws the task it creates", async () => {
  const w = world();
  w.submitGate.current = deferred<string | null>();
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.equal(w.state().kind, "sending");
  assert.equal(w.submitted.length, 1);

  w.controller.stop();
  assert.equal(w.state().kind, "idle");
  w.submitGate.current.resolve("task-1"); // the server answers after Stop
  await flush();
  assert.equal(w.state().kind, "idle", "a stale answer does not bring the state back");
  assert.deepEqual(w.cancelledTasks, ["task-1"], "SAM is told not to act on it");
});

test("Stop while still encoding sends nothing at all", async () => {
  const encoding = deferred<string>();
  const w = world({ encode: () => encoding.promise });
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.equal(w.state().kind, "sending");
  w.controller.stop();
  encoding.resolve("BASE64");
  await flush();
  assert.equal(w.submitted.length, 0);
  assert.equal(w.state().kind, "idle");
});

test("pressing the mic while SAM is sending, working or speaking is Stop", async () => {
  const w = world();
  w.submitGate.current = deferred<string | null>();
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.equal(w.state().kind, "sending");
  w.controller.press(); // Stop
  assert.equal(w.state().kind, "idle");
  w.submitGate.current.resolve("task-1");
  await flush();

  const w2 = world();
  await sendMessage(w2);
  w2.controller.press(); // Stop while working
  assert.equal(w2.state().kind, "idle");
  assert.deepEqual(w2.cancelledTasks, ["task-1"]);
});

test("Stop while the task is running cancels the task, and a later finish is not spoken", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.stop();
  assert.equal(w.state().kind, "idle");
  assert.deepEqual(w.cancelledTasks, ["task-1"]);

  w.controller.taskFinished(completed, true); // it finished just as it was cancelled
  assert.equal(w.state().kind, "idle");
  assert.equal(w.speakCalls.length, 0, "nothing is spoken for a task the user stopped");
});

test("Stop while SAM is speaking silences it; the late end of the speech is ignored", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished(completed, true);
  const speech = w.speakCalls[0];
  const stopsBefore = w.audio.stops;

  w.controller.stop();
  assert.equal(w.state().kind, "idle");
  assert.equal(speech.signal.aborted, true, "the speech request and the fallback voice are aborted");
  assert.equal(w.audio.stops > stopsBefore, true, "the audio player is stopped");
  assert.equal(w.cancelledTasks.length, 0, "the task was finished: nothing to cancel");

  speech.finish({ outcome: "stopped" });
  speech.audioStarts();
  await flush();
  assert.equal(w.state().kind, "idle");
  assert.deepEqual(w.notices, []);
});

// ─── starting over after Stop ────────────────────────────────────────────

test("a second conversation is not disturbed by the first one's late answers", async () => {
  const w = world();
  w.submitGate.current = deferred<string | null>();
  const first = await listen(w);
  w.controller.press();
  first.deliver();
  await flush();
  const firstSubmit = w.submitGate.current;
  w.controller.stop(); // first conversation abandoned while sending

  w.submitGate.current = null;
  const second = await listen(w); // second conversation begins
  assert.equal(w.recordings.length, 2);

  firstSubmit.resolve("task-OLD"); // the old send completes
  await flush();
  assert.equal(w.state().kind, "listening", "the new conversation is untouched");
  assert.deepEqual(w.cancelledTasks, ["task-OLD"]);

  w.controller.press();
  second.deliver();
  await flush();
  assert.deepEqual(w.state(), { kind: "working", taskId: "task-2" });
});

for (const lateOutcome of ["ends", "fails"] as const) {
  test(`the late ${lateOutcome === "ends" ? "end" : "failure"} of an old reply does not disturb a new conversation's reply`, async () => {
    const w = world();
    await sendMessage(w); // task-1
    w.controller.taskFinished(completed, true);
    const oldSpeech = w.speakCalls[0];
    w.controller.stop(); // the user stops the first reply

    w.controller.press(); // a second conversation
    await flush();
    const secondRecording = w.recordings[1];
    w.controller.press();
    secondRecording.deliver();
    await flush();
    assert.deepEqual(w.state(), { kind: "working", taskId: "task-2" });
    w.controller.taskFinished({ ...completed, task_id: "task-2", result_text: "Second answer." }, true);
    assert.deepEqual(w.state(), { kind: "speaking", taskId: "task-2", preparing: true });

    oldSpeech.audioStarts(); // the first reply's callbacks fire late
    assert.deepEqual(w.state(), { kind: "speaking", taskId: "task-2", preparing: true });
    if (lateOutcome === "ends") oldSpeech.finish({ outcome: "played", notice: "a notice from the old reply" });
    else oldSpeech.fail(new Error("the old reply failed late"));
    await flush();
    assert.deepEqual(w.state(), { kind: "speaking", taskId: "task-2", preparing: true });
    assert.deepEqual(w.notices, []);
  });
}

test("a microphone failure that arrives after the user cancelled is not shown, even in a newer conversation", async () => {
  const w = world();
  const oldPrompt = deferred<void>(); // the permission prompt of the first attempt
  w.startGate.current = oldPrompt;
  w.controller.press();
  w.controller.press(); // cancelled
  assert.equal(w.state().kind, "idle");

  const newPrompt = deferred<void>();
  w.startGate.current = newPrompt;
  w.controller.press(); // a second attempt, waiting for its own prompt
  assert.equal(w.state().kind, "starting");

  oldPrompt.reject(new RecordingError("Microphone access was blocked."));
  await flush();
  assert.equal(w.state().kind, "starting", "the old failure is not the new attempt's");

  newPrompt.resolve();
  await flush();
  assert.equal(w.state().kind, "listening");
});

// ─── things going wrong ──────────────────────────────────────────────────

test("a microphone that can't be opened is an error, and pressing again retries", async () => {
  const w = world();
  w.failNextStart(new RecordingError("No microphone was found. Connect one and try again."));
  w.controller.press();
  await flush();
  assert.deepEqual(w.state(), { kind: "error", message: "No microphone was found. Connect one and try again." });

  w.failNextStart(null as unknown as Error);
  w.controller.press();
  assert.equal(w.state().kind, "starting");
  await flush();
  assert.equal(w.state().kind, "listening");
});

test("a recording that fails or is too short is an error with the reason", async () => {
  const w = world();
  const recording = await listen(w);
  recording.fail("That was too short. Click the mic, speak, then click it again.");
  await flush();
  assert.deepEqual(w.state(), {
    kind: "error",
    message: "That was too short. Click the mic, speak, then click it again.",
  });
  assert.equal(w.submitted.length, 0);

  const w2 = world();
  const second = await listen(w2);
  w2.controller.press(); // the user pressed send, then the recording turned out to be unusable
  second.fail("No audio was captured. Check your microphone and try again.");
  await flush();
  assert.equal(w2.state().kind, "error");
});

test("a recording that ends by itself at the maximum length is sent as if the user had pressed", async () => {
  const w = world();
  const recording = await listen(w);
  recording.deliver(); // no press: the recorder reached its limit
  await flush();
  assert.deepEqual(w.state(), { kind: "working", taskId: "task-1" });
  assert.equal(w.submitted.length, 1);
});

test("a task that couldn't be created is an error that says so", async () => {
  const w = world({ submit: async () => null });
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.deepEqual(w.state(), { kind: "error", message: SEND_FAILED });
});

test("a submit that throws is the same error, not a crash", async () => {
  const w = world({
    submit: async () => {
      throw new Error("boom");
    },
  });
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.deepEqual(w.state(), { kind: "error", message: SEND_FAILED });
});

test("a recording that can't be encoded is an error", async () => {
  const w = world({
    encode: async () => {
      throw new Error("FileReader failed");
    },
  });
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  assert.deepEqual(w.state(), { kind: "error", message: READ_FAILED });
  assert.equal(w.submitted.length, 0);
});

test("the error can be dismissed", async () => {
  const w = world({ submit: async () => null });
  const recording = await listen(w);
  w.controller.press();
  recording.deliver();
  await flush();
  w.controller.dismissError();
  assert.equal(w.state().kind, "idle");
});

// ─── replies ─────────────────────────────────────────────────────────────

test("with spoken replies off, a finished task goes straight back to idle", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished(completed, false);
  assert.equal(w.state().kind, "idle");
  assert.equal(w.speakCalls.length, 0);
});

test("a cancelled task is not spoken", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished({ task_id: "task-1", status: "cancelled", result_text: "Cancelled.", error: null }, true);
  assert.equal(w.state().kind, "idle");
  assert.equal(w.speakCalls.length, 0);
});

test("a failed task is spoken as a short apology with the reason", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished({ task_id: "task-1", status: "failed", result_text: null, error: "Ollama is not running." }, true);
  assert.equal(w.speakCalls[0].text, "Sorry, that didn't work. Ollama is not running.");
});

test("a task that isn't the voice task is ignored, even while another reply is being spoken", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished({ ...completed, task_id: "someone-elses" }, true);
  assert.deepEqual(w.state(), { kind: "working", taskId: "task-1" });

  w.controller.taskFinished(completed, true);
  assert.equal(w.speakCalls.length, 1);
  w.controller.taskFinished({ ...completed, task_id: "someone-elses" }, true);
  w.controller.taskFinished(completed, true); // and the same task twice
  assert.equal(w.speakCalls.length, 1, "a reply is spoken once");
  assert.equal(w.state().kind, "speaking");
});

test("a notice from the speech layer is passed on once, when speech ends", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished(completed, true);
  w.speakCalls[0].finish({ outcome: "fallback", notice: "Using the built-in voice." });
  await flush();
  assert.deepEqual(w.notices, ["Using the built-in voice."]);
  assert.equal(w.state().kind, "idle");
});

test("speech that fails outright still ends the conversation instead of hanging on 'speaking'", async () => {
  const w = world();
  await sendMessage(w);
  w.controller.taskFinished(completed, true);
  w.speakCalls[0].fail(new Error("audio device lost"));
  await flush();
  assert.equal(w.state().kind, "idle");
});

// ─── going away ──────────────────────────────────────────────────────────

test("an AudioContext failure does not block microphone start or Stop", async () => {
  const w = world({ unlockAudio: () => { throw new Error("AudioContext unavailable"); } });
  w.controller.press();
  await flush();
  assert.equal(w.state().kind, "listening");
  w.controller.stop();
  assert.equal(w.state().kind, "idle");
});

test("dispose releases the microphone and silences audio, but leaves the task running", async () => {
  const w = world();
  const recording = await listen(w);
  w.controller.dispose();
  assert.equal(recording.cancels, 1);
  assert.equal(w.audio.stops >= 1, true);
  assert.equal(w.state().kind, "idle");

  const w2 = world();
  await sendMessage(w2);
  w2.controller.dispose();
  assert.deepEqual(w2.cancelledTasks, [], "the task carries on; only the listening ends");
});

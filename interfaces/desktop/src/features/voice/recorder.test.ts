import { test } from "node:test";
import assert from "node:assert/strict";
import {
  baseMimeType,
  describeMicError,
  MAX_AUDIO_BYTES,
  MAX_RECORDING_MS,
  pickMimeType,
  RecordingCancelled,
  RecordingError,
  startRecording,
  STOP_GRACE_MS,
} from "./recorder.ts";
import type { RecorderCtor, RecorderDeps, StreamLike } from "./recorder.ts";

// ─── fakes ───────────────────────────────────────────────────────────────

class FakeTrack {
  stopped = 0;
  stop() {
    this.stopped++;
  }
}

class FakeStream implements StreamLike {
  tracks = [new FakeTrack(), new FakeTrack()];
  getTracks() {
    return this.tracks;
  }
  get released() {
    return this.tracks.every((track) => track.stopped >= 1);
  }
}

function fakeRecorderClass(supported: string[], reportedMime: string): RecorderCtor & { instances: FakeRecorder[] } {
  class FakeRecorder {
    static instances: FakeRecorder[] = [];
    static isTypeSupported(type: string) {
      return supported.includes(type);
    }
    mimeType: string;
    options: { mimeType?: string } | undefined;
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    onerror: ((event: unknown) => void) | null = null;
    started = false;
    stopCalls = 0;
    constructor(_stream: StreamLike, options?: { mimeType?: string }) {
      this.options = options;
      this.mimeType = reportedMime;
      FakeRecorder.instances.push(this);
    }
    start() {
      this.started = true;
    }
    stop() {
      this.stopCalls++;
    }
    emitData(bytes: number) {
      this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)]) });
    }
    emitStop() {
      this.onstop?.();
    }
  }
  return FakeRecorder as unknown as RecorderCtor & { instances: FakeRecorder[] };
}
type FakeRecorder = {
  options: { mimeType?: string } | undefined;
  started: boolean;
  stopCalls: number;
  emitData(bytes: number): void;
  emitStop(): void;
  onerror: ((event: unknown) => void) | null;
};

function fakeClock() {
  let time = 0;
  let nextId = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => time,
    setTimeout: (fn: () => void, ms: number) => {
      const id = ++nextId;
      timers.set(id, { at: time + ms, fn });
      return id;
    },
    clearTimeout: (handle: unknown) => {
      timers.delete(handle as number);
    },
    advance(ms: number) {
      const target = time + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        time = due[1].at;
        timers.delete(due[0]);
        due[1].fn();
      }
      time = target;
    },
    pending: () => timers.size,
  };
}

function setup(options: { supported?: string[]; reportedMime?: string } = {}) {
  const stream = new FakeStream();
  const clock = fakeClock();
  const Recorder = fakeRecorderClass(options.supported ?? ["audio/webm"], options.reportedMime ?? "audio/webm;codecs=opus");
  const deps: RecorderDeps = {
    getUserMedia: async () => stream,
    MediaRecorder: Recorder,
    now: clock.now,
    setTimeout: clock.setTimeout,
    clearTimeout: clock.clearTimeout,
  };
  return { stream, clock, Recorder, deps, recorder: () => Recorder.instances[0] as unknown as FakeRecorder };
}

// ─── recording ───────────────────────────────────────────────────────────

test("records, returns the audio under its base MIME type, and releases the microphone", async () => {
  const { stream, clock, deps, recorder } = setup();
  const recording = await startRecording(deps);
  assert.equal(recorder().started, true);

  recorder().emitData(600);
  recorder().emitData(400);
  clock.advance(1500);
  recording.stop();
  assert.equal(recorder().stopCalls, 1);
  assert.equal(stream.released, false, "the recorder still has to flush its last data");
  recorder().emitStop();

  const result = await recording.finished;
  assert.equal(result.mimeType, "audio/webm", "codec parameters are stripped: the server matches exactly");
  assert.equal(result.blob.size, 1000);
  assert.equal(result.blob.type, "audio/webm");
  assert.equal(result.durationMs, 1500);
  assert.equal(stream.released, true);
  assert.equal(clock.pending(), 0, "no timers left behind");
});

test("asks the recorder for the first preferred format the browser supports", async () => {
  const ogg = setup({ supported: ["audio/ogg", "audio/mp4"] });
  await startRecording(ogg.deps);
  assert.deepEqual(ogg.recorder().options, { mimeType: "audio/ogg" });

  const none = setup({ supported: [] });
  await startRecording(none.deps);
  assert.equal(none.recorder().options, undefined, "no preference: let the browser choose");
});

test("Safari-style recorder with no preferred type reports audio/mp4 and that is what is sent", async () => {
  const { clock, deps, recorder } = setup({ supported: [], reportedMime: "audio/mp4" });
  const recording = await startRecording(deps);
  recorder().emitData(2000);
  clock.advance(1000);
  recording.stop();
  recorder().emitStop();
  assert.equal((await recording.finished).mimeType, "audio/mp4");
});

test("a format the server can't read is refused, and the microphone is still released", async () => {
  const { stream, clock, deps, recorder } = setup({ reportedMime: "video/x-matroska" });
  const recording = await startRecording(deps);
  recorder().emitData(2000);
  clock.advance(1000);
  recording.stop();
  recorder().emitStop();
  await assert.rejects(recording.finished, (error: Error) => error instanceof RecordingError && /video\/x-matroska/.test(error.message));
  assert.equal(stream.released, true);
});

test("an empty recording, a too-short one and an oversized one are each refused with a reason", async () => {
  const empty = setup();
  const emptyRecording = await startRecording(empty.deps);
  empty.clock.advance(2000);
  emptyRecording.stop();
  empty.recorder().emitStop();
  await assert.rejects(emptyRecording.finished, /No audio was captured/);

  const brief = setup();
  const briefRecording = await startRecording(brief.deps);
  brief.recorder().emitData(500);
  brief.clock.advance(100);
  briefRecording.stop();
  brief.recorder().emitStop();
  await assert.rejects(briefRecording.finished, /too short/);

  const huge = setup();
  const hugeRecording = await startRecording(huge.deps);
  huge.recorder().emitData(MAX_AUDIO_BYTES + 1);
  huge.clock.advance(5000);
  hugeRecording.stop();
  huge.recorder().emitStop();
  await assert.rejects(hugeRecording.finished, /too large/);
});

test("stops by itself at the maximum length and still delivers what was said", async () => {
  const { stream, clock, deps, recorder } = setup();
  const recording = await startRecording(deps);
  recorder().emitData(5000);
  clock.advance(MAX_RECORDING_MS - 1);
  assert.equal(recorder().stopCalls, 0);
  clock.advance(1);
  assert.equal(recorder().stopCalls, 1);
  recorder().emitStop();
  const result = await recording.finished;
  assert.equal(result.durationMs, MAX_RECORDING_MS);
  assert.equal(stream.released, true);
});

test("stop() twice stops the recorder once", async () => {
  const { deps, recorder } = setup();
  const recording = await startRecording(deps);
  recording.stop();
  recording.stop();
  assert.equal(recorder().stopCalls, 1);
});

test("cancel throws the audio away and releases the microphone", async () => {
  const { stream, deps, recorder } = setup();
  const recording = await startRecording(deps);
  recorder().emitData(5000);
  recording.cancel();
  recorder().emitStop();
  await assert.rejects(recording.finished, (error: Error) => error instanceof RecordingCancelled);
  assert.equal(stream.released, true);
});

test("cancelling before anyone awaits the recording is not an unhandled rejection", async () => {
  const { deps, recorder } = setup();
  const unhandled: unknown[] = [];
  const listener = (reason: unknown) => unhandled.push(reason);
  process.on("unhandledRejection", listener);
  try {
    const recording = await startRecording(deps);
    recording.cancel();
    recorder().emitStop();
    await new Promise((resolve) => setTimeout(resolve, 20));
  } finally {
    process.off("unhandledRejection", listener);
  }
  assert.deepEqual(unhandled, []);
});

test("if the recorder never reports its stop, the microphone is still released after a grace period", async () => {
  const { stream, clock, deps } = setup();
  const recording = await startRecording(deps);
  recording.stop();
  assert.equal(stream.released, false);
  clock.advance(STOP_GRACE_MS);
  await assert.rejects(recording.finished, /didn't finish/);
  assert.equal(stream.released, true);
});

test("a recorder error rejects the recording and releases the microphone", async () => {
  const { stream, deps, recorder } = setup();
  const recording = await startRecording(deps);
  recorder().onerror?.({});
  await assert.rejects(recording.finished, /recording failed/);
  assert.equal(stream.released, true);
});

// ─── starting ────────────────────────────────────────────────────────────

test("cancelled while the permission prompt is open: the stream is released and nothing records", async () => {
  const stream = new FakeStream();
  const Recorder = fakeRecorderClass(["audio/webm"], "audio/webm");
  let grant!: (s: StreamLike) => void;
  const deps: RecorderDeps = {
    getUserMedia: () => new Promise<StreamLike>((resolve) => (grant = resolve)),
    MediaRecorder: Recorder,
  };
  const controller = new AbortController();
  const starting = startRecording(deps, { signal: controller.signal });
  controller.abort(); // the user pressed the mic again
  grant(stream); // ...and then allowed access
  await assert.rejects(starting, (error: Error) => error instanceof RecordingCancelled);
  assert.equal(stream.released, true);
  assert.equal(Recorder.instances.length, 0);
});

test("a recorder that can't be constructed releases the microphone", async () => {
  const stream = new FakeStream();
  class Broken {
    static isTypeSupported() {
      return true;
    }
    constructor() {
      throw new Error("MediaRecorder is disabled");
    }
  }
  await assert.rejects(
    startRecording({ getUserMedia: async () => stream, MediaRecorder: Broken as unknown as RecorderCtor }),
    /Couldn't start recording: MediaRecorder is disabled/,
  );
  assert.equal(stream.released, true);
});

test("a web view without microphone or recorder support says so", async () => {
  await assert.rejects(startRecording({}), /can't record audio/);
  await assert.rejects(startRecording({ getUserMedia: async () => new FakeStream() }), /can't record audio/);
});

test("permission and device failures are explained in terms the user can act on", async () => {
  const failWith = (name: string, message = "x") => {
    const error = Object.assign(new Error(message), { name });
    return startRecording({
      getUserMedia: async () => {
        throw error;
      },
      MediaRecorder: fakeRecorderClass([], ""),
    });
  };
  await assert.rejects(failWith("NotAllowedError"), /blocked.*privacy settings/s);
  await assert.rejects(failWith("NotFoundError"), /No microphone was found/);
  await assert.rejects(failWith("NotReadableError"), /in use by another app/);
  await assert.rejects(failWith("SomethingElse", "weird"), /Couldn't open the microphone: weird/);
});

// ─── helpers ─────────────────────────────────────────────────────────────

test("baseMimeType strips parameters and normalises case", () => {
  assert.equal(baseMimeType("audio/webm;codecs=opus"), "audio/webm");
  assert.equal(baseMimeType("Audio/MP4 ; codecs=mp4a.40.2"), "audio/mp4");
  assert.equal(baseMimeType("audio/ogg"), "audio/ogg");
});

test("pickMimeType prefers webm, then ogg, then mp4, and survives a browser that throws", () => {
  assert.equal(pickMimeType(() => true), "audio/webm");
  assert.equal(pickMimeType((mime) => mime !== "audio/webm"), "audio/ogg");
  assert.equal(pickMimeType((mime) => mime === "audio/mp4"), "audio/mp4");
  assert.equal(pickMimeType(() => false), "");
  assert.equal(
    pickMimeType((mime) => {
      if (mime === "audio/webm") throw new Error("nope");
      return mime === "audio/ogg";
    }),
    "audio/ogg",
  );
});

test("describeMicError handles things that are not Errors", () => {
  assert.match(describeMicError("denied"), /Couldn't open the microphone/);
  assert.match(describeMicError(undefined), /Couldn't open the microphone/);
  assert.match(describeMicError({ name: "NotAllowedError" }), /blocked/);
});

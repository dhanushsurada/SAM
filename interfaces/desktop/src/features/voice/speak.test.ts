import { test } from "node:test";
import assert from "node:assert/strict";
import { speakReply } from "./speak.ts";
import type { SpeakDeps } from "./speak.ts";

const NOTICES = { fallback: "using the built-in voice", unavailable: "no voice here" };

function statusError(status: number): Error {
  return Object.assign(new Error(`${status}: x`), { status });
}

function abortError(): Error {
  return Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
}

function setup(overrides: Partial<SpeakDeps> = {}) {
  const calls: string[] = [];
  const deps: SpeakDeps = {
    synthesize: async (text) => {
      calls.push(`synthesize:${text}`);
      return new ArrayBuffer(4);
    },
    play: async () => {
      calls.push("play");
    },
    webviewSpeak: async (text) => {
      calls.push(`webview:${text}`);
    },
    onAudioStart: () => calls.push("audio-start"),
    notices: NOTICES,
    ...overrides,
  };
  return { calls, deps, signal: new AbortController().signal };
}

test("SAM's own voice: synthesize, announce the audio, play", async () => {
  const { calls, deps, signal } = setup();
  assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "played" });
  assert.deepEqual(calls, ["synthesize:Hello", "audio-start", "play"]);
});

test("speech turned off (409) and nothing to say (422) stay silent: no fallback voice", async () => {
  for (const status of [409, 422]) {
    const { calls, deps, signal } = setup({
      synthesize: async () => {
        throw statusError(status);
      },
    });
    assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "silent" }, String(status));
    assert.deepEqual(calls, [], "neither the web view voice nor playback was used");
  }
});

test("no engine can return audio (501): the web view's voice speaks, and the user is told once how to get SAM's own", async () => {
  const { calls, deps, signal } = setup({
    synthesize: async () => {
      throw statusError(501);
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "fallback", notice: NOTICES.fallback });
  assert.deepEqual(calls, ["audio-start", "webview:Hello"]);
});

test("any other failure (server unreachable, 500) also falls back, without the install advice", async () => {
  for (const error of [new TypeError("Failed to fetch"), statusError(500)]) {
    const { calls, deps, signal } = setup({
      synthesize: async () => {
        throw error;
      },
    });
    assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "fallback", notice: undefined });
    assert.deepEqual(calls, ["audio-start", "webview:Hello"]);
  }
});

test("audio the web view can't decode falls back to the web view's voice", async () => {
  const { calls, deps, signal } = setup({
    play: async () => {
      throw new Error("EncodingError");
    },
  });
  const result = await speakReply("Hello", deps, signal);
  assert.equal(result.outcome, "fallback");
  assert.deepEqual(calls, ["synthesize:Hello", "audio-start", "audio-start", "webview:Hello"]);
});

test("with no web view voice either, it says nothing could speak, instead of failing", async () => {
  const { deps, signal } = setup({
    synthesize: async () => {
      throw statusError(501);
    },
    webviewSpeak: undefined,
  });
  assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "unavailable", notice: NOTICES.unavailable });
});

test("a web view voice that fails is reported as unavailable, not thrown", async () => {
  const { deps, signal } = setup({
    synthesize: async () => {
      throw statusError(501);
    },
    webviewSpeak: async () => {
      throw new Error("synthesis-failed");
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, signal), { outcome: "unavailable", notice: NOTICES.unavailable });
});

test("stopping while the voice is being prepared abandons it quietly", async () => {
  const controller = new AbortController();
  const { calls, deps } = setup({
    synthesize: async () => {
      controller.abort();
      throw abortError();
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, controller.signal), { outcome: "stopped" });
  assert.deepEqual(calls, [], "no fallback voice starts after Stop");
});

test("stopping after the audio arrived but before it plays means it never plays", async () => {
  const controller = new AbortController();
  const { calls, deps } = setup({
    synthesize: async () => {
      controller.abort();
      return new ArrayBuffer(4);
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, controller.signal), { outcome: "stopped" });
  assert.deepEqual(calls, []);
});

test("stopping during playback ends as stopped", async () => {
  const controller = new AbortController();
  const { deps } = setup({
    play: async () => {
      controller.abort(); // the player resolves when stop() silences it
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, controller.signal), { outcome: "stopped" });
});

test("stopping during the web view voice ends as stopped", async () => {
  const controller = new AbortController();
  const { deps } = setup({
    synthesize: async () => {
      throw statusError(501);
    },
    webviewSpeak: async () => {
      controller.abort();
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, controller.signal), { outcome: "stopped" });
});

test("an abort that wasn't the user's Stop is just a failure: the reply is still spoken", async () => {
  const { calls, deps, signal } = setup({
    synthesize: async () => {
      throw abortError(); // e.g. the browser dropped the request; our signal was never aborted
    },
  });
  assert.equal((await speakReply("Hello", deps, signal)).outcome, "fallback");
  assert.deepEqual(calls, ["audio-start", "webview:Hello"]);
});

test("a web view voice that fails because the user pressed Stop is a stop, not 'unavailable'", async () => {
  const controller = new AbortController();
  const { deps } = setup({
    synthesize: async () => {
      throw statusError(501);
    },
    webviewSpeak: async () => {
      controller.abort();
      throw new Error("canceled");
    },
  });
  assert.deepEqual(await speakReply("Hello", deps, controller.signal), { outcome: "stopped" });
});

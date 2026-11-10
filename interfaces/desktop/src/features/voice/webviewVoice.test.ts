import { test } from "node:test";
import assert from "node:assert/strict";
import { createWebviewVoice } from "./webviewVoice.ts";
import type { SynthLike, UtteranceLike } from "./webviewVoice.ts";

class FakeUtterance implements UtteranceLike {
  onend: (() => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  text: string;
  constructor(text: string) {
    this.text = text;
  }
}

class FakeSynth implements SynthLike {
  spoken: FakeUtterance[] = [];
  cancels = 0;
  speak(utterance: UtteranceLike) {
    this.spoken.push(utterance as FakeUtterance);
  }
  cancel() {
    this.cancels++;
  }
}

const make = (text: string) => new FakeUtterance(text);

test("there is no web view voice without speech synthesis", () => {
  assert.equal(createWebviewVoice(undefined, make), undefined);
  assert.equal(createWebviewVoice(new FakeSynth(), undefined), undefined);
});

test("speaks the text and resolves when the utterance ends", async () => {
  const synth = new FakeSynth();
  const speak = createWebviewVoice(synth, make)!;
  const done = speak("Hello there", new AbortController().signal);
  assert.equal(synth.spoken[0].text, "Hello there");
  synth.spoken[0].onend?.();
  await done;
});

test("aborting cancels the speech and resolves, and the listener is gone after a normal end", async () => {
  const synth = new FakeSynth();
  const speak = createWebviewVoice(synth, make)!;

  const stopped = new AbortController();
  const stoppedSpeech = speak("one", stopped.signal);
  stopped.abort();
  await stoppedSpeech;
  assert.equal(synth.cancels, 1);

  const finished = new AbortController();
  const finishedSpeech = speak("two", finished.signal);
  synth.spoken[1].onend?.();
  await finishedSpeech;
  finished.abort();
  assert.equal(synth.cancels, 1, "no cancel() for an utterance that already ended");
});

test("an already-aborted signal speaks nothing", async () => {
  const synth = new FakeSynth();
  const speak = createWebviewVoice(synth, make)!;
  const controller = new AbortController();
  controller.abort();
  await speak("never", controller.signal);
  assert.equal(synth.spoken.length, 0);
});

test("'canceled' and 'interrupted' are stops; any other error is a failure", async () => {
  const synth = new FakeSynth();
  const speak = createWebviewVoice(synth, make)!;

  for (const reason of ["canceled", "interrupted"]) {
    const done = speak("x", new AbortController().signal);
    synth.spoken[synth.spoken.length - 1].onerror?.({ error: reason });
    await done;
  }

  const failing = speak("x", new AbortController().signal);
  synth.spoken[synth.spoken.length - 1].onerror?.({ error: "synthesis-failed" });
  await assert.rejects(failing, /synthesis-failed/);

  const unknown = speak("x", new AbortController().signal);
  synth.spoken[synth.spoken.length - 1].onerror?.({});
  await assert.rejects(unknown, /unknown error/);
});

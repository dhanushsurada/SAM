import { test } from "node:test";
import assert from "node:assert/strict";
import { createAudioPlayer } from "./player.ts";
import type { AudioContextLike, SourceLike } from "./player.ts";

class FakeSource implements SourceLike {
  buffer: unknown = null;
  onended: (() => void) | null = null;
  connected: unknown[] = [];
  started = 0;
  stopped = 0;
  throwOnStop = false;
  connect(destination: unknown) {
    this.connected.push(destination);
  }
  start() {
    this.started++;
  }
  stop() {
    this.stopped++;
    if (this.throwOnStop) throw new Error("InvalidStateError");
  }
  /** The audio reached its end by itself. */
  end() {
    this.onended?.();
  }
}

class FakeContext implements AudioContextLike {
  state = "suspended";
  destination = { name: "speakers" };
  resumes = 0;
  sources: FakeSource[] = [];
  decoded: ArrayBuffer[] = [];
  gate: Promise<void> | null = null;
  failDecode = false;
  async resume() {
    this.resumes++;
    this.state = "running";
  }
  async decodeAudioData(data: ArrayBuffer) {
    this.decoded.push(data);
    if (this.gate) await this.gate;
    if (this.failDecode) throw new Error("EncodingError");
    return { decodedBytes: data.byteLength };
  }
  createBufferSource() {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
}

const audio = (n = 8) => new Uint8Array(n).buffer;
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("unlock, called from the click, creates and resumes the audio context once", () => {
  const ctx = new FakeContext();
  let made = 0;
  const player = createAudioPlayer(() => {
    made++;
    return ctx;
  });
  player.unlock();
  player.unlock();
  assert.equal(made, 1);
  assert.equal(ctx.resumes, 1, "a running context is not resumed again");
});

test("plays decoded audio through the speakers and resolves when it ends", async () => {
  const ctx = new FakeContext();
  const player = createAudioPlayer(() => ctx);
  player.unlock();
  const data = audio(16);

  let finished = false;
  const playing = player.play(data).then(() => (finished = true));
  await tick();

  assert.equal(ctx.sources.length, 1);
  const source = ctx.sources[0];
  assert.deepEqual(source.buffer, { decodedBytes: 16 });
  assert.deepEqual(source.connected, [ctx.destination]);
  assert.equal(source.started, 1);
  assert.notEqual(ctx.decoded[0], data, "decodeAudioData is given a copy; it detaches what it is given");
  assert.equal(data.byteLength, 16, "the caller's buffer is untouched");
  assert.equal(finished, false, "still playing");

  source.end();
  await playing;
  assert.equal(finished, true);
});

test("plays even if unlock was never called: it resumes a suspended context itself", async () => {
  const ctx = new FakeContext();
  const player = createAudioPlayer(() => ctx);
  const playing = player.play(audio());
  await tick();
  assert.equal(ctx.resumes, 1);
  ctx.sources[0].end();
  await playing;
});

test("stop silences playback immediately and resolves the pending play", async () => {
  const ctx = new FakeContext();
  const player = createAudioPlayer(() => ctx);
  const playing = player.play(audio());
  await tick();
  const source = ctx.sources[0];

  player.stop();
  await playing; // resolves without the audio ever "ending"
  assert.equal(source.stopped, 1);
  assert.equal(source.onended, null);
});

test("stop while the audio is still being decoded means it never starts", async () => {
  const ctx = new FakeContext();
  let release!: () => void;
  ctx.gate = new Promise<void>((resolve) => (release = resolve));
  const player = createAudioPlayer(() => ctx);

  const playing = player.play(audio());
  await tick();
  player.stop();
  release();
  await playing;
  assert.equal(ctx.sources.length, 0);
});

test("a second play replaces the first", async () => {
  const ctx = new FakeContext();
  const player = createAudioPlayer(() => ctx);
  const first = player.play(audio());
  await tick();
  const second = player.play(audio());
  await tick();

  await first; // the first was stopped to make way
  assert.equal(ctx.sources[0].stopped, 1);
  assert.equal(ctx.sources.length, 2);
  assert.equal(ctx.sources[1].started, 1);
  ctx.sources[1].end();
  await second;
});

test("with no audio output at all, play rejects and unlock does nothing", async () => {
  const player = createAudioPlayer(() => null);
  player.unlock();
  await assert.rejects(player.play(audio()), /isn't available/);
});

test("audio that can't be decoded rejects, so the caller can fall back", async () => {
  const ctx = new FakeContext();
  ctx.failDecode = true;
  const player = createAudioPlayer(() => ctx);
  await assert.rejects(player.play(audio()), /EncodingError/);
  assert.equal(ctx.sources.length, 0);
});

test("stop with nothing playing, or a source that refuses to stop, is harmless", async () => {
  const ctx = new FakeContext();
  const player = createAudioPlayer(() => ctx);
  player.stop();

  const playing = player.play(audio());
  await tick();
  ctx.sources[0].throwOnStop = true;
  player.stop();
  await playing;
});

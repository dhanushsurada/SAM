/**
 * Plays the audio file SAM's voice endpoint returns, through the Web Audio
 * API rather than an <audio> element. Reason: WebKit (the macOS web view)
 * only lets a page start audio from a user gesture. A reply is spoken long
 * after the click that started the conversation, so the AudioContext is
 * created and resumed inside that click (unlock()); a running context can
 * then start sounds whenever the reply arrives, and AudioBufferSourceNode
 * gives a Stop that works immediately.
 *
 * The context is injected so the logic (stop while decoding, stop while
 * playing, a second play replacing the first) is testable in Node.
 */

export interface SourceLike {
  buffer: unknown;
  onended: (() => void) | null;
  connect(destination: unknown): unknown;
  start(when?: number): void;
  stop(): void;
}

export interface AudioContextLike {
  state: string;
  destination: unknown;
  resume(): Promise<void>;
  decodeAudioData(data: ArrayBuffer): Promise<unknown>;
  createBufferSource(): SourceLike;
}

export interface AudioPlayer {
  /** Call from a click handler: creates and resumes the audio context. */
  unlock(): void;
  /** Plays a complete audio file. Resolves when it has finished or was
   * stopped; rejects if it cannot be decoded or there is no audio output. */
  play(data: ArrayBuffer): Promise<void>;
  /** Silences whatever is playing, or about to play. */
  stop(): void;
}

export function createAudioPlayer(makeContext: () => AudioContextLike | null): AudioPlayer {
  let context: AudioContextLike | null = null;
  // Bumped by stop() and by each play(), so a play() that is still decoding
  // when it is stopped (or replaced) knows not to start.
  let generation = 0;
  let current: { source: SourceLike; finish: () => void } | null = null;

  const getContext = (): AudioContextLike | null => {
    if (context === null) context = makeContext();
    return context;
  };

  const stopCurrent = () => {
    const playing = current;
    current = null;
    if (!playing) return;
    playing.source.onended = null;
    try {
      playing.source.stop();
    } catch {
      // Not started, or already ended.
    }
    playing.finish();
  };

  return {
    unlock() {
      const ctx = getContext();
      if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    },

    async play(data) {
      const ctx = getContext();
      if (!ctx) throw new Error("Audio playback isn't available in this web view.");
      const mine = ++generation;
      stopCurrent();
      if (ctx.state === "suspended") await ctx.resume();
      // decodeAudioData detaches the buffer it is given; hand it a copy.
      const buffer = await ctx.decodeAudioData(data.slice(0));
      if (mine !== generation) return; // stopped or replaced while decoding

      await new Promise<void>((resolve) => {
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        let done = false;
        const finish = () => {
          if (done) return;
          done = true;
          if (current?.source === source) current = null;
          resolve();
        };
        source.onended = finish;
        current = { source, finish };
        source.start(0);
      });
    },

    stop() {
      generation++;
      stopCurrent();
    },
  };
}

/**
 * Plays the audio file SAM's voice endpoint returns, through the Web Audio
 * API rather than an <audio> element. Reason: WebKit (the macOS web view)
 * only lets a page start audio from a user gesture. A reply is spoken long
 * after the click that started the conversation, so the AudioContext is
 * created and resumed inside that click (unlock()); a running context can
 * then start sounds whenever the reply arrives, and AudioBufferSourceNode
 * gives a Stop that works immediately.
 *
 * Dedicated Voice Gain & Silent Override:
 * Allows SAM's voice to remain audible even when other system/media volumes
 * are kept low or silent. Uses Web Audio GainNode to amplify speech levels.
 */

export interface SourceLike {
  buffer: unknown;
  onended: (() => void) | null;
  connect(destination: unknown): unknown;
  start(when?: number): void;
  stop(): void;
}

export interface GainNodeLike {
  gain: { value: number };
  connect(destination: unknown): unknown;
}

export interface AudioContextLike {
  state: string;
  destination: unknown;
  resume(): Promise<void>;
  decodeAudioData(data: ArrayBuffer): Promise<unknown>;
  createBufferSource(): SourceLike;
  createGain?(): GainNodeLike;
}

export interface VoiceAudioConfig {
  /** When true, boosts SAM's audio output so speech remains audible in quiet/silent environments. */
  overrideSilentMode: boolean;
  /** Digital gain boost multiplier (1.0 = normal, 1.5 = +3.5dB, 2.0 = +6dB). Default: 1.6 */
  volumeBoost: number;
}

const DEFAULT_AUDIO_CONFIG: VoiceAudioConfig = {
  overrideSilentMode: true,
  volumeBoost: 1.6,
};

let currentAudioConfig: VoiceAudioConfig = { ...DEFAULT_AUDIO_CONFIG };

export function getVoiceAudioConfig(): VoiceAudioConfig {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem("sam.voice_audio_config");
      if (stored) {
        const parsed = JSON.parse(stored);
        return { ...DEFAULT_AUDIO_CONFIG, ...parsed };
      }
    } catch {
      // fallback
    }
  }
  return currentAudioConfig;
}

export function setVoiceAudioConfig(cfg: Partial<VoiceAudioConfig>): void {
  currentAudioConfig = { ...getVoiceAudioConfig(), ...cfg };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem("sam.voice_audio_config", JSON.stringify(currentAudioConfig));
    } catch {
      // fallback
    }
  }
}

export interface AudioPlayer {
  /** Call from a click handler: creates and resumes the audio context. */
  unlock(): void;
  /** Plays a complete audio file. Resolves when it has finished or was
   * stopped; rejects if it cannot be decoded or there is no audio output. */
  play(data: ArrayBuffer): Promise<void>;
  /** Silences whatever is playing, or about to play. */
  stop(): void;
  /** Configure digital gain boost and silent mode override. */
  configureAudio(cfg: Partial<VoiceAudioConfig>): void;
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

    configureAudio(cfg: Partial<VoiceAudioConfig>) {
      setVoiceAudioConfig(cfg);
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

        // Apply gain node when available to support silent mode override and digital boost
        const config = getVoiceAudioConfig();
        if (typeof ctx.createGain === "function" && config.overrideSilentMode) {
          try {
            const gain = ctx.createGain();
            gain.gain.value = Math.max(0.5, Math.min(3.0, config.volumeBoost || 1.6));
            source.connect(gain);
            gain.connect(ctx.destination);
          } catch {
            source.connect(ctx.destination);
          }
        } else {
          source.connect(ctx.destination);
        }

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

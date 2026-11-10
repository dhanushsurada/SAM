/**
 * Microphone recording for voice input: getUserMedia + MediaRecorder behind
 * injected dependencies, so the parts that go wrong in real use can be
 * tested without a browser: the microphone must always be released (a
 * forgotten track leaves the OS "mic in use" light on), a cancelled start
 * must not leave a stream open, and the audio sent to SAM must be in a
 * format its server accepts.
 *
 * MIME handling is copied from the phone client (interfaces/web/audio.js)
 * and the server's allow-list (multimodal/media_validation.py). One
 * difference matters: MediaRecorder.mimeType can carry codec parameters
 * ("audio/webm;codecs=opus"), which the server's exact-match check would
 * reject, so only the base type is sent.
 */

/** What the server accepts (multimodal/media_validation.py ALLOWED_AUDIO_MIME). */
export const SERVER_AUDIO_MIME: readonly string[] = [
  "audio/webm",
  "audio/wav",
  "audio/x-wav",
  "audio/mp4",
  "audio/ogg",
  "audio/mpeg",
];
/** Tried in this order, as interfaces/web/audio.js does. */
export const PREFERRED_MIME: readonly string[] = ["audio/webm", "audio/ogg", "audio/mp4"];

/** Recording stops by itself here: voice input is for commands, not dictation. */
export const MAX_RECORDING_MS = 60_000;
/** Shorter than this is a stray double-click, not speech. */
export const MIN_RECORDING_MS = 400;
/** The server's limit (multimodal/media_validation.py MAX_AUDIO_BYTES). */
export const MAX_AUDIO_BYTES = 15 * 1024 * 1024;
/** How long to wait for the recorder's final "stop" before giving up on it. */
export const STOP_GRACE_MS = 3000;

export class RecordingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RecordingError";
  }
}

/** The recording was cancelled on purpose; not a failure to report. */
export class RecordingCancelled extends Error {
  constructor() {
    super("Recording cancelled");
    this.name = "RecordingCancelled";
  }
}

export interface TrackLike {
  stop(): void;
}
export interface StreamLike {
  getTracks(): TrackLike[];
}
export interface RecorderLike {
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  onerror: ((event: unknown) => void) | null;
  start(): void;
  stop(): void;
}
export interface RecorderCtor {
  new (stream: StreamLike, options?: { mimeType?: string }): RecorderLike;
  isTypeSupported(type: string): boolean;
}

export interface RecorderDeps {
  getUserMedia?: (constraints: { audio: boolean }) => Promise<StreamLike>;
  MediaRecorder?: RecorderCtor;
  now?: () => number;
  setTimeout?: (fn: () => void, ms: number) => unknown;
  clearTimeout?: (handle: unknown) => void;
}

export interface RecordingResult {
  blob: Blob;
  /** Base type only, e.g. "audio/webm" — safe to send to the server. */
  mimeType: string;
  durationMs: number;
}

export interface Recording {
  /** Settles when the recording ends: resolves with the audio, rejects with
   * RecordingError (nothing usable) or RecordingCancelled. It ends when
   * stop() is called and also by itself at MAX_RECORDING_MS. */
  finished: Promise<RecordingResult>;
  /** Stop and keep the audio. */
  stop(): void;
  /** Stop and throw the audio away. */
  cancel(): void;
}

/** "audio/webm;codecs=opus" -> "audio/webm". */
export function baseMimeType(mime: string): string {
  return mime.split(";")[0].trim().toLowerCase();
}

/** First preferred type this browser can record, or "" to let it choose. */
export function pickMimeType(isTypeSupported: (mime: string) => boolean): string {
  for (const mime of PREFERRED_MIME) {
    try {
      if (isTypeSupported(mime)) return mime;
    } catch {
      // A browser that throws for a type does not support it.
    }
  }
  return "";
}

/** A getUserMedia failure, in words the user can act on. */
export function describeMicError(err: unknown): string {
  const name = typeof err === "object" && err !== null && "name" in err ? String((err as { name: unknown }).name) : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
    case "PermissionDeniedError":
      return "Microphone access was blocked. Allow SAM to use the microphone in your system's privacy settings, then try again.";
    case "NotFoundError":
    case "DevicesNotFoundError":
    case "OverconstrainedError":
      return "No microphone was found. Connect one and try again.";
    case "NotReadableError":
    case "TrackStartError":
      return "The microphone is in use by another app, or can't be opened.";
    default: {
      const detail = err instanceof Error && err.message ? `: ${err.message}` : "";
      return `Couldn't open the microphone${detail}`;
    }
  }
}

export async function startRecording(
  deps: RecorderDeps,
  options: { signal?: AbortSignal } = {},
): Promise<Recording> {
  const { getUserMedia, MediaRecorder: Recorder } = deps;
  if (!getUserMedia || !Recorder) throw new RecordingError("This app's web view can't record audio.");
  const now = deps.now ?? Date.now;
  const setTimer = deps.setTimeout ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer = deps.clearTimeout ?? ((handle: unknown) => clearTimeout(handle as ReturnType<typeof setTimeout>));

  let stream: StreamLike;
  try {
    stream = await getUserMedia({ audio: true });
  } catch (err) {
    throw new RecordingError(describeMicError(err));
  }

  const release = () => {
    for (const track of stream.getTracks()) {
      try {
        track.stop();
      } catch {
        // Already stopped.
      }
    }
  };

  if (options.signal?.aborted) {
    release(); // the user cancelled while the permission prompt was open
    throw new RecordingCancelled();
  }

  const preferred = pickMimeType((mime) => Recorder.isTypeSupported(mime));
  let recorder: RecorderLike;
  try {
    recorder = preferred ? new Recorder(stream, { mimeType: preferred }) : new Recorder(stream);
    recorder.start();
  } catch (err) {
    release();
    const detail = err instanceof Error && err.message ? `: ${err.message}` : "";
    throw new RecordingError(`Couldn't start recording${detail}`);
  }

  const startedAt = now();
  const chunks: Blob[] = [];
  let stopRequested = false;
  let cancelled = false;
  let maxTimer: unknown;
  let graceTimer: unknown;
  let resolveFinished!: (result: RecordingResult) => void;
  let rejectFinished!: (error: Error) => void;
  const finished = new Promise<RecordingResult>((resolve, reject) => {
    resolveFinished = resolve;
    rejectFinished = reject;
  });
  // A recording cancelled before anyone awaits `finished` is not an
  // "unhandled rejection"; consumers that do await it still get the error.
  finished.catch(() => {});

  const settle = (fn: () => void) => {
    if (maxTimer !== undefined) clearTimer(maxTimer);
    if (graceTimer !== undefined) clearTimer(graceTimer);
    release();
    fn();
  };

  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data);
  };
  recorder.onerror = () => {
    settle(() => rejectFinished(new RecordingError("The microphone recording failed. Try again.")));
  };
  recorder.onstop = () => {
    settle(() => {
      if (cancelled) return rejectFinished(new RecordingCancelled());
      const durationMs = now() - startedAt;
      const mimeType = baseMimeType(recorder.mimeType || preferred || "audio/webm");
      const blob = new Blob(chunks, { type: mimeType });
      if (!SERVER_AUDIO_MIME.includes(mimeType)) {
        return rejectFinished(new RecordingError(`This web view recorded audio as ${mimeType}, which SAM can't read.`));
      }
      if (blob.size === 0) {
        return rejectFinished(new RecordingError("No audio was captured. Check your microphone and try again."));
      }
      if (durationMs < MIN_RECORDING_MS) {
        return rejectFinished(new RecordingError("That was too short. Click the mic, speak, then click it again."));
      }
      if (blob.size > MAX_AUDIO_BYTES) {
        return rejectFinished(new RecordingError("That recording is too large to send."));
      }
      resolveFinished({ blob, mimeType, durationMs });
    });
  };

  const requestStop = () => {
    if (stopRequested) return;
    stopRequested = true;
    try {
      recorder.stop();
    } catch {
      // Already inactive: the "stop" event may never come, so fall through
      // to the grace timer, which releases the microphone either way.
    }
    graceTimer = setTimer(() => {
      settle(() => rejectFinished(new RecordingError("The recording didn't finish. Try again.")));
    }, STOP_GRACE_MS);
  };

  maxTimer = setTimer(requestStop, MAX_RECORDING_MS);

  return {
    finished,
    stop: requestStop,
    cancel: () => {
      cancelled = true;
      requestStop();
    },
  };
}

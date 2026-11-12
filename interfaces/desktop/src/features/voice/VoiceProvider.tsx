import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { TERMINAL_PHASES } from "@/api/types";
import { blobToBase64 } from "@/lib/file";
import { speechService } from "@/services/speech";
import { useTaskSession } from "@/stores/taskSession";
import { createAudioPlayer } from "./player";
import type { AudioContextLike } from "./player";
import { startRecording } from "./recorder";
import type { RecorderCtor, RecorderDeps } from "./recorder";
import { speakReply } from "./speak";
import { createVoiceController } from "./voiceController";
import { isBusy, isCapturing } from "./voiceMachine";
import type { VoiceState } from "./voiceMachine";
import {
  FALLBACK_VOICE_NOTICE,
  micLabel,
  micUnavailableReason,
  NO_VOICE_NOTICE,
  shortStatus,
  statusText,
} from "./voiceText";
import type { VoiceEnvironment } from "./voiceText";
import { createWebviewVoice } from "./webviewVoice";
import type { UtteranceLike } from "./webviewVoice";
import { replyToSpeak } from "./speechText";

/**
 * Touch-to-talk for the desktop app: the React side. The behaviour lives in
 * voiceController.ts (tested in Node without a browser); this file connects
 * it to the browser's microphone and speakers, to the task session (which
 * creates and tracks the voice task), and to React.
 *
 * Voice is not a second assistant: a recording is sent through the same
 * gateway, Brain and Hands as a typed message (an "audio" attachment on a
 * task), and the task's reply is spoken by the engine SAM already has.
 */

const SPEAK_REPLIES_KEY = "sam.desktop.voice.speak-replies.v1";
/** After this long on one step, say what the likely reason is. */
const SLOW_AFTER_MS = 8000;

// ─── the browser, behind the shapes the voice modules expect ─────────────

function browserRecorderDeps(): RecorderDeps {
  const devices = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
  return {
    getUserMedia: devices && typeof devices.getUserMedia === "function" ? (constraints) => devices.getUserMedia(constraints) : undefined,
    MediaRecorder: typeof MediaRecorder !== "undefined" ? (MediaRecorder as unknown as RecorderCtor) : undefined,
  };
}

function browserVoiceEnvironment(): VoiceEnvironment {
  const deps = browserRecorderDeps();
  return { hasMicrophoneApi: deps.getUserMedia !== undefined, hasRecorderApi: deps.MediaRecorder !== undefined };
}

function makeAudioContext(): AudioContextLike | null {
  const scope = window as unknown as { AudioContext?: new () => unknown; webkitAudioContext?: new () => unknown };
  const Context = scope.AudioContext ?? scope.webkitAudioContext;
  return Context ? (new Context() as AudioContextLike) : null;
}

function makeWebviewVoice() {
  if (typeof window === "undefined" || !("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
    return undefined;
  }
  const synth = window.speechSynthesis;
  return createWebviewVoice(
    {
      speak: (utterance) => synth.speak(utterance as unknown as SpeechSynthesisUtterance),
      cancel: () => synth.cancel(),
    },
    (text) => {
      const utterance = new SpeechSynthesisUtterance(text);
      const voices = synth.getVoices();
      if (voices.length > 0) {
        const localVoice = voices.find((voice) => voice.localService) || voices.find((voice) => voice.lang.startsWith("en")) || voices[0];
        if (localVoice) utterance.voice = localVoice;
      }
      return utterance as unknown as UtteranceLike;
    },
  );
}

function readSpeakReplies(): boolean {
  try {
    return window.localStorage.getItem(SPEAK_REPLIES_KEY) !== "off";
  } catch {
    return true; // storage can be unavailable; spoken replies are the default
  }
}

function writeSpeakReplies(on: boolean): void {
  try {
    window.localStorage.setItem(SPEAK_REPLIES_KEY, on ? "on" : "off");
  } catch {
    // The choice still holds for this session.
  }
}

// ─── context ─────────────────────────────────────────────────────────────

export interface VoiceValue {
  state: VoiceState;
  /** Why the mic can't be used at all right now; null when it can. */
  unavailableReason: string | null;
  /** One line on what is happening and what the user can do; "" when idle. */
  status: string;
  /** One or two words for a compact indicator; "" when idle. */
  shortStatus: string;
  /** What pressing the mic button does right now. */
  micLabel: string;
  /** The mic button: talk, send, or (while SAM is busy) stop. */
  press: () => void;
  /** Stop listening, working or speaking. */
  stop: () => void;
  dismissError: () => void;
  speakReplies: boolean;
  setSpeakReplies: (on: boolean) => void;
  /** Explicitly speak a text snippet out loud using SAM's voice */
  speak: (text: string) => Promise<void>;
  /** A quiet, one-off message that is not an error; null when there is none. */
  notice: string | null;
  dismissNotice: () => void;
}

const VoiceContext = createContext<VoiceValue | null>(null);

export function VoiceProvider({ children }: { children: ReactNode }) {
  const { sessionTasks, events, health, submitTask, cancelTask } = useTaskSession();
  const [speakReplies, setSpeakRepliesState] = useState<boolean>(readSpeakReplies);
  const [notice, setNotice] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const shownNotices = useRef(new Set<string>());

  const showNotice = useCallback((text: string) => {
    if (shownNotices.current.has(text)) return; // once per session is enough
    shownNotices.current.add(text);
    setNotice(text);
  }, []);

  // The controller outlives renders; it reaches the session's functions
  // through this ref so it never calls a stale one.
  const latest = useRef({ submitTask, cancelTask, showNotice });
  latest.current = { submitTask, cancelTask, showNotice };

  const player = useMemo(() => createAudioPlayer(makeAudioContext), []);
  const webviewSpeak = useMemo(makeWebviewVoice, []);

  const controller = useMemo(
    () =>
      createVoiceController({
        startRecording: (signal) => startRecording(browserRecorderDeps(), { signal }),
        encode: blobToBase64,
        submit: async (request) => {
          const task = await latest.current.submitTask(request);
          return task ? task.task_id : null;
        },
        cancelTask: (taskId) => latest.current.cancelTask(taskId),
        speak: (text, signal, onAudioStart) =>
          speakReply(
            text,
            {
              synthesize: (reply, abortSignal) => speechService.synthesize(reply, abortSignal),
              play: (audio) => player.play(audio),
              webviewSpeak,
              onAudioStart,
              notices: { fallback: FALLBACK_VOICE_NOTICE, unavailable: NO_VOICE_NOTICE },
            },
            signal,
          ),
        unlockAudio: () => player.unlock(),
        stopAudio: () => player.stop(),
        onNotice: (text) => latest.current.showNotice(text),
      }),
    [player, webviewSpeak],
  );

  const state = useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);

  // Leaving (the window closes, or the app unmounts) must not leave the
  // microphone open.
  useEffect(() => () => controller.dispose(), [controller]);

  // When the voice task reaches a final state, say its reply.
  useEffect(() => {
    if (state.kind !== "working") return;
    const task = sessionTasks.find((candidate) => candidate.task_id === state.taskId);
    if (task && TERMINAL_PHASES.has(task.status as never)) controller.taskFinished(task, speakReplies);
  }, [state, sessionTasks, speakReplies, controller]);

  // Esc stops whatever voice is doing.
  const busy = isBusy(state);
  useEffect(() => {
    if (!busy) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const target = event.target;
      if (target instanceof Element && target.closest(
        "[data-quick-assistant], input, textarea, select, [contenteditable='true'], [role='dialog'], [role='listbox']",
      )) return;
      if (!event.defaultPrevented) controller.stop();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, controller]);

  // The microphone must not stay open behind a hidden window.
  const capturing = isCapturing(state);
  useEffect(() => {
    if (!capturing) return;
    const onHidden = () => {
      if (document.visibilityState === "hidden") controller.stop();
    };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", onHidden);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", onHidden);
    };
  }, [capturing, controller]);

  // What the voice task is doing now.
  const voiceTaskId = state.kind === "working" || state.kind === "speaking" ? state.taskId : null;
  const voiceTask = voiceTaskId ? sessionTasks.find((task) => task.task_id === voiceTaskId) : undefined;
  const lastEvent = events.length > 0 ? events[events.length - 1] : undefined;
  const taskMessage = lastEvent && lastEvent.task_id === voiceTaskId ? lastEvent.message : null;
  const phase = voiceTask?.status ?? null;

  // A step that takes a while is probably a first-use download: say so.
  const slowStep = (state.kind === "working" && phase === "perceiving") || (state.kind === "speaking" && state.preparing);
  useEffect(() => {
    setSlow(false);
    if (!slowStep) return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [slowStep, voiceTaskId]);

  const environment = useMemo(browserVoiceEnvironment, []);
  const unavailableReason = micUnavailableReason(environment, health ? health.whisper_available : null);

  const setSpeakReplies = useCallback((on: boolean) => {
    setSpeakRepliesState(on);
    writeSpeakReplies(on);
  }, []);

  const speakText = useCallback(
    async (text: string) => {
      if (!text || !text.trim()) return;
      try {
        const audio = await speechService.synthesize(text);
        await player.play(audio);
      } catch {
        if (webviewSpeak) {
          try {
            await webviewSpeak(text, new AbortController().signal);
          } catch {
            // ignore
          }
        }
      }
    },
    [player, webviewSpeak]
  );

  // Spoken replies for completed tasks in the session when speakReplies is on
  const spokenTaskIds = useRef(new Set<string>());
  useEffect(() => {
    if (!speakReplies) return;
    for (const task of sessionTasks) {
      if (TERMINAL_PHASES.has(task.status as never) && !spokenTaskIds.current.has(task.task_id)) {
        spokenTaskIds.current.add(task.task_id);
        const reply = replyToSpeak(task);
        if (reply) {
          void speakText(reply);
        }
      }
    }
  }, [sessionTasks, speakReplies, speakText]);

  const value = useMemo<VoiceValue>(
    () => ({
      state,
      unavailableReason,
      status: statusText(state, { phase, taskMessage, slow }),
      shortStatus: shortStatus(state),
      micLabel: micLabel(state),
      press: controller.press,
      stop: controller.stop,
      dismissError: controller.dismissError,
      speakReplies,
      setSpeakReplies,
      speak: speakText,
      notice,
      dismissNotice: () => setNotice(null),
    }),
    [state, unavailableReason, phase, taskMessage, slow, controller, speakReplies, setSpeakReplies, speakText, notice],
  );

  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}

export function useVoice(): VoiceValue {
  const value = useContext(VoiceContext);
  if (!value) throw new Error("useVoice must be used within a VoiceProvider");
  return value;
}

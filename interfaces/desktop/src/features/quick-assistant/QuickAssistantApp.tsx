import { useEffect, useRef, useState } from "react";
import { FiSend } from "react-icons/fi";
import { TaskSessionProvider, useTaskSession } from "@/stores/taskSession";
import { StatusPill } from "@/components/StatusPill";
import { Button } from "@/components/Button";
import { phaseToSamState, phaseLabel } from "@/features/iqoo/phase";
import { hideQuickAssistant } from "@/lib/native";
import { VoiceProvider } from "@/features/voice/VoiceProvider";
import { useTaskLabel, VoiceMicButton, VoiceStatusLine } from "@/features/voice/VoiceControls";
import { useVoice } from "@/features/voice/VoiceProvider";
import { isVoiceTask } from "@/features/voice/taskLabel";
import { shouldStopOnQuickAssistantEscape } from "@/features/voice/voiceMachine";

/**
 * The Quick Assistant palette — a second, small native window (global
 * shortcut: Cmd+Shift+Space), not a second app. It talks to the *same*
 * real gateway as the main window, through its own TaskSessionProvider.
 *
 * Known limitation, documented in src-tauri/NATIVE_SHELL_NOTES.md: each
 * Tauri window has its own JS runtime, so this session is a separate
 * TaskSessionProvider instance from the main window's — a task submitted
 * here won't show up in the main window's Tasks list without a refresh
 * there. The gateway and task IDs are the same real ones either way.
 */
function QuickAssistantInner() {
  const { submitTask, submitting, submitError, selectedTask, events } = useTaskSession();
  const { state: voiceState, stop: stopVoice } = useVoice();
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const labelOf = useTaskLabel();

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      // Escape dismisses this palette without withdrawing a command SAM has
      // already received. It still stops capture, submission, and playback.
      if (shouldStopOnQuickAssistantEscape(voiceState)) stopVoice();
      void hideQuickAssistant();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [voiceState, stopVoice]);

  const submit = async () => {
    const trimmed = value.trim();
    if (!trimmed || submitting) return;
    await submitTask({ instruction: trimmed, input_type: "text", attachments: [] });
    setValue("");
  };

  const latestEvent = events[events.length - 1];

  return (
    <div className="flex h-screen flex-col gap-3 bg-void/95 p-3 text-ink backdrop-blur-2xl" data-theme="dark" data-quick-assistant>
      <div className="flex items-center gap-2 rounded-xl border border-line/70 bg-surface/90 p-2 shadow-panel focus-within:border-ember/50 focus-within:ring-1 focus-within:ring-ember/20 transition-all">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submit();
          }}
          placeholder="Ask SAM anything, or tell it to perform a task…"
          className="flex-1 bg-transparent px-2 py-1 text-sm text-ink placeholder:text-mute/60 focus:outline-none"
        />
        <VoiceMicButton blockStart={submitting} />
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={() => void submit()}
          disabled={!value.trim() || submitting}
          aria-label="Send"
          className="h-8 px-3"
        >
          <FiSend size={13} />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto rounded-xl border border-line/70 bg-surface/80 p-3 text-sm shadow-panel">
        <VoiceStatusLine showUnavailable />
        {submitError && <p className="text-danger text-xs">{submitError}</p>}
        {!submitError && selectedTask && (
          <>
            <StatusPill
              state={phaseToSamState(selectedTask.status)}
              label={phaseLabel(selectedTask.status)}
              live
            />
            {isVoiceTask(selectedTask) && (
              <p className="mt-2 text-xs text-mute">You said: “{labelOf(selectedTask)}”</p>
            )}
            <p className="mt-2 whitespace-pre-wrap text-ink text-xs">
              {selectedTask.result_text ?? latestEvent?.message ?? "Working on it…"}
            </p>
          </>
        )}
        {!submitError && !selectedTask && (
          <div className="flex flex-col items-center justify-center h-full text-center py-6 text-xs text-mute/70 space-y-1">
            <p className="font-medium text-ink/80">Autonomous Quick Assistant</p>
            <p>Press Enter to dispatch. Esc to dismiss.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export function QuickAssistantApp() {
  return (
    <TaskSessionProvider>
      <VoiceProvider>
        <QuickAssistantInner />
      </VoiceProvider>
    </TaskSessionProvider>
  );
}

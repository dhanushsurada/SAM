import { useState, type ChangeEvent, type KeyboardEvent } from "react";
import { FiSend } from "react-icons/fi";
import { Button } from "@/components/Button";
import { VoiceMicButton, VoiceSpeakToggle } from "@/features/voice/VoiceControls";

export function ChatComposer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-xl border border-line/70 bg-surface/90 p-2.5 shadow-panel transition-all focus-within:border-ember/50 focus-within:ring-1 focus-within:ring-ember/20">
      <textarea
        value={value}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Message SAM... (Press Enter to send, Shift+Enter for newline)"
        rows={1}
        className="max-h-36 flex-1 resize-none bg-transparent px-2 py-1 text-sm text-ink placeholder:text-mute/60 focus:outline-none"
      />
      <div className="flex items-center gap-1">
        <VoiceSpeakToggle />
        <VoiceMicButton blockStart={disabled} />
        <Button
          variant="primary"
          size="sm"
          onClick={submit}
          disabled={!value.trim() || disabled}
          aria-label="Send message"
          className="h-8 px-3"
        >
          <FiSend size={13} />
        </Button>
      </div>
    </div>
  );
}

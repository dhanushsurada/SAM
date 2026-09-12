import { useState, type ChangeEvent, type KeyboardEvent } from "react";
import { FiSend } from "react-icons/fi";
import { Button } from "@/components/Button";

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
    <div className="flex items-end gap-2 rounded-lg border border-line bg-surface p-2 shadow-panel">
      <textarea
        value={value}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Message SAM (demo)…"
        rows={1}
        className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-mute focus:outline-none"
      />
      <Button variant="primary" size="sm" onClick={submit} disabled={!value.trim() || disabled} aria-label="Send message">
        <FiSend size={14} />
      </Button>
    </div>
  );
}

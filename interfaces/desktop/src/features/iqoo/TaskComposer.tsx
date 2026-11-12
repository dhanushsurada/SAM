import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { FiImage, FiX, FiSend } from "react-icons/fi";
import { Button } from "@/components/Button";
import { fileToBase64Payload } from "@/lib/file";
import { VoiceMicButton, VoiceSpeakToggle, VoiceStatusLine } from "@/features/voice/VoiceControls";
import type { TaskCreateRequest } from "@/api/types";

// Mirrors multimodal/media_validation.py exactly (checked directly, not
// guessed) — client-side rejection here should match server-side rejection
// there, so a failed upload never reaches the network only to bounce.
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const ALLOWED_IMAGE_MIME = new Set(["image/jpeg", "image/png", "image/webp"]);

export interface TaskComposerProps {
  onSubmit: (req: TaskCreateRequest) => Promise<unknown>;
  submitting: boolean;
  presetText?: string;
  onClearPreset?: () => void;
}

export function TaskComposer({ onSubmit, submitting, presetText, onClearPreset }: TaskComposerProps) {
  const [instruction, setInstruction] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  useEffect(() => {
    if (presetText !== undefined && presetText !== "") {
      setInstruction(presetText);
      onClearPreset?.();
    }
  }, [presetText, onClearPreset]);

  useEffect(() => {
    if (!imageFile) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(imageFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  const handleFile = (file: File | undefined) => {
    setImageError(null);
    if (!file) return;
    if (!ALLOWED_IMAGE_MIME.has(file.type)) {
      setImageError("Only JPEG, PNG, or WebP images are accepted.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError(`Image is over the 8 MB limit (${(file.size / 1024 / 1024).toFixed(1)} MB).`);
      return;
    }
    setImageFile(file);
  };

  const canSubmit = instruction.trim().length > 0 && !submitting && !imageError;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    let req: TaskCreateRequest;
    if (imageFile) {
      const { data, mimeType } = await fileToBase64Payload(imageFile);
      req = {
        instruction: instruction.trim(),
        input_type: "image+text",
        attachments: [{ kind: "image", mime_type: mimeType, data, filename: imageFile.name }],
      };
    } else {
      req = { instruction: instruction.trim(), input_type: "text", attachments: [] };
    }

    await onSubmit(req);
    setInstruction("");
    setImageFile(null);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.key === "Enter" && !e.shiftKey) || ((e.metaKey || e.ctrlKey) && e.key === "Enter")) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <div className="rounded-xl border border-line/70 bg-surface/90 p-3 shadow-panel transition-all focus-within:border-ember/50 focus-within:ring-1 focus-within:ring-ember/20">
      <textarea
        value={instruction}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInstruction(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask SAM anything or give an action (e.g. 'take a screenshot and save to desktop', 'open browser')..."
        rows={3}
        maxLength={4000}
        className="w-full resize-none bg-transparent px-2 py-1 text-sm text-ink placeholder:text-mute/60 focus:outline-none"
      />

      {previewUrl && (
        <div className="flex items-center gap-2 p-1.5">
          <img src={previewUrl} alt="Attached" className="h-14 w-14 rounded-lg border border-line object-cover" />
          <button
            type="button"
            onClick={() => setImageFile(null)}
            className="flex items-center gap-1 text-xs text-mute hover:text-danger transition-colors"
          >
            <FiX size={13} /> Remove
          </button>
        </div>
      )}
      {imageError && <p className="px-2 text-xs text-danger">{imageError}</p>}

      <div className="mt-2 flex items-center justify-between border-t border-line/40 pt-2.5">
        <div className="flex items-center gap-1.5">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-lg p-1.5 text-mute hover:bg-void hover:text-ink transition-colors" title="Attach Image">
            <FiImage size={15} />
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e: ChangeEvent<HTMLInputElement>) => handleFile(e.target.files?.[0])}
            />
          </label>
          <VoiceMicButton blockStart={submitting} />
          <VoiceSpeakToggle />
        </div>
        <div className="flex items-center gap-2.5">
          <span className="hidden sm:inline font-mono text-[10px] text-mute/60">
            ↵ to run · ⇧↵ for newline
          </span>
          <Button variant="primary" size="sm" onClick={handleSubmit} disabled={!canSubmit} loading={submitting}>
            <FiSend size={13} /> Run
          </Button>
        </div>
      </div>
      <VoiceStatusLine showUnavailable />
    </div>
  );
}

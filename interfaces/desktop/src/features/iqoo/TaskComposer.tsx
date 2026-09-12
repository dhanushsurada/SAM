import { useEffect, useState, type ChangeEvent } from "react";
import { FiImage, FiMic, FiX, FiSend } from "react-icons/fi";
import { Button } from "@/components/Button";
import { fileToBase64Payload } from "@/lib/file";
import type { TaskCreateRequest } from "@/api/types";

// Mirrors multimodal/media_validation.py exactly (checked directly, not
// guessed) — client-side rejection here should match server-side rejection
// there, so a failed upload never reaches the network only to bounce.
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const ALLOWED_IMAGE_MIME = new Set(["image/jpeg", "image/png", "image/webp"]);

export interface TaskComposerProps {
  onSubmit: (req: TaskCreateRequest) => Promise<void>;
  submitting: boolean;
}

export function TaskComposer({ onSubmit, submitting }: TaskComposerProps) {
  const [instruction, setInstruction] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

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

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <textarea
        value={instruction}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInstruction(e.target.value)}
        placeholder="What should SAM do?"
        rows={3}
        maxLength={4000}
        className="w-full resize-none rounded-md border border-line bg-void px-3 py-2 text-sm text-ink placeholder:text-mute focus:border-ember/50"
      />

      {previewUrl && (
        <div className="flex items-center gap-2">
          <img src={previewUrl} alt="Attached" className="h-14 w-14 rounded-md border border-line object-cover" />
          <button
            type="button"
            onClick={() => setImageFile(null)}
            className="flex items-center gap-1 text-xs text-mute hover:text-ink"
          >
            <FiX size={12} /> Remove
          </button>
        </div>
      )}
      {imageError && <p className="text-xs text-danger">{imageError}</p>}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-md p-2 text-mute hover:bg-void hover:text-ink">
            <FiImage size={16} />
            <span className="sr-only">Attach image</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e: ChangeEvent<HTMLInputElement>) => handleFile(e.target.files?.[0])}
            />
          </label>
          <button
            type="button"
            disabled
            title="Voice input isn't wired up in this build yet"
            className="flex items-center gap-1.5 rounded-md p-2 text-mute/40 cursor-not-allowed"
            aria-label="Voice input (not yet available)"
          >
            <FiMic size={16} />
          </button>
        </div>
        <Button variant="primary" size="sm" onClick={handleSubmit} disabled={!canSubmit} loading={submitting}>
          <FiSend size={14} /> Send
        </Button>
      </div>
    </div>
  );
}

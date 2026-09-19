import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";
import { Card } from "./Card";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Renders the confirm action as `danger` styling. Defaults to true since
   * every current caller (window.confirm's original use case) guards a
   * destructive action — flip to false if a future non-destructive
   * confirmation ever needs this. */
  destructive?: boolean;
  confirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * The styled, accessible confirmation primitive from PHASE5_PLAN.md §E —
 * see §H step 4 for why `IqooPage` used `window.confirm` as a stand-in
 * until this existed. Portaled to `document.body` so `position: fixed`
 * stays relative to the viewport regardless of any transform on an
 * ancestor (e.g. the mobile drawer's slide-in animation in Sidebar).
 *
 * Matches the mobile drawer's existing a11y bar rather than exceeding it:
 * Escape-to-close and initial focus on the panel, but — same honestly-
 * stated limit as that drawer — no full focus trap (Tab can still leave
 * the dialog) and no focus-return-to-trigger on close.
 *
 * The focus/ARIA target (this file's own panelRef div) and the visual
 * card are two elements, not one: Card doesn't forward refs (same as
 * Button), so the behavior lives on a plain wrapper and Card stays
 * purely visual inside it.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = true,
  confirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancelRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // Intentionally just `open`: onCancel is read via the ref above so a
    // new inline callback each render (every caller here passes one)
    // doesn't re-fire this effect and re-steal focus mid-dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 px-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
      >
        <Card padding="md" className="w-full max-w-sm outline-none">
          <h2 id="confirm-dialog-title" className="text-sm font-semibold text-ink">
            {title}
          </h2>
          <p id="confirm-dialog-description" className="mt-2 text-sm text-mute">
            {description}
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={onCancel} disabled={confirming}>
              {cancelLabel}
            </Button>
            <Button variant={destructive ? "danger" : "primary"} size="sm" onClick={onConfirm} loading={confirming}>
              {confirmLabel}
            </Button>
          </div>
        </Card>
      </div>
    </div>,
    document.body,
  );
}

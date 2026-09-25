import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ModeBadge } from "@/components/ModeBadge";
import { Button } from "@/components/Button";
import {
  isNative,
  notificationPermissionState,
  requestNotificationPermission,
  type PermissionStatus,
} from "@/lib/native";

/**
 * Two genuinely different kinds of "permission" live on this one page —
 * kept visibly separate rather than in one flat list, because conflating
 * them is exactly the kind of thing that reads as the desktop app
 * overclaiming what it can see and control:
 *
 *  - Desktop app: this Tauri shell's own OS permissions. Notifications is
 *    the only one relevant to the shell itself, and it's real — checked
 *    and requested through the same plugin bindings native.ts wraps.
 *  - SAM Core: Accessibility, Screen Recording and Microphone belong to
 *    the separate Python process (Hands, vision, Ears). This shell can't
 *    check or request any of them — there's no backend endpoint yet that
 *    reports Core's permission state over the API. Listed here so
 *    there's one place that explains what each is for and who grants it,
 *    not because this page can do anything about them.
 */

interface CorePermission {
  name: string;
  owner: string;
  why: string;
}

const CORE_PERMISSIONS: CorePermission[] = [
  {
    name: "Accessibility",
    owner: "SAM Core — Hands (PyAutoGUI)",
    why: "Lets SAM click, type and control other apps on your behalf.",
  },
  {
    name: "Screen Recording",
    owner: "SAM Core — Hands (vision)",
    why: "Lets SAM read what's on screen to verify actions and understand context.",
  },
  {
    name: "Microphone",
    owner: "SAM Core — Ears (wake word, Whisper)",
    why: "Lets SAM hear its wake word and transcribe speech.",
  },
];

function statusText(status: PermissionStatus): { label: string; className: string } {
  switch (status) {
    case "granted":
      return { label: "Granted", className: "text-success" };
    case "denied":
      return { label: "Denied", className: "text-danger" };
    case "unavailable":
      return { label: "Unavailable", className: "text-mute" };
    case "prompt":
      return { label: "Not granted", className: "text-mute" };
  }
}

export function PermissionsPage() {
  const [notifStatus, setNotifStatus] = useState<PermissionStatus | null>(null);
  const [requesting, setRequesting] = useState(false);

  useEffect(() => {
    notificationPermissionState().then(setNotifStatus);
  }, []);

  const handleRequest = async () => {
    setRequesting(true);
    try {
      setNotifStatus(await requestNotificationPermission());
    } finally {
      setRequesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Permissions"
        description="What SAM and the desktop shell can access on this machine, and why."
      />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-ink">Desktop app</h2>
        <div className="rounded-lg border border-line bg-surface p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-ink">Notifications</span>
                <ModeBadge mode="live" />
              </div>
              <p className="mt-0.5 text-xs text-mute">
                Lets SAM tell you about finished tasks without keeping the window open.
              </p>
            </div>
            <div className="flex items-center gap-3">
              {notifStatus && (
                <span className={`text-sm ${statusText(notifStatus).className}`}>
                  {statusText(notifStatus).label}
                </span>
              )}
              {notifStatus && notifStatus !== "granted" && notifStatus !== "unavailable" && (
                <Button size="sm" variant="secondary" loading={requesting} onClick={() => void handleRequest()}>
                  Request
                </Button>
              )}
            </div>
          </div>
          {!isNative() && (
            <p className="mt-2 text-xs text-mute">
              Running in a plain browser tab right now — this reflects the browser's own
              notification permission, not the native app's. Open SAM as the desktop app to see
              and manage the real one.
            </p>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">SAM Core</h2>
          <ModeBadge mode="demo" />
        </div>
        <p className="text-xs text-mute">
          Granted separately, in System Settings, to the SAM Core process — not requestable or
          checkable from this desktop shell. Listed here so it's in one place; status isn't live
          yet because Core doesn't report it over the API.
        </p>
        <div className="divide-y divide-line rounded-lg border border-line bg-surface">
          {CORE_PERMISSIONS.map((perm) => (
            <div key={perm.name} className="flex items-center justify-between gap-4 p-4">
              <div>
                <span className="text-sm font-medium text-ink">{perm.name}</span>
                <p className="mt-0.5 text-xs text-mute">
                  {perm.owner} — {perm.why}
                </p>
              </div>
              <span className="text-sm text-mute">Not reported</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

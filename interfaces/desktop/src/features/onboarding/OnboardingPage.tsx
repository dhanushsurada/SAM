import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { StatusPill } from "@/components/StatusPill";
import { ModeBadge } from "@/components/ModeBadge";
import { useTaskSession } from "@/stores/taskSession";

const STEPS = ["Welcome", "System check", "Model & voice", "Permissions", "Configuration", "Ready"] as const;

export function OnboardingPage() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { health, healthLoading, healthError, refreshHealth } = useTaskSession();

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <div className="flex min-h-screen items-center justify-center bg-void px-4 py-10 text-ink">
      <div className="w-full max-w-lg space-y-6">
        <div className="flex items-center justify-center gap-1.5">
          {STEPS.map((label, i) => (
            <span
              key={label}
              className={`h-1.5 w-6 rounded-full transition-colors duration-[var(--sam-motion-state)] ${
                i <= step ? "bg-ember" : "bg-line"
              }`}
              aria-hidden="true"
            />
          ))}
        </div>

        <div className="min-h-[280px] rounded-lg border border-line bg-surface p-6 shadow-panel">
          {step === 0 && (
            <div className="space-y-3 text-center">
              <div className="flex items-center justify-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-ember" />
                <h1 className="text-xl font-semibold">Welcome to SAM</h1>
              </div>
              <p className="text-sm text-mute">
                A local-first autonomous assistant. Your conversations, memory, and Founder Mode
                data never leave this machine — ever. Only license verification and software
                updates touch the network, and neither carries personal data.
              </p>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-medium">System check</h2>
                <ModeBadge mode="live" />
              </div>
              <p className="text-sm text-mute">Checking whether SAM's gateway is reachable on port 8420.</p>
              {healthError && (
                <p className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">
                  Can't reach it — make sure you've run the installer and started the server
                  (<code className="font-mono-data">python main.py</code>, or the packaged app).
                </p>
              )}
              {health && !healthError && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-mute">Gateway</span>
                    <StatusPill state="SUCCESS" label="Reachable" />
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-mute">Worker</span>
                    <StatusPill state={health.worker_alive ? "SUCCESS" : "FAILED"} />
                  </div>
                </div>
              )}
              <Button variant="secondary" size="sm" onClick={refreshHealth} loading={healthLoading}>
                Re-check
              </Button>
              <p className="text-xs text-mute">
                This only checks the iQOO gateway — it's the one thing this browser tab can
                actually reach. Not being able to continue past this step isn't required; you can
                set up the rest first and come back.
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <h2 className="text-base font-medium">Model & voice</h2>
              <p className="text-sm text-mute">
                Both happen outside this browser — nothing here can install a model or grant
                microphone access to a native process. Genuinely nothing to verify from a browser
                tab for either, so this step is informational rather than an interactive check
                that would just be theater.
              </p>
              <div className="rounded-md border border-line bg-void px-3 py-2">
                <p className="font-mono-data text-xs text-mute">ollama pull qwen2.5:14b</p>
                <p className="font-mono-data text-xs text-mute">ollama pull qwen2.5:7b # fallback</p>
              </div>
              <p className="text-xs text-mute">
                Wake-word listening runs as a native process on this machine, not through a
                browser tab — there's no permission here for it to request. Voice attachments sent
                through the iQOO phone gateway are a separate, later concept, handled on the phone
                itself.
              </p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <h2 className="text-base font-medium">Permissions</h2>
              <p className="text-sm text-mute">
                Browser/computer control (HANDS) needs OS-level automation permissions — on macOS,
                Accessibility and Screen Recording in System Settings. A browser tab can't check or
                request those on the OS's behalf, so this is a pointer, not a checklist:
              </p>
              <ul className="list-inside list-disc space-y-1 text-sm text-ink">
                <li>System Settings → Privacy &amp; Security → Accessibility</li>
                <li>System Settings → Privacy &amp; Security → Screen Recording</li>
              </ul>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-3">
              <h2 className="text-base font-medium">Configuration</h2>
              <p className="text-sm text-mute">
                Everything else — model choice, voice, memory, integrations — lives in Settings,
                not duplicated here.
              </p>
              <Button variant="secondary" size="sm" onClick={() => navigate("/settings")}>
                Open Settings
              </Button>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-3 text-center">
              <h2 className="text-base font-medium">Ready</h2>
              <p className="text-sm text-mute">
                Command Center is the home screen — its quick input runs on the same live gateway
                you just checked.
              </p>
              <Button variant="primary" onClick={() => navigate("/")}>
                Go to Command Center
              </Button>
            </div>
          )}
        </div>

        <div className="flex justify-between">
          <Button variant="ghost" size="sm" onClick={back} disabled={step === 0}>
            Back
          </Button>
          {step < STEPS.length - 1 && (
            <Button variant="secondary" size="sm" onClick={next}>
              {step === 0 ? "Get started" : "Next"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

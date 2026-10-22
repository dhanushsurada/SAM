import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { StatusPill } from "@/components/StatusPill";
import { ModeBadge } from "@/components/ModeBadge";
import { useTaskSession } from "@/stores/taskSession";
import { useRuntime, useRuntimePolling } from "@/stores/runtime";
import { isNative } from "@/lib/native";

const STEPS = ["Welcome", "System check", "Model & voice", "Permissions", "Configuration", "Ready"] as const;

export function OnboardingPage() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { health, healthLoading, healthError, refreshHealth } = useTaskSession();
  const runtime = useRuntime();
  const native = isNative();
  useRuntimePolling();
  const [modelName, setModelName] = useState("");

  useEffect(() => {
    if (!native) return;
    void runtime.refreshModels();
  }, [native, runtime.refreshModels]);
  useEffect(() => {
    if (!native) return;
    if (step !== 2 || (runtime.models && !runtime.modelsError)) return;
    const timer = setInterval(() => void runtime.refreshModels(), 4000);
    return () => clearInterval(timer);
  }, [native, step, runtime.models, runtime.modelsError, runtime.refreshModels]);
  useEffect(() => {
    if (runtime.models?.selected_model && !modelName) setModelName(runtime.models.selected_model);
  }, [runtime.models, modelName]);

  const next = () => {
    if (step === 0) void runtime.advanceSetupState("in_progress");
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };
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

        <Card padding="lg" className="min-h-[280px]">
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
              <p className="text-sm text-mute">Checking whether the configured SAM gateway is reachable.</p>
              {healthError && (
                <p className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">
                  Can't reach the local SAM API yet. The installed desktop app starts it automatically; check its runtime configuration or retry the API from Settings.
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
              {healthError && native && <Button variant="secondary" size="sm" onClick={() => void runtime.startProcess("api")}>Start SAM API</Button>}
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
              {!native && <p className="text-xs text-mute">Runtime controls are available in the installed SAM desktop app.</p>}
              <p className="text-sm text-mute">Ollama and the installed models are read from SAM's shared runtime state. Downloads may be several GB; review the model name before starting one.</p>
              {runtime.snapshot?.ollama && <p className="text-xs text-mute">Ollama: {runtime.snapshot.ollama.state} — {runtime.snapshot.ollama.detail}</p>}
              {runtime.snapshot?.ollama.state !== "READY" && <Button variant="secondary" size="sm" onClick={() => void runtime.startOllama()}>Start Ollama</Button>}
              <div className="flex gap-2">
                <input aria-label="Model name" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="e.g. qwen2.5:14b" className="min-w-0 flex-1 rounded-md border border-line bg-void px-2 py-1 text-sm" />
                <Button variant="secondary" size="sm" onClick={() => void runtime.refreshModels()} loading={runtime.modelsLoading}>Refresh</Button>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={!modelName || runtime.pulling} onClick={() => void runtime.pullModel(modelName)}>Download model</Button>
                <Button variant="primary" size="sm" disabled={!modelName || runtime.pulling} onClick={() => void runtime.selectModel(modelName)}>Use this model</Button>
              </div>
              {runtime.pullProgress && <p className="text-xs text-mute">{runtime.pullProgress.name}: {runtime.pullProgress.status}{runtime.pullProgress.total ? ` (${Math.round(100 * (runtime.pullProgress.completed ?? 0) / runtime.pullProgress.total)}%)` : ""}</p>}
              {runtime.pullError && <p className="text-xs text-danger">{runtime.pullError}</p>}
              {runtime.modelsError && <p className="text-xs text-danger">{runtime.modelsError}</p>}
              <p className="text-xs text-mute">Configured primary: {runtime.models?.selected_model ?? "loading"}; installed: {runtime.models?.models.map((m) => m.name).join(", ") || "none detected"}.</p>
              <p className="text-xs text-mute">Voice permissions and wake-word controls are managed separately by macOS and SAM's runtime.</p>
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
              <Button variant="primary" onClick={() => { void runtime.advanceSetupState("complete", modelName || runtime.models?.selected_model); navigate("/"); }}>
                Go to Command Center
              </Button>
            </div>
          )}
        </Card>

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

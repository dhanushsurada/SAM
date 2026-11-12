import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { StatusPill } from "@/components/StatusPill";
import { ModeBadge } from "@/components/ModeBadge";
import { useTaskSession } from "@/stores/taskSession";
import { useRuntime, useRuntimePolling } from "@/stores/runtime";
import { isNative, openOllamaDownload, repairRuntimeConfiguration } from "@/lib/native";
import { getEnvironmentReport, repairEnvironment, type EnvironmentReport } from "@/api/client";

const STEPS = ["Welcome", "System check", "Model & voice", "Permissions", "Configuration", "Ready"] as const;

const RECOMMENDED_MODELS = [
  { name: "qwen2.5:14b", label: "Qwen 2.5 14B", desc: "Recommended · Advanced reasoning & tool execution", size: "9.0 GB" },
  { name: "qwen2.5:7b", label: "Qwen 2.5 7B", desc: "Balanced · Fast responses & efficient", size: "4.7 GB" },
  { name: "llama3.2:3b", label: "Llama 3.2 3B", desc: "Lightweight · Fast intent & low RAM", size: "2.0 GB" },
] as const;

export function OnboardingPage() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { health, healthLoading, healthError, refreshHealth } = useTaskSession();
  const runtime = useRuntime();
  const native = isNative();
  useRuntimePolling();
  const [modelName, setModelName] = useState("");
  const [environment, setEnvironment] = useState<EnvironmentReport | null>(null);
  const [environmentError, setEnvironmentError] = useState<string | null>(null);
  const [confirmPull, setConfirmPull] = useState(false);
  const [ollamaActionMessage, setOllamaActionMessage] = useState<string | null>(null);
  const [runtimeRepairMessage, setRuntimeRepairMessage] = useState<string | null>(null);
  const [voiceInstalling, setVoiceInstalling] = useState(false);
  const [voiceMessage, setVoiceMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!native) return;
    void runtime.refreshModels();
  }, [native, runtime.refreshModels]);
  useEffect(() => {
    if (!native || (step !== 1 && step !== 2)) return;
    let active = true;
    getEnvironmentReport().then((report) => { if (active) { setEnvironment(report); setEnvironmentError(null); } })
      .catch((error: unknown) => { if (active) setEnvironmentError(error instanceof Error ? error.message : "Environment status is unavailable."); });
    return () => { active = false; };
  }, [native, step]);
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
  const startOllama = async () => {
    setOllamaActionMessage(null);
    try {
      const result = await runtime.startOllama();
      setOllamaActionMessage(result.message);
    } catch (error) {
      setOllamaActionMessage(error instanceof Error ? error.message : "Could not start Ollama.");
    }
  };
  const getOllama = async () => {
    setOllamaActionMessage(null);
    try {
      setOllamaActionMessage(await openOllamaDownload());
    } catch (error) {
      setOllamaActionMessage(error instanceof Error ? error.message : "Could not open Ollama's installation route.");
    }
  };
  const repairRuntime = async () => {
    setRuntimeRepairMessage(null);
    try {
      await repairRuntimeConfiguration();
      await runtime.startProcess("api");
      await runtime.refresh();
      setRuntimeRepairMessage("SAM runtime setup was repaired and the API start was requested.");
      await refreshHealth();
    } catch (error) {
      setRuntimeRepairMessage(error instanceof Error ? error.message : "Reinstall SAM from its DMG, then try again.");
    }
  };
  const installedModel = Boolean(runtime.models?.models.some((model) => model.name === modelName));

  const installVoice = async () => {
    setVoiceInstalling(true);
    setVoiceMessage(null);
    try {
      await repairEnvironment(["speech-input", "speech-output"]);
      const updated = await getEnvironmentReport();
      setEnvironment(updated);
      setVoiceMessage("Voice touch-to-talk & TTS capabilities installed successfully.");
    } catch (error) {
      setVoiceMessage(error instanceof Error ? error.message : "Voice installation failed.");
    } finally {
      setVoiceInstalling(false);
    }
  };

  const voiceReady = Boolean(
    environment?.dependencies?.["speech-input"]?.available &&
    environment?.dependencies?.["speech-output"]?.available
  );

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
              {environmentError && <p role="alert" className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">Environment details could not be loaded: {environmentError}</p>}
              {environment && <div className="space-y-1 rounded-md border border-line bg-void p-2 text-xs">
                <p className="text-mute">{environment.environment.os.name} {environment.environment.os.version} · Python {environment.environment.python.current} · {environment.environment.hardware.disk.free_gb ?? "?"} GB free</p>
                {!environment.environment.python.selected.supported && <p className="text-danger">A supported Python interpreter is unavailable. {environment.environment.python.selected.detail}</p>}
                {environment.diagnostics.filter((issue) => issue.severity === "error").map((issue, index) => <p key={index} className="text-danger">{issue.message}</p>)}
                {Object.entries(environment.capabilities.features).filter(([, capability]) => !capability.available).map(([name, capability]) => <p key={name} className="text-mute">{name} is unavailable: {capability.reason}</p>)}
              </div>}
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
              {native && runtime.error && <div className="space-y-2">
                <p role="alert" className="text-xs text-danger">Desktop runtime: {runtime.error}</p>
                <Button variant="secondary" size="sm" onClick={() => void repairRuntime()}>Repair runtime setup</Button>
                {runtimeRepairMessage && <p role="status" className="text-xs text-mute">{runtimeRepairMessage}</p>}
              </div>}
              <p className="text-xs text-mute">
                This checks the SAM API gateway — the core service managing tasks and model routing.
                You can continue onboarding or adjust settings at any time.
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <h2 className="text-base font-medium">Model & voice</h2>
              {!native && <p className="text-xs text-mute">Runtime controls are available in the installed SAM desktop app.</p>}
              <p className="text-sm text-mute">Choose a local LLM model and enable the voice speech engine so SAM is completely ready.</p>
              {environment && <p className={`text-xs ${environment.environment.hardware.disk.free_gb !== null && environment.environment.hardware.disk.free_gb < 15 ? "text-warn" : "text-mute"}`}>
                {environment.environment.hardware.disk.free_gb ?? "Unknown"} GB free on the home volume. Model size varies; Ollama reports byte progress after you start a download.
              </p>}
              {runtime.snapshot?.ollama && <p className="text-xs text-mute">Ollama: {runtime.snapshot.ollama.state} — {runtime.snapshot.ollama.detail}</p>}
              {runtime.snapshot?.ollama.state === "NOT_INSTALLED" && <div className="space-y-2 rounded-md border border-line bg-void p-3">
                <p className="text-sm text-ink">Ollama is needed for local models. SAM does not bundle it.</p>
                <p className="text-xs text-mute">Install Ollama for your operating system using its official installer or instructions. SAM does not bundle it. You may also connect to an Ollama server configured in Settings.</p>
                <Button variant="secondary" size="sm" onClick={() => void getOllama()}>Get Ollama</Button>
              </div>}
              {runtime.snapshot?.ollama.state === "STOPPED" && <div className="space-y-2">
                <p className="text-xs text-mute">Ollama is installed but not responding. Start it or check the configured host.</p>
                <Button variant="secondary" size="sm" onClick={() => void startOllama()}>Start Ollama</Button>
              </div>}
              {runtime.snapshot?.ollama.state === "READY" && runtime.models?.models.length === 0 && <p className="text-xs text-warn">No model is installed. Model-backed chat, planning, and other Brain features stay unavailable until you choose and download a model.</p>}
              {ollamaActionMessage && <p role="status" className="text-xs text-mute">{ollamaActionMessage}</p>}

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-mute">Recommended Models</label>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
                  {RECOMMENDED_MODELS.map((m) => {
                    const isSelected = modelName === m.name;
                    const isInstalled = Boolean(runtime.models?.models.some((installed) => installed.name === m.name));
                    return (
                      <button
                        key={m.name}
                        type="button"
                        onClick={() => setModelName(m.name)}
                        className={`flex flex-col items-start rounded-md border p-2 text-left transition-colors ${
                          isSelected
                            ? "border-ember bg-ember/10 text-ink"
                            : "border-line bg-void hover:border-line-hover text-mute"
                        }`}
                      >
                        <div className="flex w-full items-center justify-between">
                          <span className="text-xs font-semibold text-ink">{m.label}</span>
                          <span className="text-[10px] text-mute">{m.size}</span>
                        </div>
                        <span className="mt-1 text-[11px] leading-tight text-mute">{m.desc}</span>
                        {isInstalled && (
                          <span className="mt-1.5 text-[10px] font-medium text-success">✓ Installed</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex gap-2">
                <input aria-label="Model name" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="e.g. qwen2.5:14b" className="min-w-0 flex-1 rounded-md border border-line bg-void px-2 py-1 text-sm" />
                <Button variant="secondary" size="sm" onClick={() => void runtime.refreshModels()} loading={runtime.modelsLoading}>Refresh</Button>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={!modelName.trim() || runtime.pulling || runtime.snapshot?.ollama.state !== "READY"} onClick={() => setConfirmPull(true)}>{runtime.pullError ? "Retry model download" : "Download model"}</Button>
                {runtime.pulling && <Button variant="ghost" size="sm" onClick={() => void runtime.cancelPull()}>Cancel download</Button>}
                <Button variant="primary" size="sm" disabled={!installedModel || runtime.pulling} onClick={() => void runtime.selectModel(modelName)}>Use this model</Button>
              </div>
              {runtime.pullProgress && <p className="text-xs text-mute">{runtime.pullProgress.name}: {runtime.pullProgress.status}{runtime.pullProgress.total ? ` (${Math.round(100 * (runtime.pullProgress.completed ?? 0) / runtime.pullProgress.total)}%)` : ""}</p>}
              {runtime.pullError && <p className="text-xs text-danger">{runtime.pullError}</p>}
              {runtime.modelsError && <p className="text-xs text-danger">{runtime.modelsError}</p>}
              <p className="text-xs text-mute">Configured primary: {runtime.models?.selected_model ?? "loading"}; installed: {runtime.models?.models.map((m) => m.name).join(", ") || "none detected"}.</p>

              <div className="space-y-2 rounded-md border border-line bg-void p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-ink">Touch-to-Talk Voice Engine</span>
                    <span className="text-[10px] text-mute">(Whisper STT + Kokoro TTS)</span>
                  </div>
                  <StatusPill state={voiceReady ? "SUCCESS" : "UNAVAILABLE"} label={voiceReady ? "Ready" : "Not Installed"} />
                </div>
                <p className="text-xs text-mute">
                  Enables microphone voice messages and spoken responses without third-party cloud audio services.
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={voiceInstalling || voiceReady}
                    loading={voiceInstalling}
                    onClick={() => void installVoice()}
                  >
                    {voiceReady ? "Voice Ready" : "Download & Enable Voice"}
                  </Button>
                  {voiceMessage && (
                    <span className="text-xs text-mute truncate">{voiceMessage}</span>
                  )}
                </div>
              </div>
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

        <ConfirmDialog
          open={confirmPull}
          title="Download this model?"
          description={`Ollama will download ${modelName || "the selected model"}. Model downloads can require several gigabytes of storage and network data. Review available disk space above before confirming. You can cancel and retry later.`}
          confirmLabel="Download model"
          destructive={false}
          onConfirm={() => { setConfirmPull(false); if (modelName.trim()) void runtime.pullModel(modelName.trim()); }}
          onCancel={() => setConfirmPull(false)}
        />

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

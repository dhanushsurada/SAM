import { useEffect, useState, type ChangeEvent } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/Card";
import { Switch } from "@/components/Switch";
import { SETTINGS_SCHEMA, type SettingField } from "./types";
import { useRuntime, useRuntimePolling } from "@/stores/runtime";
import { Button } from "@/components/Button";
import { isNative, launchAtLoginEnabled, setLaunchAtLogin } from "@/lib/native";
import { getSettings, updateSettings } from "@/api/client";

type FormState = Record<string, string | number | boolean>;

// Stacks label-over-control below sm rather than a fixed-width input beside
// a label — at narrow widths (this page has long labels: "Founder Mode
// classifier model" etc.) side-by-side was tight against a fixed w-48
// input. Found by re-reading the layout with a phone-width viewport in
// mind, not by running one.
const ROW = "flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3";

function initialState(): FormState {
  const state: FormState = {};
  for (const section of SETTINGS_SCHEMA) {
    for (const field of section.fields) state[field.key] = field.default;
  }
  return state;
}

function Field({
  field,
  value,
  onChange,
}: {
  field: SettingField;
  value: string | number | boolean;
  onChange: (v: string | number | boolean) => void;
}) {
  if (field.type === "path") {
    return (
      <div className={ROW}>
        <span className="text-sm text-mute">{field.label}</span>
        <span className="truncate font-mono-data text-xs text-unverified">{String(value)}</span>
      </div>
    );
  }

  if (field.type === "readonly") {
    return (
      <div className={ROW}>
        <div>
          <p className="text-sm text-mute">{field.label}</p>
          {field.description && <p className="text-xs text-mute">{field.description}</p>}
        </div>
        <span className="font-mono-data text-xs text-unverified">{String(value)}</span>
      </div>
    );
  }

  if (field.type === "toggle") {
    return (
      <div className={ROW}>
        <div>
          <p className="text-sm text-ink">{field.label}</p>
          {field.description && <p className="text-xs text-mute">{field.description}</p>}
        </div>
        <Switch checked={Boolean(value)} onChange={onChange} label={field.label} />
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <div className={ROW}>
        <span className="text-sm text-ink">{field.label}</span>
        <select
          value={String(value)}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
          className="w-full rounded-md border border-line bg-void px-2 py-1 text-sm text-ink sm:w-auto"
        >
          {field.options?.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={ROW}>
      <div>
        <span className="text-sm text-ink">{field.label}</span>
        {field.description && <p className="text-xs text-mute">{field.description}</p>}
      </div>
      <input
        type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
        value={String(value)}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(field.type === "number" ? Number(e.target.value) : e.target.value)
        }
        className="w-full rounded-md border border-line bg-void px-2 py-1 text-sm text-ink sm:w-48 sm:text-right"
      />
    </div>
  );
}

export function SettingsPage() {
  const [values, setValues] = useState<FormState>(initialState);
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [launchAtLogin, setLaunchAtLoginValue] = useState<boolean | null>(null);
  const [launchAtLoginError, setLaunchAtLoginError] = useState<string | null>(null);
  const [pullName, setPullName] = useState("");
  const runtime = useRuntime();
  useRuntimePolling();

  useEffect(() => {
    let current = true;
    void getSettings().then((stored) => {
      if (!current) return;
      setValues((previous) => ({ ...previous, ...Object.fromEntries(
        Object.entries(stored).map(([key, value]) => [key, value ?? ""])
      ) }));
      setSettingsMessage(null);
    }).catch(() => {
      if (current) setSettingsMessage("Saved settings could not be loaded. Check that SAM is running.");
    }).finally(() => { if (current) setSettingsLoading(false); });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    if (!isNative()) return;
    void runtime.refreshModels();
  }, [runtime.refreshModels]);

  useEffect(() => {
    if (!isNative()) return;
    void launchAtLoginEnabled().then(setLaunchAtLoginValue).catch((error) => {
      setLaunchAtLoginError(error instanceof Error ? error.message : "Could not read startup preference.");
    });
  }, []);

  const setField = (key: string, value: string | number | boolean) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setDirty((prev) => new Set(prev).add(key));
    setSettingsMessage(null);
  };

  const saveSettings = async () => {
    if (dirty.size === 0) return;
    setSettingsSaving(true);
    try {
      const changed = Object.fromEntries([...dirty].map((key) => [key, values[key]]));
      await updateSettings(changed);
      setDirty(new Set());
      setSettingsMessage("Settings saved. Incognito applies to this session only.");
    } catch (error) {
      setSettingsMessage(error instanceof Error ? `Could not save settings: ${error.message}` : "Could not save settings.");
    } finally {
      setSettingsSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        title="Settings"
        mode="live"
        description="Settings are saved to this device and shared with SAM's runtime. Password fields are never shown after saving."
      />

      <Card as="section" className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-ink">{settingsLoading ? "Loading saved settings…" : dirty.size ? `${dirty.size} unsaved change${dirty.size === 1 ? "" : "s"}` : "Settings are up to date"}</p>
          {settingsMessage && <p role="status" className="mt-1 text-xs text-mute">{settingsMessage}</p>}
          <p className="mt-1 text-xs text-mute">Leave a password field blank to keep its saved value. API host and port are read-only here; incognito is session-only.</p>
        </div>
        <Button variant="primary" size="sm" disabled={settingsLoading || settingsSaving || dirty.size === 0} onClick={() => void saveSettings()} loading={settingsSaving}>Save settings</Button>
      </Card>

      {isNative() && <Card as="section" className="space-y-3">
        <div>
          <h2 className="text-sm font-medium text-ink">Live runtime and models</h2>
          <p className="text-xs text-mute">These controls use the same runtime state as onboarding.</p>
        </div>
        {runtime.error && <p className="text-xs text-danger">Runtime status: {runtime.error}</p>}
        <p className="text-xs text-mute">API: {runtime.snapshot?.processes.api?.state ?? (runtime.loading ? "checking" : "unknown")} · Ollama: {runtime.snapshot?.ollama.state ?? "unknown"}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => void runtime.startProcess("api")}>Start SAM API</Button>
          <Button variant="secondary" size="sm" onClick={() => void runtime.startOllama()}>Start Ollama</Button>
          <Button variant="ghost" size="sm" onClick={() => { void runtime.refresh(); void runtime.refreshModels(); }}>Refresh status</Button>
        </div>
        <div className="flex items-center justify-between border-t border-line pt-3">
          <div>
            <p className="text-sm text-ink">Open SAM at login</p>
            <p className="text-xs text-mute">SAM will start its backend when the desktop app opens.</p>
            {launchAtLoginError && <p className="text-xs text-danger">{launchAtLoginError}</p>}
          </div>
          <Switch
            checked={launchAtLogin ?? false}
            disabled={launchAtLogin === null}
            onChange={(enabled) => {
              setLaunchAtLoginError(null);
              void setLaunchAtLogin(enabled).then(setLaunchAtLoginValue).catch((error) => {
                setLaunchAtLoginError(error instanceof Error ? error.message : "Could not update startup preference.");
              });
            }}
            label="Open SAM at login"
          />
        </div>
        {runtime.models && <>
          <p className="text-xs text-mute">Selected: {runtime.models.selected_model} · Active: {runtime.models.active_model ?? "none"}</p>
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label="Select installed model" value={runtime.models.selected_model} onChange={(e) => void runtime.selectModel(e.target.value)} className="rounded-md border border-line bg-void px-2 py-1 text-sm text-ink">
              {runtime.models.models.filter((model) => model.compatibility !== "incompatible").map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}
            </select>
            <Button variant="ghost" size="sm" onClick={() => void runtime.refreshModels()}>Refresh models</Button>
          </div>
        </>}
        <div className="flex flex-wrap gap-2">
          <input aria-label="Model to download" value={pullName} onChange={(e) => setPullName(e.target.value)} placeholder="Model name (downloads can be large)" className="min-w-0 flex-1 rounded-md border border-line bg-void px-2 py-1 text-sm text-ink" />
          <Button variant="secondary" size="sm" disabled={!pullName || runtime.pulling} onClick={() => void runtime.pullModel(pullName)}>Download model</Button>
        </div>
        {runtime.pullProgress && <p className="text-xs text-mute">{runtime.pullProgress.name}: {runtime.pullProgress.status}{runtime.pullProgress.total ? ` (${Math.round(100 * (runtime.pullProgress.completed ?? 0) / runtime.pullProgress.total)}%)` : ""}</p>}
        {(runtime.pullError || runtime.modelsError) && <p className="text-xs text-danger">{runtime.pullError || runtime.modelsError}</p>}
      </Card>}

      <nav className="flex flex-wrap gap-x-3 gap-y-1 border-b border-line pb-3 text-xs text-mute">
        {SETTINGS_SCHEMA.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="hover:text-ember-text">
            {s.title}
          </a>
        ))}
      </nav>

      {SETTINGS_SCHEMA.map((section) => (
        <Card as="section" key={section.id} id={section.id} className="scroll-mt-4 space-y-1">
          <h2 className="text-sm font-medium text-ink">{section.title}</h2>
          {section.note && (
            <p
              className={`rounded-md border px-3 py-2 text-xs ${
                section.note.tone === "danger"
                  ? "border-danger/25 bg-danger/5 text-danger"
                  : "border-warn/25 bg-warn/5 text-warn"
              }`}
            >
              {section.note.text}
            </p>
          )}
          <div className="divide-y divide-line">
            {section.fields.map((field) => (
              <Field key={field.key} field={field} value={values[field.key]} onChange={(v) => setField(field.key, v)} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

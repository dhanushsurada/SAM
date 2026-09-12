import { useState, type ChangeEvent } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Switch } from "@/components/Switch";
import { SETTINGS_SCHEMA, type SettingField } from "./types";

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

  const setField = (key: string, value: string | number | boolean) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        title="Settings"
        mode="demo"
        description="Every field and default here comes straight from config/settings.py. Editable locally for preview — nothing here is saved anywhere: Settings.save() writes a local YAML file directly, which a browser has no endpoint to reach yet."
      />

      <nav className="flex flex-wrap gap-x-3 gap-y-1 border-b border-line pb-3 text-xs text-mute">
        {SETTINGS_SCHEMA.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="hover:text-ember-text">
            {s.title}
          </a>
        ))}
      </nav>

      {SETTINGS_SCHEMA.map((section) => (
        <section
          key={section.id}
          id={section.id}
          className="scroll-mt-4 space-y-1 rounded-lg border border-line bg-surface p-4 shadow-panel"
        >
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
        </section>
      ))}
    </div>
  );
}

import type { BrainStatus, ModelInfo } from "@/api/types";

/** Pure view helpers for the Brain screens — no React, no fetching, so the
 * rules for what a row says and when it can be switched to live in one
 * place. */

export function formatBytes(bytes: number | null): string | null {
  if (bytes === null) return null;
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

export function formatContext(tokens: number | null): string | null {
  if (tokens === null) return null;
  return tokens >= 1024 ? `${Math.round(tokens / 1024)}K context` : `${tokens} context`;
}

/** The facts worth showing under a model's name, in reading order. Only
 * what the server actually reported — nothing is inferred from the name. */
export function modelMeta(m: ModelInfo): string[] {
  const parts: Array<string | null> = [
    m.family,
    m.parameter_size,
    m.quantization,
    formatBytes(m.size_bytes),
    formatContext(m.context_length),
  ];
  return parts.filter((p): p is string => p !== null && p !== "");
}

/** Why a model can't be switched to right now, or null if it can. */
export function switchBlockedReason(status: BrainStatus, m: ModelInfo): string | null {
  if (status.busy) return "A task is running. Wait for it to finish before switching.";
  if (m.compatibility === "incompatible") return m.compatibility_reason;
  return null;
}

const OVERRIDE_LABELS: Record<string, string> = {
  planner: "Planner",
  reflection: "Reflection",
  founder_classifier: "Founder Mode classifier",
};

/** One line per subsystem pinned to its own model. */
export function describeOverrides(overrides: Record<string, string>): string[] {
  return Object.keys(overrides).map((key) => `${OVERRIDE_LABELS[key] ?? key} uses ${overrides[key]}`);
}

/** Wording for where the active model came from. */
export function activeSourceLabel(status: BrainStatus): string | null {
  if (status.active_source === "fallback") return "fallback: the selected model isn't installed";
  if (status.active_source === "selected") return status.user_selected ? "chosen by you" : "SAM's default";
  return null;
}

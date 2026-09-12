import type { FC } from "react";
import {
  FiHome,
  FiMessageSquare,
  FiCheckSquare,
  FiSmartphone,
  FiDatabase,
  FiUser,
  FiZap,
  FiCpu,
  FiActivity,
  FiSettings,
  FiKey,
} from "react-icons/fi";

export type SamIcon = FC<{ className?: string; size?: number | string }>;

export type NavGroup = "assistant" | "iqoo" | "understanding" | "system" | "settings";

export interface RouteMeta {
  path: string;
  label: string;
  icon: SamIcon;
  group: NavGroup;
  /** Which step of docs/frontend/PHASE5_PLAN.md §H builds the real version
   * of this screen. Shown on the stub page so "not built" always says when
   * it's coming, not just that it's missing. */
  plannedStep: string;
  description: string;
}

export const GROUP_LABELS: Record<Exclude<NavGroup, "settings">, string> = {
  assistant: "Assistant",
  iqoo: "iQOO",
  understanding: "Understanding",
  system: "System",
};

// Order here is render order, both in the sidebar and (via the .find in
// router.tsx) implicitly in route registration.
export const ROUTES: RouteMeta[] = [
  {
    path: "/",
    label: "Command Center",
    icon: FiHome,
    group: "assistant",
    plannedStep: "Step 5",
    description:
      "System status, current model, recent tasks, and a quick command/task input — SAM's home screen.",
  },
  {
    path: "/chat",
    label: "Chat",
    icon: FiMessageSquare,
    group: "assistant",
    plannedStep: "Step 6",
    description:
      "Conversational interface. The one screen waiting on a capability that doesn't exist yet anywhere in the backend, not just an unwired endpoint — see PHASE5_PLAN.md §A/§F.",
  },
  {
    path: "/tasks",
    label: "Tasks",
    icon: FiCheckSquare,
    group: "assistant",
    plannedStep: "Step 4",
    description:
      "Task Execution / Agent Console, as a general concept independent of source. Right now the only task source is iQOO — see the iQOO workspace for live tasks until there's more than one source to unify here.",
  },
  {
    path: "/iqoo",
    label: "iQOO",
    icon: FiSmartphone,
    group: "iqoo",
    plannedStep: "Step 4",
    description: "Phone gateway workspace — the one section built on a real, live backend today.",
  },
  {
    path: "/memory",
    label: "Memory",
    icon: FiDatabase,
    group: "understanding",
    plannedStep: "Step 7",
    description: "Episodic and semantic memory, search and browse.",
  },
  {
    path: "/founder-mode",
    label: "Founder Mode",
    icon: FiUser,
    group: "understanding",
    plannedStep: "Step 7",
    description: "Decisions, reflections, taste profile — SAM's persistent understanding of you.",
  },
  {
    path: "/skills",
    label: "Skills",
    icon: FiZap,
    group: "understanding",
    plannedStep: "Step 7",
    description: "Compiled skills library and status.",
  },
  {
    path: "/models",
    label: "Models",
    icon: FiCpu,
    group: "system",
    plannedStep: "Step 7",
    description: "Active and fallback model, Ollama availability.",
  },
  {
    path: "/diagnostics",
    label: "Diagnostics",
    icon: FiActivity,
    group: "system",
    plannedStep: "Step 7",
    description: "sam doctor–style PASS/WARN/FAIL/UNVERIFIED status for every subsystem.",
  },
  {
    path: "/licensing",
    label: "Licensing",
    icon: FiKey,
    group: "system",
    plannedStep: "Step 7",
    description: "License and activation state.",
  },
  {
    path: "/settings",
    label: "Settings",
    icon: FiSettings,
    group: "settings",
    plannedStep: "Step 8",
    description: "General, model, voice, memory, runtime, and privacy configuration.",
  },
];

export function findRoute(pathname: string): RouteMeta | undefined {
  return ROUTES.find((r) => r.path === pathname);
}

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
  FiMousePointer,
  FiActivity,
  FiSettings,
  FiKey,
} from "react-icons/fi";

export type SamIcon = FC<{ className?: string; size?: number | string }>;

export type NavGroup = "assistant" | "core" | "workspaces" | "understanding" | "system" | "settings";

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

// SAM is the product; the Brain and Hands are what it's made of; a workspace
// is one workflow built on top of them. Nothing here makes the browser or a
// single competition workflow the frame around everything else.
export const GROUP_LABELS: Record<Exclude<NavGroup, "settings">, string> = {
  assistant: "Assistant",
  core: "Brain and Hands",
  workspaces: "Workspaces",
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
      "Conversational view over SAM's task pipeline: each message runs as a task and SAM's reply is its outcome. Single-turn — no conversation history reaches the Brain.",
  },
  {
    path: "/tasks",
    label: "Tasks",
    icon: FiCheckSquare,
    group: "assistant",
    plannedStep: "Step 4",
    description:
      "General task console: request to outcome, with the lifecycle, live progress, cancel and retry.",
  },
  {
    path: "/brain",
    label: "Brain",
    icon: FiCpu,
    group: "core",
    plannedStep: "Brain pass",
    description: "The local model SAM thinks with: what's installed in Ollama, which one is active, and switching it.",
  },
  {
    path: "/hands",
    label: "Hands",
    icon: FiMousePointer,
    group: "core",
    plannedStep: "Brain pass",
    description: "How SAM acts on a computer: desktop control, vision, browser, terminal and verification.",
  },
  {
    path: "/iqoo",
    label: "iQOO Workspace",
    icon: FiSmartphone,
    group: "workspaces",
    plannedStep: "Step 4",
    description: "Phone to PC workflow: the gateway a phone sends tasks to, its health, and the demo controls.",
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

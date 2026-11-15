export type AuthMethod =
  | "founder"
  | "passkey"
  | "email_otp"
  | "phone_sms"
  | "guest"
  | "local_token";

export type PlatformId =
  | "telegram"
  | "instagram"
  | "whatsapp"
  | "twitter"
  | "linkedin"
  | "github"
  | "traceop";

export interface ConnectedPlatform {
  id: PlatformId;
  name: string;
  category: "messaging" | "social" | "code" | "intelligence";
  handle: string;
  connected: boolean;
  connectedAt?: string;
  syncMessages: boolean;
  syncContext: boolean;
  statusText?: string;
  syncedFactsCount?: number;
}

export interface TraceOpPersonaAnalysis {
  analyzedAt: string;
  overallScore: number; // 0 - 100%
  executiveSummary: string;
  communicationStyle: string;
  toneAndDemeanor: string;
  activeHours: string;
  keyInterests: string[];
  cognitivePreferences: string[];
  crossPlatformFootprint: { platform: string; activityMetric: string }[];
}

export interface UserProfile {
  id: string;
  name: string;
  handle: string;
  email: string;
  isEmailVerified: boolean;
  phone?: string;
  isPhoneVerified: boolean;
  role: string;
  bio: string;
  avatar: string;        // Initials or emoji (e.g. "DS", "⚡", "🛡️", "💎")
  avatarBg?: string;
  isSignedIn: boolean;
  authMethod: AuthMethod;
  sessionStartedAt: string;
  lastActiveAt: string;
  incognitoMode: boolean;
  nodeId: string;
  deviceKeyFingerprint: string;
  connectedPlatforms: ConnectedPlatform[];
  personaAnalysis?: TraceOpPersonaAnalysis;
}

export const FOUNDER_CONNECTED_PLATFORMS: ConnectedPlatform[] = [
  {
    id: "telegram",
    name: "Telegram",
    category: "messaging",
    handle: "@dhanush",
    connected: true,
    connectedAt: "2026-10-12T10:00:00Z",
    syncMessages: true,
    syncContext: true,
    statusText: "Direct context tunnel active",
    syncedFactsCount: 38,
  },
  {
    id: "instagram",
    name: "Instagram",
    category: "social",
    handle: "@dhanushsurada",
    connected: true,
    connectedAt: "2026-10-15T14:30:00Z",
    syncMessages: false,
    syncContext: true,
    statusText: "Story and visual interests synced",
    syncedFactsCount: 19,
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    category: "messaging",
    handle: "+91 98765 43210",
    connected: true,
    connectedAt: "2026-10-20T09:15:00Z",
    syncMessages: true,
    syncContext: true,
    statusText: "End-to-end encrypted notes stream",
    syncedFactsCount: 47,
  },
  {
    id: "traceop",
    name: "TraceOp Profiler",
    category: "intelligence",
    handle: "traceop:usr_dhanush_sovereign",
    connected: true,
    connectedAt: "2026-11-01T11:00:00Z",
    syncMessages: false,
    syncContext: true,
    statusText: "Deep cross-platform persona intelligence active",
    syncedFactsCount: 94,
  },
  {
    id: "github",
    name: "GitHub",
    category: "code",
    handle: "@dhanushsurada",
    connected: true,
    connectedAt: "2026-10-01T08:00:00Z",
    syncMessages: false,
    syncContext: true,
    statusText: "Repositories and commit tone indexed",
    syncedFactsCount: 112,
  },
  {
    id: "twitter",
    name: "X (Twitter)",
    category: "social",
    handle: "@dhanushsurada",
    connected: true,
    connectedAt: "2026-10-05T18:20:00Z",
    syncMessages: false,
    syncContext: true,
    statusText: "Public discourse & tech takes indexed",
    syncedFactsCount: 52,
  },
  {
    id: "linkedin",
    name: "LinkedIn",
    category: "social",
    handle: "dhanushsurada",
    connected: true,
    connectedAt: "2026-10-08T12:00:00Z",
    syncMessages: false,
    syncContext: true,
    statusText: "Professional accomplishments & network mapped",
    syncedFactsCount: 28,
  },
];

export const FOUNDER_PERSONA_ANALYSIS: TraceOpPersonaAnalysis = {
  analyzedAt: "2026-11-15T10:00:00Z",
  overallScore: 96,
  executiveSummary:
    "Visionary sovereign systems architect and high-agency product builder. Prefers deep autonomous execution, rapid iteration, and verifiable offline-first local intelligence.",
  communicationStyle:
    "Direct, analytical, concise. Values concrete code diffs and architectural integrity over generic prose.",
  toneAndDemeanor:
    "Driven, high-standards, impatient with fluff, laser-focused on sovereign computing & privacy.",
  activeHours: "08:00 - 02:00 IST (Peak cognitive flow: Late Evening / Night)",
  keyInterests: [
    "Autonomous Multi-Agent Orchestration",
    "Local-First LLMs & Edge Hardware",
    "Cross-Device Distributed Protocols",
    "Applied AI Product Engineering",
    "Venture Architecture & Stealth Shipping",
  ],
  cognitivePreferences: [
    "First-principles reasoning",
    "Low-latency reactive feedback",
    "Strict privacy & sovereign local custody",
    "Uncluttered, high-contrast, atmospheric interfaces",
  ],
  crossPlatformFootprint: [
    { platform: "Telegram", activityMetric: "Daily executive memos & architecture notes" },
    { platform: "Instagram", activityMetric: "Curated design aesthetics & lifestyle balance" },
    { platform: "GitHub", activityMetric: "Core engineering, rust checkouts, Tauri builds" },
    { platform: "TraceOp", activityMetric: "96% synthesis coherence across 7 nodes" },
  ],
};

export const DEFAULT_FOUNDER_PROFILE: UserProfile = {
  id: "usr_sovereign_dhanush",
  name: "Dhanush Surada",
  handle: "@dhanush",
  email: "dhanush@sam.local",
  isEmailVerified: true,
  phone: "+91 98765 43210",
  isPhoneVerified: true,
  role: "Sovereign Operator",
  bio: "Local-first sovereign AI workspace founder.",
  avatar: "DS",
  avatarBg: "obsidian",
  isSignedIn: true,
  authMethod: "founder",
  sessionStartedAt: new Date().toISOString(),
  lastActiveAt: new Date().toISOString(),
  incognitoMode: false,
  nodeId: "sam-node-8420-local",
  deviceKeyFingerprint: "ed25519:7f4a...9b12",
  connectedPlatforms: FOUNDER_CONNECTED_PLATFORMS,
  personaAnalysis: FOUNDER_PERSONA_ANALYSIS,
};

export const GUEST_PROFILE: UserProfile = {
  id: "usr_guest_session",
  name: "Guest Operator",
  handle: "@guest",
  email: "guest@sam.local",
  isEmailVerified: false,
  phone: undefined,
  isPhoneVerified: false,
  role: "Incognito Guest",
  bio: "Ephemeral session. Memory and task logs are not preserved.",
  avatar: "GO",
  avatarBg: "titanium",
  isSignedIn: false,
  authMethod: "guest",
  sessionStartedAt: new Date().toISOString(),
  lastActiveAt: new Date().toISOString(),
  incognitoMode: true,
  nodeId: "sam-node-guest",
  deviceKeyFingerprint: "ephemeral",
  connectedPlatforms: [],
  personaAnalysis: undefined,
};

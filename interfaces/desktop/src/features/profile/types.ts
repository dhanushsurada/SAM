export type AuthMethod = "founder" | "passkey" | "guest" | "local_token";

export interface UserProfile {
  id: string;
  name: string;
  handle: string;
  email: string;
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
}

export const DEFAULT_FOUNDER_PROFILE: UserProfile = {
  id: "usr_sovereign_dhanush",
  name: "Dhanush Surada",
  handle: "@dhanush",
  email: "dhanush@sam.local",
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
};

export const GUEST_PROFILE: UserProfile = {
  id: "usr_guest_session",
  name: "Guest Operator",
  handle: "@guest",
  email: "guest@sam.local",
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
};

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  DEFAULT_FOUNDER_PROFILE,
  GUEST_PROFILE,
  FOUNDER_CONNECTED_PLATFORMS,
  type UserProfile,
  type PlatformId,
  type ConnectedPlatform,
  type TraceOpPersonaAnalysis,
} from "./types";

const PROFILE_STORAGE_KEY = "sam.user_profile";
const ACCOUNT_VAULT_PREFIX = "sam.account_vault.";

export type ProfileTab = "overview" | "edit" | "ecosystem" | "appearance";

interface ProfileContextValue {
  profile: UserProfile;
  isSignedIn: boolean;
  signIn: (opts?: Partial<UserProfile>) => void;
  signOut: () => void;
  updateProfile: (data: Partial<UserProfile>) => void;
  verifyEmail: (code: string) => Promise<boolean>;
  verifyPhone: (code: string) => Promise<boolean>;
  updatePlatform: (id: PlatformId, patch: Partial<ConnectedPlatform>) => void;
  connectPlatform: (platform: ConnectedPlatform) => void;
  disconnectPlatform: (id: PlatformId) => void;
  runTraceOpAnalysis: () => Promise<TraceOpPersonaAnalysis>;
  toggleIncognito: () => void;
  isProfileModalOpen: boolean;
  profileModalTab: ProfileTab;
  openProfileModal: (tab?: ProfileTab) => void;
  closeProfileModal: () => void;
  isSignInModalOpen: boolean;
  openSignInModal: () => void;
  closeSignInModal: () => void;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

function getAccountKey(p: Partial<UserProfile>): string {
  if (p.email && p.email.trim()) return p.email.trim().toLowerCase();
  if (p.phone && p.phone.trim()) return p.phone.trim().replace(/\s+/g, "");
  return "founder_default";
}

function getInitialProfile(): UserProfile {
  if (typeof window === "undefined") return DEFAULT_FOUNDER_PROFILE;
  try {
    const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.name === "string") {
        return {
          ...DEFAULT_FOUNDER_PROFILE,
          ...parsed,
          connectedPlatforms: parsed.connectedPlatforms || DEFAULT_FOUNDER_PROFILE.connectedPlatforms,
          personaAnalysis: parsed.personaAnalysis || DEFAULT_FOUNDER_PROFILE.personaAnalysis,
          lastActiveAt: new Date().toISOString(),
        };
      }
    }
  } catch {
    // fallback
  }
  return DEFAULT_FOUNDER_PROFILE;
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState<UserProfile>(getInitialProfile);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [profileModalTab, setProfileModalTab] = useState<ProfileTab>("overview");
  const [isSignInModalOpen, setIsSignInModalOpen] = useState(false);

  // Sync profile to local storage and update account vault
  useEffect(() => {
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
      if (profile.isSignedIn) {
        const key = getAccountKey(profile);
        window.localStorage.setItem(ACCOUNT_VAULT_PREFIX + key, JSON.stringify(profile));
      }
    } catch {
      // ignore
    }
  }, [profile]);

  const signIn = (opts?: Partial<UserProfile>) => {
    let savedVault: Partial<UserProfile> | null = null;
    if (opts) {
      const key = getAccountKey(opts);
      try {
        const rawVault = window.localStorage.getItem(ACCOUNT_VAULT_PREFIX + key);
        if (rawVault) {
          savedVault = JSON.parse(rawVault);
        }
      } catch {
        // ignore
      }
    }

    setProfileState((prev) => {
      const isFounder = !opts || opts.authMethod === "founder" || (!opts.email && !opts.phone);
      const base = isFounder ? DEFAULT_FOUNDER_PROFILE : prev;
      const merged = {
        ...base,
        ...(savedVault || {}),
        ...opts,
        isSignedIn: true,
        authMethod: opts?.authMethod || (isFounder ? "founder" : "email_otp"),
        lastActiveAt: new Date().toISOString(),
        incognitoMode: false,
      };

      // Ensure connected platforms and persona analysis are always preserved
      if (!merged.connectedPlatforms || merged.connectedPlatforms.length === 0) {
        merged.connectedPlatforms = isFounder ? FOUNDER_CONNECTED_PLATFORMS : [
          {
            id: "telegram",
            name: "Telegram",
            category: "messaging",
            handle: merged.handle || "@user",
            connected: false,
            syncMessages: false,
            syncContext: false,
          },
          {
            id: "instagram",
            name: "Instagram",
            category: "social",
            handle: merged.handle || "@user",
            connected: false,
            syncMessages: false,
            syncContext: false,
          },
          {
            id: "whatsapp",
            name: "WhatsApp",
            category: "messaging",
            handle: merged.phone || "+1 555-0100",
            connected: false,
            syncMessages: false,
            syncContext: false,
          },
          {
            id: "traceop",
            name: "TraceOp Profiler",
            category: "intelligence",
            handle: `traceop:${merged.id}`,
            connected: false,
            syncMessages: false,
            syncContext: true,
          },
        ];
      }

      return merged;
    });

    setIsSignInModalOpen(false);
  };

  const signOut = () => {
    setProfileState((prev) => {
      // Save state into vault before signing out so it is remembered upon future sign-in
      try {
        const key = getAccountKey(prev);
        window.localStorage.setItem(ACCOUNT_VAULT_PREFIX + key, JSON.stringify(prev));
      } catch {
        // ignore
      }
      return {
        ...prev,
        ...GUEST_PROFILE,
        isSignedIn: false,
        lastActiveAt: new Date().toISOString(),
      };
    });
    setIsProfileModalOpen(false);
  };

  const updateProfile = (data: Partial<UserProfile>) => {
    setProfileState((prev) => ({
      ...prev,
      ...data,
      lastActiveAt: new Date().toISOString(),
    }));
  };

  const verifyEmail = async (code: string): Promise<boolean> => {
    // Simulated instant verification (accepts standard test code 123456 or any 6-digit code)
    if (code.trim().length >= 4) {
      setProfileState((prev) => ({
        ...prev,
        isEmailVerified: true,
        lastActiveAt: new Date().toISOString(),
      }));
      return true;
    }
    return false;
  };

  const verifyPhone = async (code: string): Promise<boolean> => {
    // Simulated instant verification (accepts standard test code 123456 or any 6-digit code)
    if (code.trim().length >= 4) {
      setProfileState((prev) => ({
        ...prev,
        isPhoneVerified: true,
        lastActiveAt: new Date().toISOString(),
      }));
      return true;
    }
    return false;
  };

  const updatePlatform = (id: PlatformId, patch: Partial<ConnectedPlatform>) => {
    setProfileState((prev) => ({
      ...prev,
      connectedPlatforms: prev.connectedPlatforms.map((p) =>
        p.id === id ? { ...p, ...patch, lastSyncedAt: new Date().toISOString() } : p,
      ),
      lastActiveAt: new Date().toISOString(),
    }));
  };

  const connectPlatform = (platform: ConnectedPlatform) => {
    setProfileState((prev) => {
      const exists = prev.connectedPlatforms.some((p) => p.id === platform.id);
      const updated = exists
        ? prev.connectedPlatforms.map((p) =>
            p.id === platform.id
              ? { ...p, ...platform, connected: true, connectedAt: new Date().toISOString() }
              : p,
          )
        : [...prev.connectedPlatforms, { ...platform, connected: true, connectedAt: new Date().toISOString() }];
      return {
        ...prev,
        connectedPlatforms: updated,
        lastActiveAt: new Date().toISOString(),
      };
    });
  };

  const disconnectPlatform = (id: PlatformId) => {
    setProfileState((prev) => ({
      ...prev,
      connectedPlatforms: prev.connectedPlatforms.map((p) =>
        p.id === id ? { ...p, connected: false, syncMessages: false, syncContext: false } : p,
      ),
      lastActiveAt: new Date().toISOString(),
    }));
  };

  const runTraceOpAnalysis = async (): Promise<TraceOpPersonaAnalysis> => {
    // Simulate real-time deep persona synthesis across connected footprints
    await new Promise((resolve) => setTimeout(resolve, 800));

    const connectedCount = profile.connectedPlatforms.filter((p) => p.connected).length;
    const completeness = Math.min(98, Math.max(50, 45 + connectedCount * 10));

    const updatedAnalysis: TraceOpPersonaAnalysis = {
      analyzedAt: new Date().toISOString(),
      overallScore: completeness,
      executiveSummary:
        profile.personaAnalysis?.executiveSummary ||
        `${profile.name} exhibits high agency, technical depth, and rapid execution patterns across ${connectedCount} connected platforms.`,
      communicationStyle:
        profile.personaAnalysis?.communicationStyle ||
        "Direct, clear, concise. Focuses on pragmatic outputs and verified milestones.",
      toneAndDemeanor:
        profile.personaAnalysis?.toneAndDemeanor ||
        "Product-focused, disciplined, analytical.",
      activeHours: profile.personaAnalysis?.activeHours || "09:00 - 01:00 (Peak: Evening)",
      keyInterests: profile.personaAnalysis?.keyInterests || [
        "Autonomous Systems",
        "Edge AI Models",
        "Ecosystem Integration",
      ],
      cognitivePreferences: profile.personaAnalysis?.cognitivePreferences || [
        "First-principles reasoning",
        "Concise code diffs",
      ],
      crossPlatformFootprint: profile.connectedPlatforms
        .filter((p) => p.connected)
        .map((p) => ({
          platform: p.name,
          activityMetric: `${p.handle} · Synced ${p.syncedFactsCount || 12} persona facts`,
        })),
    };

    setProfileState((prev) => ({
      ...prev,
      personaAnalysis: updatedAnalysis,
      lastActiveAt: new Date().toISOString(),
    }));

    return updatedAnalysis;
  };

  const toggleIncognito = () => {
    setProfileState((prev) => ({
      ...prev,
      incognitoMode: !prev.incognitoMode,
      lastActiveAt: new Date().toISOString(),
    }));
  };

  const openProfileModal = (tab: ProfileTab = "overview") => {
    setProfileModalTab(tab);
    setIsProfileModalOpen(true);
  };

  const closeProfileModal = () => setIsProfileModalOpen(false);
  const openSignInModal = () => setIsSignInModalOpen(true);
  const closeSignInModal = () => setIsSignInModalOpen(false);

  return (
    <ProfileContext.Provider
      value={{
        profile,
        isSignedIn: profile.isSignedIn,
        signIn,
        signOut,
        updateProfile,
        verifyEmail,
        verifyPhone,
        updatePlatform,
        connectPlatform,
        disconnectPlatform,
        runTraceOpAnalysis,
        toggleIncognito,
        isProfileModalOpen,
        profileModalTab,
        openProfileModal,
        closeProfileModal,
        isSignInModalOpen,
        openSignInModal,
        closeSignInModal,
      }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error("useProfile must be used within a ProfileProvider");
  }
  return context;
}

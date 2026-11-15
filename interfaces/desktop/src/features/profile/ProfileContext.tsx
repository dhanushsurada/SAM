import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DEFAULT_FOUNDER_PROFILE, GUEST_PROFILE, type UserProfile } from "./types";

const PROFILE_STORAGE_KEY = "sam.user_profile";

export type ProfileTab = "overview" | "edit" | "appearance";

interface ProfileContextValue {
  profile: UserProfile;
  isSignedIn: boolean;
  signIn: (opts?: Partial<UserProfile>) => void;
  signOut: () => void;
  updateProfile: (data: Partial<UserProfile>) => void;
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

  useEffect(() => {
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
    } catch {
      // ignore
    }
  }, [profile]);

  const signIn = (opts?: Partial<UserProfile>) => {
    setProfileState((prev) => ({
      ...prev,
      ...DEFAULT_FOUNDER_PROFILE,
      ...opts,
      isSignedIn: true,
      authMethod: opts?.authMethod || "founder",
      lastActiveAt: new Date().toISOString(),
      incognitoMode: false,
    }));
    setIsSignInModalOpen(false);
  };

  const signOut = () => {
    setProfileState((prev) => ({
      ...prev,
      ...GUEST_PROFILE,
      isSignedIn: false,
      lastActiveAt: new Date().toISOString(),
    }));
    setIsProfileModalOpen(false);
  };

  const updateProfile = (data: Partial<UserProfile>) => {
    setProfileState((prev) => ({
      ...prev,
      ...data,
      lastActiveAt: new Date().toISOString(),
    }));
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

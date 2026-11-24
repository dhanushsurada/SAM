import { useState, useEffect, type FormEvent } from "react";
import {
  FiX,
  FiUser,
  FiShield,
  FiLogOut,
  FiLogIn,
  FiDroplet,
  FiCheck,
  FiEyeOff,
  FiEdit3,
  FiMail,
  FiPhone,
  FiCheckCircle,
  FiActivity,
} from "react-icons/fi";
import { useProfile, type ProfileTab } from "./ProfileContext";
import { ThemePicker } from "@/features/theme/ThemePicker";
import { EcosystemHub } from "./EcosystemHub";
import { Button } from "@/components/Button";

const AVATAR_OPTIONS = ["DS", "⚡", "🛡️", "💎", "🚀", "🤖", "🌐", "🧠", "✦"];

export function ProfileModal() {
  const {
    profile,
    isSignedIn,
    signOut,
    updateProfile,
    verifyEmail,
    verifyPhone,
    toggleIncognito,
    isProfileModalOpen,
    profileModalTab,
    closeProfileModal,
    openSignInModal,
  } = useProfile();

  const [activeTab, setActiveTab] = useState<ProfileTab>(profileModalTab);
  const [name, setName] = useState(profile.name);
  const [handle, setHandle] = useState(profile.handle);
  const [email, setEmail] = useState(profile.email);
  const [phone, setPhone] = useState(profile.phone || "");
  const [role, setRole] = useState(profile.role);
  const [bio, setBio] = useState(profile.bio);
  const [avatar, setAvatar] = useState(profile.avatar);
  const [savedNotice, setSavedNotice] = useState(false);

  // Verification state
  const [verifyingEmail, setVerifyingEmail] = useState(false);
  const [emailOtp, setEmailOtp] = useState("123456");
  const [verifyingPhone, setVerifyingPhone] = useState(false);
  const [phoneOtp, setPhoneOtp] = useState("123456");

  useEffect(() => {
    setActiveTab(profileModalTab);
  }, [profileModalTab]);

  useEffect(() => {
    setName(profile.name);
    setHandle(profile.handle);
    setEmail(profile.email);
    setPhone(profile.phone || "");
    setRole(profile.role);
    setBio(profile.bio);
    setAvatar(profile.avatar);
  }, [profile]);

  useEffect(() => {
    if (!isProfileModalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeProfileModal();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isProfileModalOpen, closeProfileModal]);

  if (!isProfileModalOpen) return null;

  const handleSaveProfile = (e: FormEvent) => {
    e.preventDefault();
    updateProfile({
      name: name.trim() || profile.name,
      handle: handle.trim().startsWith("@") ? handle.trim() : `@${handle.trim()}`,
      email: email.trim() || profile.email,
      phone: phone.trim() || undefined,
      role: role.trim() || profile.role,
      bio: bio.trim(),
      avatar,
    });
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 2000);
  };

  const handleConfirmEmailVerification = async () => {
    await verifyEmail(emailOtp);
    setVerifyingEmail(false);
  };

  const handleConfirmPhoneVerification = async () => {
    await verifyPhone(phoneOtp);
    setVerifyingPhone(false);
  };

  const connectedCount = profile.connectedPlatforms?.filter((p) => p.connected).length || 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
    >
      {/* Backdrop */}
      <div
        onClick={closeProfileModal}
        aria-hidden="true"
        className="fixed inset-0 bg-void/80 backdrop-blur-md animate-sam-fade-in"
      />

      {/* Modal Surface */}
      <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-line/70 bg-surface/95 p-6 shadow-2xl backdrop-blur-2xl ring-1 ring-white/5 animate-sam-scale-in">
        {/* Top Header */}
        <div className="flex items-start justify-between border-b border-line/50 pb-4">
          <div className="flex items-center gap-3.5">
            <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-void border border-ember/30 text-ink text-base font-bold shadow-md">
              <span>{profile.avatar}</span>
              <span
                className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-surface ${
                  isSignedIn ? "bg-success" : "bg-mute"
                }`}
              />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="profile-modal-title" className="text-base font-semibold text-ink">
                  {profile.name}
                </h2>
                <span className="rounded-md border border-line/60 bg-void/80 px-2 py-0.5 font-mono text-[10px] text-mute">
                  {profile.role}
                </span>
              </div>
              <p className="text-xs text-mute mt-0.5">
                {profile.handle} · {profile.email} · {isSignedIn ? "Sovereign Session" : "Guest Mode"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeProfileModal}
            className="rounded-lg p-1 text-mute hover:bg-void hover:text-ink transition-colors"
            aria-label="Close profile modal"
          >
            <FiX size={18} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-line/40 pt-3 text-xs overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors shrink-0 ${
              activeTab === "overview"
                ? "border-ember text-ink"
                : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiUser size={13} />
            Overview & Node
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("ecosystem")}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors shrink-0 ${
              activeTab === "ecosystem"
                ? "border-ember text-ink"
                : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiActivity size={13} />
            Ecosystem & TraceOp ({connectedCount})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("edit")}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors shrink-0 ${
              activeTab === "edit"
                ? "border-ember text-ink"
                : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiEdit3 size={13} />
            Edit Profile
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("appearance")}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors shrink-0 ${
              activeTab === "appearance"
                ? "border-ember text-ink"
                : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiDroplet size={13} />
            Appearance & Themes
          </button>
        </div>

        {/* Tab Body */}
        <div className="py-4 max-h-[62vh] overflow-y-auto space-y-4 pr-1">
          {activeTab === "overview" && (
            <div className="space-y-4">
              {/* Account & Verification Badges */}
              <div className="rounded-xl border border-line/60 bg-void/60 p-3.5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-mute">
                    Verified Sovereign Credentials
                  </span>
                  <span className="flex items-center gap-1 text-[11px] font-mono text-success">
                    <FiShield size={12} />
                    Cryptographically Anchored
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  {/* Email Verification Card */}
                  <div className="rounded-lg border border-line/50 bg-surface/50 p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FiMail size={14} className="text-mute" />
                      <div>
                        <p className="font-mono text-ink text-[11px] truncate max-w-[140px]">
                          {profile.email}
                        </p>
                        <span className="text-[10px] text-mute block">Email Verification</span>
                      </div>
                    </div>
                    {profile.isEmailVerified ? (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-success bg-success/10 px-2 py-0.5 rounded-md">
                        <FiCheckCircle size={11} /> Verified
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setVerifyingEmail(true)}
                        className="text-[11px] text-ember-text border border-ember/30"
                      >
                        Verify Now
                      </Button>
                    )}
                  </div>

                  {/* Phone Verification Card */}
                  <div className="rounded-lg border border-line/50 bg-surface/50 p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FiPhone size={14} className="text-mute" />
                      <div>
                        <p className="font-mono text-ink text-[11px] truncate max-w-[140px]">
                          {profile.phone || "Not linked"}
                        </p>
                        <span className="text-[10px] text-mute block">Mobile SMS Verification</span>
                      </div>
                    </div>
                    {profile.isPhoneVerified ? (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-success bg-success/10 px-2 py-0.5 rounded-md">
                        <FiCheckCircle size={11} /> Verified
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setVerifyingPhone(true)}
                        className="text-[11px] text-ember-text border border-ember/30"
                      >
                        {profile.phone ? "Verify" : "Link Mobile"}
                      </Button>
                    )}
                  </div>
                </div>

                {/* Inline OTP Verification Panels */}
                {verifyingEmail && (
                  <div className="rounded-lg border border-ember/40 bg-ember/10 p-3 space-y-2">
                    <p className="text-xs font-semibold text-ink">Verify Email ({profile.email})</p>
                    <p className="text-[11px] text-mute">
                      Enter the 6-digit verification code sent to your email.
                    </p>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={emailOtp}
                        onChange={(e) => setEmailOtp(e.target.value)}
                        placeholder="123456"
                        className="w-32 font-mono text-center rounded border border-line bg-void px-2 py-1 text-xs text-ink"
                      />
                      <Button size="sm" variant="primary" onClick={handleConfirmEmailVerification}>
                        Confirm Code
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setVerifyingEmail(false)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {verifyingPhone && (
                  <div className="rounded-lg border border-ember/40 bg-ember/10 p-3 space-y-2">
                    <p className="text-xs font-semibold text-ink">
                      Verify Mobile Phone ({profile.phone || "+91 98765 43210"})
                    </p>
                    <p className="text-[11px] text-mute">
                      Enter the SMS OTP verification code.
                    </p>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={phoneOtp}
                        onChange={(e) => setPhoneOtp(e.target.value)}
                        placeholder="123456"
                        className="w-32 font-mono text-center rounded border border-line bg-void px-2 py-1 text-xs text-ink"
                      />
                      <Button size="sm" variant="primary" onClick={handleConfirmPhoneVerification}>
                        Confirm SMS
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setVerifyingPhone(false)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Node Identity Details */}
              <div className="rounded-xl border border-line/60 bg-surface/60 p-3.5 space-y-2.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-mute block">
                  Node & Cryptographic Fingerprint
                </span>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-mute block text-[10px] uppercase">Node Identifier</span>
                    <span className="font-mono text-ink text-[11px]">{profile.nodeId}</span>
                  </div>
                  <div>
                    <span className="text-mute block text-[10px] uppercase">Ed25519 Fingerprint</span>
                    <span className="font-mono text-ink text-[11px]">{profile.deviceKeyFingerprint}</span>
                  </div>
                  <div>
                    <span className="text-mute block text-[10px] uppercase">Authentication Mode</span>
                    <span className="capitalize text-ink">{profile.authMethod} mode</span>
                  </div>
                  <div>
                    <span className="text-mute block text-[10px] uppercase">Ecosystem Nodes</span>
                    <span className="text-ink">{connectedCount} Platforms Active</span>
                  </div>
                </div>
              </div>

              {/* Incognito / Privacy Toggle */}
              <div className="flex items-center justify-between rounded-xl border border-line/60 bg-surface/60 p-3">
                <div className="flex items-center gap-2.5">
                  <div className="rounded-lg bg-void p-2 text-mute">
                    <FiEyeOff size={16} />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-ink">Incognito Privacy Mode</p>
                    <p className="text-[11px] text-mute">
                      Do not persist task memory or conversation transcripts.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={toggleIncognito}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                    profile.incognitoMode ? "bg-ember" : "bg-line"
                  }`}
                  role="switch"
                  aria-checked={profile.incognitoMode}
                >
                  <span
                    className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-void shadow-lg ring-0 transition duration-200 ease-in-out ${
                      profile.incognitoMode ? "translate-x-4" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>

              {/* Sign In / Sign Out Actions */}
              <div className="border-t border-line/50 pt-3 flex items-center justify-between">
                {isSignedIn ? (
                  <>
                    <p className="text-xs text-mute">
                      Signed in as Sovereign Operator ({profile.name}).
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={signOut}
                      className="text-danger hover:bg-danger/10 hover:text-danger flex items-center gap-1.5"
                    >
                      <FiLogOut size={13} />
                      Sign Out
                    </Button>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-mute">
                      Currently using Guest / Incognito mode.
                    </p>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => {
                        closeProfileModal();
                        openSignInModal();
                      }}
                      className="flex items-center gap-1.5"
                    >
                      <FiLogIn size={13} />
                      Sign In / Verify Account
                    </Button>
                  </>
                )}
              </div>
            </div>
          )}

          {activeTab === "ecosystem" && <EcosystemHub />}

          {activeTab === "edit" && (
            <form onSubmit={handleSaveProfile} className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Display Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                  placeholder="e.g. Dhanush Surada"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Handle</label>
                  <input
                    type="text"
                    value={handle}
                    onChange={(e) => setHandle(e.target.value)}
                    className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    placeholder="@dhanush"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Role Title</label>
                  <input
                    type="text"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    placeholder="Sovereign Operator"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Email Address</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    placeholder="dhanush@sam.local"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Mobile Phone</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    placeholder="+91 98765 43210"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-ink mb-1">Bio</label>
                <textarea
                  rows={2}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                  placeholder="Describe your workspace mission..."
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-ink mb-1.5">Avatar Symbol</label>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_OPTIONS.map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => setAvatar(sym)}
                      className={`flex h-8 w-8 items-center justify-center rounded-lg border text-xs transition-all ${
                        avatar === sym
                          ? "border-ember bg-ember/20 text-ember-text font-bold ring-1 ring-ember"
                          : "border-line bg-void text-mute hover:border-line hover:text-ink"
                      }`}
                    >
                      {sym}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-line/50 pt-3">
                {savedNotice ? (
                  <span className="flex items-center gap-1 text-xs text-success font-medium">
                    <FiCheck size={13} />
                    Profile saved successfully
                  </span>
                ) : (
                  <span className="text-[11px] text-mute">Updates are saved to sovereign local storage.</span>
                )}
                <Button type="submit" variant="primary" size="sm">
                  Save Changes
                </Button>
              </div>
            </form>
          )}

          {activeTab === "appearance" && (
            <div className="space-y-4">
              <ThemePicker />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

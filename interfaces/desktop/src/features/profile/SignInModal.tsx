import { useState, type FormEvent } from "react";
import { FiX, FiShield, FiKey, FiUser, FiArrowRight } from "react-icons/fi";
import { useProfile } from "./ProfileContext";
import { Button } from "@/components/Button";

export function SignInModal() {
  const { isSignInModalOpen, closeSignInModal, signIn } = useProfile();
  const [usePasskey, setUsePasskey] = useState(false);
  const [passkeyInput, setPasskeyInput] = useState("");
  const [nameInput, setNameInput] = useState("");

  if (!isSignInModalOpen) return null;

  const handleSignInFounder = () => {
    signIn();
    closeSignInModal();
  };

  const handleSignInCustom = (e: FormEvent) => {
    e.preventDefault();
    signIn({
      name: nameInput.trim() || "Sovereign Operator",
      handle: nameInput.trim() ? `@${nameInput.trim().toLowerCase().replace(/\s+/g, "")}` : "@operator",
      authMethod: usePasskey ? "passkey" : "founder",
    });
    closeSignInModal();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="signin-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
    >
      {/* Backdrop */}
      <div
        onClick={closeSignInModal}
        aria-hidden="true"
        className="fixed inset-0 bg-void/80 backdrop-blur-md transition-opacity"
      />

      {/* Surface */}
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-line/70 bg-surface/95 p-6 shadow-2xl backdrop-blur-2xl ring-1 ring-white/5 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-start justify-between border-b border-line/40 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-void border border-ember/30 text-ink">
              <FiShield size={18} className="text-ember" />
            </div>
            <div>
              <h2 id="signin-modal-title" className="text-sm font-semibold text-ink">
                Sign In to SAM
              </h2>
              <p className="text-xs text-mute">Local sovereign workspace authentication</p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeSignInModal}
            className="rounded-lg p-1 text-mute hover:bg-void hover:text-ink transition-colors"
            aria-label="Close sign in dialog"
          >
            <FiX size={16} />
          </button>
        </div>

        <div className="py-4 space-y-3.5">
          {/* Quick Founder Sign-in */}
          <button
            type="button"
            onClick={handleSignInFounder}
            className="w-full flex items-center justify-between p-3 rounded-xl border border-line bg-void/60 hover:border-ember/60 hover:bg-void transition-all text-left group cursor-pointer"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface border border-line text-xs font-bold text-ink">
                DS
              </div>
              <div>
                <p className="text-xs font-semibold text-ink group-hover:text-ember-text transition-colors">
                  Continue as Founder (Dhanush Surada)
                </p>
                <p className="text-[11px] text-mute">Instant local cryptographic session</p>
              </div>
            </div>
            <FiArrowRight size={14} className="text-mute group-hover:text-ink transition-colors" />
          </button>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-line/50" />
            <span className="flex-shrink mx-3 text-[10px] uppercase font-mono text-mute/60">
              or custom profile
            </span>
            <div className="flex-grow border-t border-line/50" />
          </div>

          <form onSubmit={handleSignInCustom} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-ink mb-1">Operator Name</label>
              <div className="relative">
                <input
                  type="text"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  placeholder="e.g. Dhanush Surada"
                  className="w-full rounded-lg border border-line bg-void pl-8 pr-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                />
                <FiUser size={12} className="absolute left-2.5 top-2.5 text-mute" />
              </div>
            </div>

            {usePasskey && (
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Passkey / Key Phrase</label>
                <div className="relative">
                  <input
                    type="password"
                    value={passkeyInput}
                    onChange={(e) => setPasskeyInput(e.target.value)}
                    placeholder="Enter local passkey"
                    className="w-full rounded-lg border border-line bg-void pl-8 pr-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                  />
                  <FiKey size={12} className="absolute left-2.5 top-2.5 text-mute" />
                </div>
              </div>
            )}

            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={() => setUsePasskey(!usePasskey)}
                className="text-mute hover:text-ink text-[11px] underline"
              >
                {usePasskey ? "Skip passkey check" : "Sign in with local passkey"}
              </button>
            </div>

            <Button type="submit" variant="primary" size="sm" className="w-full mt-2">
              Sign In to Session
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

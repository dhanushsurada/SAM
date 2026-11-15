import { useState, type FormEvent } from "react";
import {
  FiX,
  FiShield,
  FiMail,
  FiPhone,
  FiKey,
  FiArrowRight,
  FiCheckCircle,
} from "react-icons/fi";
import { useProfile } from "./ProfileContext";
import { Button } from "@/components/Button";

type SignInMode = "founder" | "email" | "phone" | "passkey";

export function SignInModal() {
  const { isSignInModalOpen, closeSignInModal, signIn } = useProfile();
  const [mode, setMode] = useState<SignInMode>("email");

  // Email flow state
  const [emailInput, setEmailInput] = useState("");
  const [emailCodeSent, setEmailCodeSent] = useState(false);
  const [emailOtp, setEmailOtp] = useState("");
  const [emailSending, setEmailSending] = useState(false);

  // Phone flow state
  const [phoneInput, setPhoneInput] = useState("");
  const [phoneCodeSent, setPhoneCodeSent] = useState(false);
  const [phoneOtp, setPhoneOtp] = useState("");
  const [phoneSending, setPhoneSending] = useState(false);

  // Custom/Passkey state
  const [nameInput, setNameInput] = useState("");
  const [passkeyInput, setPasskeyInput] = useState("");

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isSignInModalOpen) return null;

  const handleSignInFounder = () => {
    signIn();
    closeSignInModal();
  };

  const handleSendEmailCode = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!emailInput.trim() || !emailInput.includes("@")) {
      setErrorMsg("Please enter a valid email address.");
      return;
    }
    setEmailSending(true);
    setTimeout(() => {
      setEmailSending(false);
      setEmailCodeSent(true);
      setEmailOtp("123456"); // simulated test code auto-filled for user convenience
    }, 400);
  };

  const handleVerifyEmailAndSignIn = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (emailOtp.trim().length < 4) {
      setErrorMsg("Please enter the verification code.");
      return;
    }
    const cleanEmail = emailInput.trim().toLowerCase();
    const username = cleanEmail.split("@")[0] || "Operator";
    signIn({
      email: cleanEmail,
      isEmailVerified: true,
      name: username.charAt(0).toUpperCase() + username.slice(1),
      handle: `@${username}`,
      authMethod: "email_otp",
    });
    closeSignInModal();
  };

  const handleSendPhoneCode = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!phoneInput.trim() || phoneInput.trim().length < 7) {
      setErrorMsg("Please enter a valid phone number with country code.");
      return;
    }
    setPhoneSending(true);
    setTimeout(() => {
      setPhoneSending(false);
      setPhoneCodeSent(true);
      setPhoneOtp("123456"); // simulated test code
    }, 400);
  };

  const handleVerifyPhoneAndSignIn = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (phoneOtp.trim().length < 4) {
      setErrorMsg("Please enter the SMS verification code.");
      return;
    }
    const cleanPhone = phoneInput.trim();
    signIn({
      phone: cleanPhone,
      isPhoneVerified: true,
      name: `Operator (${cleanPhone.slice(-4)})`,
      handle: `@operator_${cleanPhone.slice(-4)}`,
      authMethod: "phone_sms",
    });
    closeSignInModal();
  };

  const handleSignInPasskey = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    const cleanName = nameInput.trim() || "Sovereign Operator";
    signIn({
      name: cleanName,
      handle: `@${cleanName.toLowerCase().replace(/\s+/g, "")}`,
      authMethod: "passkey",
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
              <p className="text-xs text-mute">Verified sovereign authentication & ecosystem context</p>
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

        {/* Tab switchers */}
        <div className="flex border-b border-line/40 pt-3 text-xs">
          <button
            type="button"
            onClick={() => {
              setMode("email");
              setErrorMsg(null);
            }}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors ${
              mode === "email" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiMail size={12} />
            Email Login
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("phone");
              setErrorMsg(null);
            }}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors ${
              mode === "phone" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiPhone size={12} />
            Mobile SMS
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("founder");
              setErrorMsg(null);
            }}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors ${
              mode === "founder" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiShield size={12} />
            Founder
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("passkey");
              setErrorMsg(null);
            }}
            className={`flex items-center gap-1.5 px-3 py-2 font-medium border-b-2 transition-colors ${
              mode === "passkey" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <FiKey size={12} />
            Passkey
          </button>
        </div>

        <div className="py-4 space-y-3.5">
          {errorMsg && (
            <p className="rounded-lg bg-danger/10 border border-danger/30 px-3 py-1.5 text-xs text-danger">
              {errorMsg}
            </p>
          )}

          {/* Email Login Flow */}
          {mode === "email" && (
            <div className="space-y-3">
              {!emailCodeSent ? (
                <form onSubmit={handleSendEmailCode} className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-ink mb-1">Email Address</label>
                    <div className="relative">
                      <input
                        type="email"
                        value={emailInput}
                        onChange={(e) => setEmailInput(e.target.value)}
                        placeholder="you@domain.com"
                        required
                        className="w-full rounded-lg border border-line bg-void pl-8 pr-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                      />
                      <FiMail size={12} className="absolute left-2.5 top-2.5 text-mute" />
                    </div>
                    <p className="text-[11px] text-mute mt-1">
                      A 6-digit verification code will be sent to link your ecosystem context.
                    </p>
                  </div>
                  <Button type="submit" variant="primary" size="sm" loading={emailSending} className="w-full">
                    Send Verification Code
                  </Button>
                </form>
              ) : (
                <form onSubmit={handleVerifyEmailAndSignIn} className="space-y-3">
                  <div className="flex items-center justify-between text-xs bg-void/60 p-2.5 rounded-lg border border-line/60">
                    <span className="text-ink font-mono text-[11px] truncate">{emailInput}</span>
                    <button
                      type="button"
                      onClick={() => setEmailCodeSent(false)}
                      className="text-mute hover:text-ink text-[11px] underline"
                    >
                      Change
                    </button>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink mb-1">
                      Verification Code
                    </label>
                    <input
                      type="text"
                      maxLength={6}
                      value={emailOtp}
                      onChange={(e) => setEmailOtp(e.target.value)}
                      placeholder="e.g. 123456"
                      className="w-full text-center font-mono tracking-widest text-base rounded-lg border border-line bg-void py-2 text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    />
                    <p className="text-[11px] text-success mt-1 flex items-center gap-1">
                      <FiCheckCircle size={11} /> Code ready: click verify to restore connected platforms
                    </p>
                  </div>
                  <Button type="submit" variant="primary" size="sm" className="w-full">
                    Verify & Sign In
                  </Button>
                </form>
              )}
            </div>
          )}

          {/* Mobile Phone SMS Login Flow */}
          {mode === "phone" && (
            <div className="space-y-3">
              {!phoneCodeSent ? (
                <form onSubmit={handleSendPhoneCode} className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-ink mb-1">
                      Mobile Number (with Country Code)
                    </label>
                    <div className="relative">
                      <input
                        type="tel"
                        value={phoneInput}
                        onChange={(e) => setPhoneInput(e.target.value)}
                        placeholder="+91 98765 43210 or +1 555-0199"
                        required
                        className="w-full rounded-lg border border-line bg-void pl-8 pr-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                      />
                      <FiPhone size={12} className="absolute left-2.5 top-2.5 text-mute" />
                    </div>
                    <p className="text-[11px] text-mute mt-1">
                      An SMS authentication code will be sent to verify your phone number.
                    </p>
                  </div>
                  <Button type="submit" variant="primary" size="sm" loading={phoneSending} className="w-full">
                    Send SMS Code
                  </Button>
                </form>
              ) : (
                <form onSubmit={handleVerifyPhoneAndSignIn} className="space-y-3">
                  <div className="flex items-center justify-between text-xs bg-void/60 p-2.5 rounded-lg border border-line/60">
                    <span className="text-ink font-mono text-[11px] truncate">{phoneInput}</span>
                    <button
                      type="button"
                      onClick={() => setPhoneCodeSent(false)}
                      className="text-mute hover:text-ink text-[11px] underline"
                    >
                      Change
                    </button>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink mb-1">
                      SMS Verification Code
                    </label>
                    <input
                      type="text"
                      maxLength={6}
                      value={phoneOtp}
                      onChange={(e) => setPhoneOtp(e.target.value)}
                      placeholder="e.g. 123456"
                      className="w-full text-center font-mono tracking-widest text-base rounded-lg border border-line bg-void py-2 text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    />
                    <p className="text-[11px] text-success mt-1 flex items-center gap-1">
                      <FiCheckCircle size={11} /> SMS verified: restores personal context & linked accounts
                    </p>
                  </div>
                  <Button type="submit" variant="primary" size="sm" className="w-full">
                    Verify Mobile & Sign In
                  </Button>
                </form>
              )}
            </div>
          )}

          {/* Quick Founder Sign-in */}
          {mode === "founder" && (
            <div className="space-y-3">
              <button
                type="button"
                onClick={handleSignInFounder}
                className="w-full flex items-center justify-between p-3.5 rounded-xl border border-ember/40 bg-ember/10 hover:border-ember hover:bg-ember/20 transition-all text-left group cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface border border-line text-xs font-bold text-ink">
                    DS
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-ink group-hover:text-ember-text transition-colors">
                      Continue as Founder (Dhanush Surada)
                    </p>
                    <p className="text-[11px] text-mute">
                      Pre-verified email (dhanush@sam.local) & phone (+91 98765 43210)
                    </p>
                  </div>
                </div>
                <FiArrowRight size={14} className="text-mute group-hover:text-ink transition-colors" />
              </button>
              <p className="text-[11px] text-mute text-center">
                Restores full TraceOp neural profile, Telegram, WhatsApp, and GitHub integrations.
              </p>
            </div>
          )}

          {/* Passkey Mode */}
          {mode === "passkey" && (
            <form onSubmit={handleSignInPasskey} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Operator Name</label>
                <input
                  type="text"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  placeholder="e.g. Dhanush Surada"
                  className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Local Passkey</label>
                <input
                  type="password"
                  value={passkeyInput}
                  onChange={(e) => setPasskeyInput(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full rounded-lg border border-line bg-void px-3 py-1.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                />
              </div>
              <Button type="submit" variant="primary" size="sm" className="w-full mt-2">
                Sign In with Passkey
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

import { FiLogOut, FiLogIn, FiSliders } from "react-icons/fi";
import { useProfile } from "./ProfileContext";

export function SidebarProfile() {
  const { profile, isSignedIn, openProfileModal, openSignInModal, signOut } = useProfile();

  if (!isSignedIn) {
    return (
      <div className="rounded-xl border border-line/60 bg-surface/50 p-2.5 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-void border border-line text-[11px] font-bold text-mute">
              GO
              <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-mute" />
            </div>
            <div>
              <p className="text-xs font-medium text-ink">Guest Operator</p>
              <p className="text-[10px] text-mute">Ephemeral mode</p>
            </div>
          </div>
          <button
            type="button"
            onClick={openSignInModal}
            className="flex items-center gap-1 rounded-lg border border-line bg-void px-2 py-1 text-[11px] font-medium text-ink hover:border-ember/40 hover:bg-surface transition-all"
            title="Sign in"
          >
            <FiLogIn size={11} className="text-ember" />
            <span>Sign In</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-xl border border-line/60 bg-surface/40 p-2 backdrop-blur-md hover:border-line/90 hover:bg-surface/70 transition-all">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => openProfileModal("overview")}
          className="flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer"
          title="Open Profile & Settings"
        >
          <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-void border border-ember/30 text-ink text-xs font-semibold shadow-sm">
            <span>{profile.avatar}</span>
            <span
              className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-surface ${
                profile.incognitoMode ? "bg-warn" : "bg-success"
              }`}
            />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-ink group-hover:text-ember-text transition-colors">
              {profile.name}
            </p>
            <div className="flex items-center gap-1 text-[10px] text-mute">
              <span className="truncate">{profile.role}</span>
              {profile.incognitoMode && (
                <span className="rounded bg-warn/15 px-1 text-[9px] text-warn">Incognito</span>
              )}
            </div>
          </div>
        </button>

        <div className="flex items-center gap-1 pl-1">
          <button
            type="button"
            onClick={() => openProfileModal("appearance")}
            className="rounded-md p-1 text-mute hover:bg-void hover:text-ink transition-colors"
            title="Appearance & Themes"
            aria-label="Appearance & Themes"
          >
            <FiSliders size={13} />
          </button>
          <button
            type="button"
            onClick={signOut}
            className="rounded-md p-1 text-mute hover:bg-danger/15 hover:text-danger transition-colors"
            title="Sign Out"
            aria-label="Sign Out"
          >
            <FiLogOut size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

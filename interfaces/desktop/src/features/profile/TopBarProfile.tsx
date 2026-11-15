import { useProfile } from "./ProfileContext";

export function TopBarProfile() {
  const { profile, isSignedIn, openProfileModal, openSignInModal } = useProfile();

  if (!isSignedIn) {
    return (
      <button
        type="button"
        onClick={openSignInModal}
        className="flex items-center gap-1.5 rounded-full border border-line/70 bg-surface/60 px-2.5 py-1 text-xs text-mute hover:text-ink hover:border-ember/40 transition-all"
        title="Sign In to SAM"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-mute" />
        <span className="font-mono text-[10px]">Sign In</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => openProfileModal("overview")}
      className="flex items-center gap-2 rounded-full border border-line/60 bg-surface/60 py-0.5 pl-1 pr-2.5 text-xs text-mute hover:text-ink hover:border-ember/40 transition-all cursor-pointer"
      title={`Operator: ${profile.name} (${profile.role})`}
    >
      <div className="relative flex h-5 w-5 items-center justify-center rounded-full bg-void border border-ember/30 text-[10px] font-bold text-ink">
        <span>{profile.avatar}</span>
        <span
          className={`absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full border border-surface ${
            profile.incognitoMode ? "bg-warn" : "bg-success"
          }`}
        />
      </div>
      <span className="font-mono text-[10px] text-ink truncate max-w-[80px] hidden sm:inline">
        {profile.name.split(" ")[0]}
      </span>
    </button>
  );
}

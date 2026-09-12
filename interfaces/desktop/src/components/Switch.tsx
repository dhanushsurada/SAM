export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
}

export function Switch({ checked, onChange, label, disabled }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-[var(--sam-motion-fast)] disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-ember" : "bg-line"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-void transition-transform duration-[var(--sam-motion-fast)] ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

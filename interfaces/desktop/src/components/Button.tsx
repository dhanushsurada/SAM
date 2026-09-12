import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a pending state and disables interaction. Distinct from
   * `disabled` so callers can tell "can't be pressed yet" apart from
   * "is currently doing something" — both real states, not the same one. */
  loading?: boolean;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium " +
  "transition-colors duration-[var(--sam-motion-state)] disabled:cursor-not-allowed disabled:opacity-50";

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
};

const variants: Record<Variant, string> = {
  primary: "bg-ember text-ember-ink hover:bg-ember/90 active:bg-ember/80",
  secondary:
    "bg-surface text-ink border border-line hover:border-mute/60 active:bg-surface/80",
  ghost: "text-mute hover:text-ink hover:bg-surface",
  danger: "bg-danger text-ink hover:bg-danger/90 active:bg-danger/80",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

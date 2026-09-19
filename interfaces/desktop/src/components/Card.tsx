import type { HTMLAttributes } from "react";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** p-4 ("sm") covers most panels; p-5 ("md") is the design-system
   * reference page's slightly roomier read; p-6 ("lg") is the one-per-
   * screen onboarding card. These match the exact values already in use
   * across the app, not a new scale invented for this component. */
  padding?: "sm" | "md" | "lg";
  /** "section" for SettingsPage's per-field-group anchors, where an id +
   * scroll-mt-4 target wants a real landmark element. "div" (default)
   * everywhere else. */
  as?: "div" | "section";
}

const PADDING: Record<NonNullable<CardProps["padding"]>, string> = {
  sm: "p-4",
  md: "p-5",
  lg: "p-6",
};

/**
 * The one boxed-content container nearly every screen was already
 * hand-rolling: `rounded-lg border border-line bg-surface ... shadow-panel`
 * showed up at 13 call sites across 10 files before this extraction —
 * Settings, Onboarding, Licensing, the iQOO workspace (×3), Command
 * Center (×2), and the design-system reference page (×4). Pulled out on
 * the same basis PageHeader was (PHASE5_PLAN.md §H step 7): repetition,
 * not a rule laid down in advance, justifies a primitive.
 *
 * Deliberately does NOT impose child layout (no built-in space-y) — every
 * call site stacks or arranges its own content differently, so that stays
 * the caller's job via `className`.
 */
export function Card({ as = "div", padding = "sm", className = "", children, ...rest }: CardProps) {
  const Tag = as;
  return (
    <Tag
      className={`rounded-lg border border-line bg-surface shadow-panel ${PADDING[padding]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export type Theme = "dark" | "light";

export type ColorTemplate =
  | "obsidian"   // Minimal Silver Glass (Default - Monochromatic)
  | "frost"      // Nordic Ice Cyan
  | "emerald"    // Sage Mint Glass
  | "amethyst"   // Soft Lavender Haze
  | "titanium"   // Industrial Monochromatic Slate
  | "amber";     // Warm Amber (Legacy)

export interface ColorTemplateMeta {
  id: ColorTemplate;
  name: string;
  tagline: string;
  accentHex: string;
  dotClass: string;
  borderClass: string;
}

export const COLOR_TEMPLATES: ColorTemplateMeta[] = [
  {
    id: "obsidian",
    name: "Obsidian Frost",
    tagline: "Transparent glass with crisp monochromatic silver accents",
    accentHex: "#F0F2F5",
    dotClass: "bg-slate-200",
    borderClass: "border-slate-300",
  },
  {
    id: "frost",
    name: "Ice Cyan",
    tagline: "Cool arctic glass with crisp electric cyan accents",
    accentHex: "#38BDF8",
    dotClass: "bg-sky-400",
    borderClass: "border-sky-500",
  },
  {
    id: "emerald",
    name: "Sage Emerald",
    tagline: "Calm organic mint with subtle translucent glass",
    accentHex: "#34D399",
    dotClass: "bg-emerald-400",
    borderClass: "border-emerald-500",
  },
  {
    id: "amethyst",
    name: "Lavender Haze",
    tagline: "Soft minimal violet with atmospheric glass gradients",
    accentHex: "#A78BFA",
    dotClass: "bg-purple-400",
    borderClass: "border-purple-500",
  },
  {
    id: "titanium",
    name: "Titanium Slate",
    tagline: "Ultra-minimalist zero-color slate, pure focus",
    accentHex: "#CBD5E1",
    dotClass: "bg-slate-400",
    borderClass: "border-slate-500",
  },
  {
    id: "amber",
    name: "Warm Amber",
    tagline: "Classic warm amber glow with high-contrast surfaces",
    accentHex: "#F59E0B",
    dotClass: "bg-amber-500",
    borderClass: "border-amber-600",
  },
];

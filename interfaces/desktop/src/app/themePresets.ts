export type Theme = "dark" | "light";

export type ColorTemplate =
  | "obsidian"   // Minimal Frost (Silver in Dark, Cobalt in Light)
  | "frost"      // Nordic Ice Cyan
  | "emerald"    // Sage Mint Glass
  | "amethyst"   // Soft Lavender Haze
  | "coral"      // Sunset Rose Coral
  | "titanium"   // Industrial Monochromatic Slate
  | "amber"      // Warm Amber
  | "custom";    // Custom user color

export interface ColorTemplateMeta {
  id: ColorTemplate;
  name: string;
  tagline: string;
  accentHex: string;
  lightAccentHex: string;
  dotClass: string;
  borderClass: string;
}

export const COLOR_TEMPLATES: ColorTemplateMeta[] = [
  {
    id: "obsidian",
    name: "Obsidian Frost",
    tagline: "Monochromatic silver glass in dark, royal cobalt sapphire in light",
    accentHex: "#F0F2F5",
    lightAccentHex: "#2563EB",
    dotClass: "bg-slate-200 dark:bg-slate-200",
    borderClass: "border-slate-300",
  },
  {
    id: "frost",
    name: "Ice Cyan",
    tagline: "Cool arctic glass with vibrant electric cyan accents",
    accentHex: "#38BDF8",
    lightAccentHex: "#0284C7",
    dotClass: "bg-sky-400",
    borderClass: "border-sky-500",
  },
  {
    id: "emerald",
    name: "Sage Emerald",
    tagline: "Calm organic mint with soft luminous translucent glass",
    accentHex: "#34D399",
    lightAccentHex: "#059669",
    dotClass: "bg-emerald-400",
    borderClass: "border-emerald-500",
  },
  {
    id: "amethyst",
    name: "Lavender Haze",
    tagline: "Deep minimal violet with vibrant atmospheric glow",
    accentHex: "#A78BFA",
    lightAccentHex: "#7C3AED",
    dotClass: "bg-purple-400",
    borderClass: "border-purple-500",
  },
  {
    id: "coral",
    name: "Sunset Coral",
    tagline: "Luminous warm rose coral with energized glass highlights",
    accentHex: "#FB7185",
    lightAccentHex: "#E11D48",
    dotClass: "bg-rose-400",
    borderClass: "border-rose-500",
  },
  {
    id: "titanium",
    name: "Titanium Slate",
    tagline: "Ultra-minimalist zero-color slate, pure focus",
    accentHex: "#CBD5E1",
    lightAccentHex: "#475569",
    dotClass: "bg-slate-400",
    borderClass: "border-slate-500",
  },
  {
    id: "amber",
    name: "Warm Amber",
    tagline: "Classic warm amber glow with high-contrast surfaces",
    accentHex: "#F59E0B",
    lightAccentHex: "#D97706",
    dotClass: "bg-amber-500",
    borderClass: "border-amber-600",
  },
];

export const QUICK_CUSTOM_SWATCHES = [
  { name: "Electric Blue", hex: "#3B82F6" },
  { name: "Hyper Violet", hex: "#8B5CF6" },
  { name: "Neon Pink", hex: "#EC4899" },
  { name: "Vivid Mint", hex: "#10B981" },
  { name: "Electric Cyan", hex: "#06B6D4" },
  { name: "Radiant Gold", hex: "#F59E0B" },
  { name: "Sunset Orange", hex: "#FB923C" },
  { name: "Crimson Rose", hex: "#EF4444" },
];

export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const clean = hex.replace("#", "").trim();
  if (clean.length === 3) {
    const r = parseInt(clean[0] + clean[0], 16);
    const g = parseInt(clean[1] + clean[1], 16);
    const b = parseInt(clean[2] + clean[2], 16);
    return isNaN(r) || isNaN(g) || isNaN(b) ? null : { r, g, b };
  }
  if (clean.length === 6) {
    const r = parseInt(clean.slice(0, 2), 16);
    const g = parseInt(clean.slice(2, 4), 16);
    const b = parseInt(clean.slice(4, 6), 16);
    return isNaN(r) || isNaN(g) || isNaN(b) ? null : { r, g, b };
  }
  return null;
}

export function rgbToTriplet(r: number, g: number, b: number): string {
  return `${Math.round(r)} ${Math.round(g)} ${Math.round(b)}`;
}

export function getContrastInk(r: number, g: number, b: number): string {
  // Relative luminance according to WCAG 2.1
  const sR = r / 255;
  const sG = g / 255;
  const sB = b / 255;
  const R = sR <= 0.03928 ? sR / 12.92 : Math.pow((sR + 0.055) / 1.055, 2.4);
  const G = sG <= 0.03928 ? sG / 12.92 : Math.pow((sG + 0.055) / 1.055, 2.4);
  const B = sB <= 0.03928 ? sB / 12.92 : Math.pow((sB + 0.055) / 1.055, 2.4);
  const L = 0.2126 * R + 0.7152 * G + 0.0722 * B;
  // If bright background, use dark ink (10 12 16); otherwise white (255 255 255)
  return L > 0.45 ? "10 12 16" : "255 255 255";
}

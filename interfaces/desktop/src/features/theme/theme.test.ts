import { test } from "node:test";
import assert from "node:assert/strict";
import {
  COLOR_TEMPLATES,
  QUICK_CUSTOM_SWATCHES,
  hexToRgb,
  rgbToTriplet,
  getContrastInk,
} from "../../app/themePresets.ts";

test("theme color templates include 7 curated presets", () => {
  const ids = COLOR_TEMPLATES.map((t) => t.id);
  assert.deepEqual(ids, [
    "obsidian",
    "frost",
    "emerald",
    "amethyst",
    "coral",
    "titanium",
    "amber",
  ]);
});

test("default template is obsidian frost with silver in dark and royal cobalt in light", () => {
  const obsidian = COLOR_TEMPLATES.find((t) => t.id === "obsidian");
  assert.ok(obsidian, "obsidian template must exist");
  assert.equal(obsidian.name, "Obsidian Frost");
  assert.equal(obsidian.accentHex.toUpperCase(), "#F0F2F5");
  // Light mode has rich cobalt depth instead of lifeless grey
  assert.equal(obsidian.lightAccentHex.toUpperCase(), "#2563EB");
});

test("all templates have valid metadata, dark and light hex values", () => {
  for (const tpl of COLOR_TEMPLATES) {
    assert.ok(tpl.id.length > 0, "id required");
    assert.ok(tpl.name.length > 0, "name required");
    assert.ok(tpl.tagline.length > 0, "tagline required");
    assert.ok(tpl.accentHex.startsWith("#"), "accentHex must be hex code");
    assert.ok(tpl.lightAccentHex.startsWith("#"), "lightAccentHex must be hex code");
    assert.ok(tpl.dotClass.length > 0, "dotClass required");
    assert.ok(tpl.borderClass.length > 0, "borderClass required");
  }
});

test("custom color converter parses hex to RGB and formats Tailwind triplet", () => {
  const rgb = hexToRgb("#3B82F6");
  assert.ok(rgb);
  assert.equal(rgb.r, 59);
  assert.equal(rgb.g, 130);
  assert.equal(rgb.b, 246);

  const triplet = rgbToTriplet(rgb.r, rgb.g, rgb.b);
  assert.equal(triplet, "59 130 246");
});

test("contrast ink selector picks white text for dark/saturated colors and dark text for bright pastel", () => {
  // Saturated blue (#3B82F6): relative luminance ~0.24 -> white text
  const blueInk = getContrastInk(59, 130, 246);
  assert.equal(blueInk, "255 255 255");

  // Pure white (#FFFFFF): luminance 1.0 -> dark text
  const whiteInk = getContrastInk(255, 255, 255);
  assert.equal(whiteInk, "10 12 16");

  // Pitch black (#000000): luminance 0 -> white text
  const blackInk = getContrastInk(0, 0, 0);
  assert.equal(blackInk, "255 255 255");
});

test("quick custom swatches are defined with 8 vibrant colors", () => {
  assert.equal(QUICK_CUSTOM_SWATCHES.length, 8);
  for (const swatch of QUICK_CUSTOM_SWATCHES) {
    assert.ok(swatch.name.length > 0);
    assert.ok(swatch.hex.startsWith("#"));
  }
});

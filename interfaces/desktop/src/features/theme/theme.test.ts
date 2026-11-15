import { test } from "node:test";
import assert from "node:assert/strict";
import { COLOR_TEMPLATES } from "../../app/themePresets.ts";

test("theme color templates include 6 presets", () => {
  const ids = COLOR_TEMPLATES.map((t) => t.id);
  assert.deepEqual(ids, ["obsidian", "frost", "emerald", "amethyst", "titanium", "amber"]);
});

test("default template is obsidian frost with minimal platinum/silver accent (zero orange)", () => {
  const obsidian = COLOR_TEMPLATES.find((t) => t.id === "obsidian");
  assert.ok(obsidian, "obsidian template must exist");
  assert.equal(obsidian.name, "Obsidian Frost");
  // Accent is silver/platinum, not orange (#F2761E)
  assert.notEqual(obsidian.accentHex.toLowerCase(), "#f2761e");
  assert.equal(obsidian.accentHex.toUpperCase(), "#F0F2F5");
});

test("all templates have valid metadata and swatch colors", () => {
  for (const tpl of COLOR_TEMPLATES) {
    assert.ok(tpl.id.length > 0, "id required");
    assert.ok(tpl.name.length > 0, "name required");
    assert.ok(tpl.tagline.length > 0, "tagline required");
    assert.ok(tpl.accentHex.startsWith("#"), "accentHex must be hex code");
    assert.ok(tpl.dotClass.length > 0, "dotClass required");
    assert.ok(tpl.borderClass.length > 0, "borderClass required");
  }
});

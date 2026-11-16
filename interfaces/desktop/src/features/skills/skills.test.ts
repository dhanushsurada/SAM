import { test } from "node:test";
import assert from "node:assert/strict";
import type { SkillItem } from "../../api/client.ts";

test("skill items support superpowers, anthropic, and custom categories", () => {
  const sampleSkills: SkillItem[] = [
    {
      id: "superpowers.systematic-debugging",
      name: "systematic-debugging",
      title: "Systematic Debugging",
      description: "Root cause analysis before attempting fixes",
      category: "superpowers",
      compiled: true,
      enabled: true,
      use_count: 5,
      last_used: new Date().toISOString(),
      triggers: ["debug", "root cause", "fix bug"],
    },
    {
      id: "anthropic.docx",
      name: "docx",
      title: "Docx Generator & Editor",
      description: "Create and edit Word documents (.docx files)",
      category: "anthropic-agent",
      compiled: true,
      enabled: true,
      use_count: 12,
      last_used: new Date().toISOString(),
      triggers: ["word", "docx", "report"],
    },
    {
      id: "custom.git-sync",
      name: "git-sync",
      title: "Fast Git Synchronization",
      description: "Pulls and rebases worktree branches",
      category: "custom",
      compiled: true,
      enabled: true,
      use_count: 2,
      last_used: null,
      triggers: ["sync", "git pull"],
      command: "git pull --rebase",
    },
  ];

  assert.equal(sampleSkills.length, 3);

  // Category filtering
  const superSkills = sampleSkills.filter((s) => s.category === "superpowers");
  assert.equal(superSkills.length, 1);
  assert.equal(superSkills[0].name, "systematic-debugging");

  const anthropicSkills = sampleSkills.filter((s) => s.category === "anthropic-agent");
  assert.equal(anthropicSkills.length, 1);
  assert.equal(anthropicSkills[0].name, "docx");

  const customSkills = sampleSkills.filter((s) => s.category === "custom");
  assert.equal(customSkills.length, 1);
  assert.equal(customSkills[0].name, "git-sync");
  assert.equal(customSkills[0].command, "git pull --rebase");
});

test("skill search matches on name, title, description, and triggers", () => {
  const skill: SkillItem = {
    name: "test-driven-development",
    title: "Test-Driven Development",
    description: "Enforce strict red-green-refactor cycles prior to implementation",
    category: "superpowers",
    compiled: true,
    enabled: true,
    use_count: 10,
    last_used: null,
    triggers: ["tdd", "red green refactor", "unit test"],
  };

  const matches = (query: string): boolean => {
    const q = query.toLowerCase();
    return (
      skill.name.toLowerCase().includes(q) ||
      (skill.title || "").toLowerCase().includes(q) ||
      skill.description.toLowerCase().includes(q) ||
      (skill.triggers || []).some((t) => t.toLowerCase().includes(q))
    );
  };

  assert.ok(matches("tdd"), "matches trigger");
  assert.ok(matches("red-green"), "matches description");
  assert.ok(matches("Test-Driven"), "matches title");
  assert.ok(!matches("photoshop"), "does not match unrelated query");
});

test("builtin skills flag distinguishes permanent inbuilt capabilities and protects from deletion", () => {
  const builtinSuperpower: SkillItem = {
    id: "superpowers.systematic-debugging",
    name: "systematic-debugging",
    title: "Systematic Debugging",
    description: "Systematic root cause analysis workflow",
    category: "superpowers",
    compiled: true,
    enabled: true,
    builtin: true,
    use_count: 0,
    last_used: null,
  };

  const builtinAnthropic: SkillItem = {
    id: "anthropic.docx",
    name: "docx",
    title: "Docx Generator",
    description: "Office document generation",
    category: "anthropic-agent",
    compiled: true,
    enabled: true,
    builtin: true,
    use_count: 0,
    last_used: null,
  };

  const customUserSkill: SkillItem = {
    id: "custom.my-script",
    name: "my-script",
    title: "My Custom Script",
    description: "User defined test script",
    category: "custom",
    compiled: true,
    enabled: true,
    builtin: false,
    use_count: 0,
    last_used: null,
  };

  const isDeletable = (s: SkillItem): boolean => !s.builtin && s.category === "custom";

  assert.equal(builtinSuperpower.builtin, true);
  assert.equal(builtinAnthropic.builtin, true);
  assert.equal(customUserSkill.builtin, false);

  assert.equal(isDeletable(builtinSuperpower), false, "Builtin superpower cannot be deleted");
  assert.equal(isDeletable(builtinAnthropic), false, "Builtin anthropic skill cannot be deleted");
  assert.equal(isDeletable(customUserSkill), true, "Custom user skill can be deleted");
});

test("supports all expanded inbuilt categories and custom skills", () => {
  const skills: SkillItem[] = [
    { name: "brainstorming", category: "superpowers", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "frontend-design", category: "anthropic-agent", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "connect-apps", category: "connect-apps", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "li-audit", category: "linkedin", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "cold-email", category: "marketing", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "reverse-engineer-anything", category: "reverse-engineering", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "github-automation", category: "plugins", builtin: true, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
    { name: "my-custom-flow", category: "custom", builtin: false, compiled: true, enabled: true, use_count: 0, last_used: null, description: "" },
  ];

  const filterCategory = (cat: string) => {
    if (cat === "all") return skills;
    if (cat === "custom") return skills.filter((s) => s.category === "custom" && !s.builtin);
    return skills.filter((s) => s.category === cat);
  };

  assert.equal(filterCategory("all").length, 8);
  assert.equal(filterCategory("superpowers").length, 1);
  assert.equal(filterCategory("anthropic-agent").length, 1);
  assert.equal(filterCategory("connect-apps").length, 1);
  assert.equal(filterCategory("linkedin").length, 1);
  assert.equal(filterCategory("marketing").length, 1);
  assert.equal(filterCategory("reverse-engineering").length, 1);
  assert.equal(filterCategory("plugins").length, 1);
  assert.equal(filterCategory("custom").length, 1);
});

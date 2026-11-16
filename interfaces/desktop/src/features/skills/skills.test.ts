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

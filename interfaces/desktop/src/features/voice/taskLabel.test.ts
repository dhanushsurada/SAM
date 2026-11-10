import { test } from "node:test";
import assert from "node:assert/strict";
import { isVoiceTask, taskLabel, VOICE_PLACEHOLDER } from "./taskLabel.ts";

const task = (input_type: string, instruction: string, task_id = "t1") => ({ task_id, instruction, input_type });

test("a typed task is labelled with what was typed, whatever transcripts exist", () => {
  assert.equal(taskLabel(task("text", "open Safari"), {}), "open Safari");
  assert.equal(taskLabel(task("text", "open Safari"), { t1: "something else" }), "open Safari");
  assert.equal(taskLabel(task("image+text", "what is this?"), {}), "what is this?");
});

test("a voice task shows what SAM heard", () => {
  assert.equal(taskLabel(task("voice", VOICE_PLACEHOLDER), { t1: "  what time is it  " }), "what time is it");
  assert.equal(taskLabel(task("image+voice", VOICE_PLACEHOLDER), { t1: "describe this" }), "describe this");
});

test("until SAM has heard it, a voice task is a 'Voice message', never the placeholder", () => {
  assert.equal(taskLabel(task("voice", VOICE_PLACEHOLDER), {}), "Voice message");
  assert.equal(taskLabel(task("voice", ""), {}), "Voice message");
  assert.equal(taskLabel(task("voice", VOICE_PLACEHOLDER), { t1: "   " }), "Voice message");
  assert.equal(taskLabel(task("voice", VOICE_PLACEHOLDER), { other: "not mine" }), "Voice message");
});

test("a voice task that carries its own typed instruction keeps it until the transcript is known", () => {
  assert.equal(taskLabel(task("image+voice", "check the chart"), {}), "check the chart");
});

test("isVoiceTask", () => {
  assert.equal(isVoiceTask({ input_type: "voice" }), true);
  assert.equal(isVoiceTask({ input_type: "image+voice" }), true);
  assert.equal(isVoiceTask({ input_type: "text" }), false);
  assert.equal(isVoiceTask({ input_type: "image" }), false);
});

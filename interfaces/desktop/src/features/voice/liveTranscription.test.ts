import { test } from "node:test";
import assert from "node:assert/strict";
import { detectWakeWord, formatTranscript } from "./liveTranscription.ts";

test("detectWakeWord recognizes 'hey sam' and isolates command text", () => {
  const result = detectWakeWord("hey sam what is the weather in San Francisco?");
  assert.equal(result.detected, true);
  assert.equal(result.wakeWordMatched, "hey sam");
  assert.equal(result.commandText, "what is the weather in San Francisco?");
});

test("detectWakeWord recognizes standalone 'sam' with punctuation", () => {
  const result = detectWakeWord("SAM, take a screenshot of my screen");
  assert.equal(result.detected, true);
  assert.equal(result.wakeWordMatched, "sam");
  assert.equal(result.commandText, "take a screenshot of my screen");
});

test("detectWakeWord recognizes solitary wake word without command text yet", () => {
  const result = detectWakeWord("Hey SAM");
  assert.equal(result.detected, true);
  assert.equal(result.wakeWordMatched, "hey sam");
  assert.equal(result.commandText, "");
});

test("detectWakeWord ignores non-wake word phrases", () => {
  const result = detectWakeWord("good morning everyone how are we doing");
  assert.equal(result.detected, false);
  assert.equal(result.wakeWordMatched, "");
  assert.equal(result.commandText, "");
});

test("detectWakeWord supports custom configured wake word", () => {
  const result = detectWakeWord("computer, run tests", "computer");
  assert.equal(result.detected, true);
  assert.equal(result.wakeWordMatched, "computer");
  assert.equal(result.commandText, "run tests");
});

test("formatTranscript normalizes spacing and capitalizes first letter", () => {
  assert.equal(formatTranscript("  hello   world  "), "Hello world");
  assert.equal(formatTranscript(""), "");
});

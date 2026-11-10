import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanForSpeech, excerptForSpeech, MAX_SPOKEN_CHARS, replyToSpeak } from "./speechText.ts";

// ─── cleanForSpeech ──────────────────────────────────────────────────────

test("markdown is stripped the way the server's cleaner does it", () => {
  assert.equal(cleanForSpeech("**Done.** I ran `ls` in *the* folder."), "Done. I ran ls in the folder.");
  assert.equal(cleanForSpeech("## Result\nSee [the docs](https://example.com/docs)."), "Result. See the docs.");
  assert.equal(cleanForSpeech("- one\n- two\n1. three"), "one. two. three");
});

test("code blocks are not read aloud and links are not spelled out", () => {
  assert.equal(
    cleanForSpeech("Run this:\n```sh\nrm -rf /tmp/x\n```\nThen open https://example.com/a/b?c=d now."),
    // The line break after the omitted code is a pause like any other.
    "Run this: (code omitted). Then open a link now.",
  );
});

test("a line break is a full stop, unless the line already ended with punctuation", () => {
  assert.equal(cleanForSpeech("Opened Safari\nWent to GitHub"), "Opened Safari. Went to GitHub");
  assert.equal(cleanForSpeech("Opened Safari.\nWent to GitHub!\nDone?\nYes"), "Opened Safari. Went to GitHub! Done? Yes");
  assert.equal(cleanForSpeech("Hello\n\n\nthere\n"), "Hello. there.");
});

test("whitespace is collapsed and empty text stays empty", () => {
  assert.equal(cleanForSpeech("  a   b \t c  "), "a b c");
  assert.equal(cleanForSpeech(""), "");
  assert.equal(cleanForSpeech("   \n  "), "");
  assert.equal(cleanForSpeech("\n\n"), "", "a reply that is only line breaks is not a lone full stop");
});

test("leading blank lines and runs of blank lines are not extra pauses", () => {
  assert.equal(cleanForSpeech("\n\nHello"), "Hello");
  assert.equal(cleanForSpeech("a\n   \n\t\nb"), "a. b");
});

test("text with nothing speakable in it comes out empty", () => {
  for (const silent of [".", "...", "?!", "---", "👍", " * "]) {
    assert.equal(cleanForSpeech(silent), "", JSON.stringify(silent));
  }
  assert.equal(cleanForSpeech("42"), "42");
  assert.equal(cleanForSpeech("完了"), "完了");
});

// ─── excerptForSpeech ────────────────────────────────────────────────────

test("a short reply is spoken whole", () => {
  assert.equal(excerptForSpeech("Opened Safari and went to GitHub."), "Opened Safari and went to GitHub.");
});

test("a long reply is cut at a sentence end and says where the rest is", () => {
  const sentence = "SAM opened the file and read it carefully. ";
  const excerpt = excerptForSpeech(sentence.repeat(40));
  assert.ok(excerpt.length <= MAX_SPOKEN_CHARS, `length ${excerpt.length}`);
  assert.ok(excerpt.endsWith("The rest is on screen."), excerpt);
  assert.ok(excerpt.includes("carefully. The rest"), "cut after a whole sentence");
});

test("with no sentence end to cut at, it cuts at a word, never in the middle of one", () => {
  const words = Array.from({ length: 300 }, (_, i) => `word${i}`).join(" ");
  const excerpt = excerptForSpeech(words);
  assert.ok(excerpt.length <= MAX_SPOKEN_CHARS, `length ${excerpt.length}`);
  assert.ok(excerpt.endsWith(". The rest is on screen."), excerpt);
  const spoken = excerpt.replace(". The rest is on screen.", "").split(" ");
  assert.ok(spoken.every((word) => /^word\d+$/.test(word)), "only whole words");
});

test("an early sentence end is not a place to cut when most of the excerpt would be thrown away", () => {
  const words = Array.from({ length: 300 }, (_, i) => `word${i}`).join(" ");
  const excerpt = excerptForSpeech(`Ok. ${words}`);
  assert.ok(excerpt.length > 300, `kept only ${excerpt.length} characters: ${excerpt}`);
  assert.ok(excerpt.startsWith("Ok. word0 word1"), excerpt);
  assert.ok(excerpt.endsWith(". The rest is on screen."), excerpt);
});

test("one enormous token is hard-cut but still respects the limit", () => {
  for (const max of [50, 100, MAX_SPOKEN_CHARS]) {
    const excerpt = excerptForSpeech("a".repeat(5000), max);
    assert.ok(excerpt.length <= max, `max ${max}, length ${excerpt.length}`);
    assert.ok(excerpt.endsWith("The rest is on screen."));
  }
});

test("the limit holds for formatted text, which is cleaned before it is measured", () => {
  const excerpt = excerptForSpeech("**bold** ".repeat(400));
  assert.ok(!excerpt.includes("*"));
  assert.ok(excerpt.length <= MAX_SPOKEN_CHARS);
});

// ─── replyToSpeak ────────────────────────────────────────────────────────

test("a completed task speaks its result, or 'Done.' when it has no text", () => {
  assert.equal(replyToSpeak({ status: "completed", result_text: "It is **3 pm**.", error: null }), "It is 3 pm.");
  assert.equal(replyToSpeak({ status: "completed", result_text: "", error: null }), "Done.");
  assert.equal(replyToSpeak({ status: "completed", result_text: null, error: null }), "Done.");
  // A result with nothing speakable in it (found by the whitespace test above:
  // it used to come out as a lone ".") is also just "Done."
  assert.equal(replyToSpeak({ status: "completed", result_text: "\n\n", error: null }), "Done.");
  assert.equal(replyToSpeak({ status: "completed", result_text: "...", error: null }), "Done.");
});

test("a failed task says so, with the start of the reason", () => {
  assert.equal(
    replyToSpeak({ status: "failed", result_text: null, error: "Ollama is not running." }),
    "Sorry, that didn't work. Ollama is not running.",
  );
  assert.equal(replyToSpeak({ status: "failed", result_text: null, error: null }), "Sorry, that didn't work.");
  const long = replyToSpeak({ status: "failed", result_text: null, error: "It broke. ".repeat(100) });
  assert.ok(long !== null && long.length <= "Sorry, that didn't work. ".length + 160, `length ${long?.length}`);
});

test("a cancelled or unfinished task is not spoken", () => {
  assert.equal(replyToSpeak({ status: "cancelled", result_text: "Cancelled.", error: null }), null);
  assert.equal(replyToSpeak({ status: "executing", result_text: null, error: null }), null);
});

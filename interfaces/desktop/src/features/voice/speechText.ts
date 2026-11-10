/**
 * What SAM says out loud. A reply can be long, formatted, full of paths and
 * code; read aloud that is unbearable, and the web view's fallback voice
 * would pronounce the markdown. This turns a reply into a short spoken
 * excerpt (the full text stays on screen) and decides what to say when a
 * task fails. Pure text in, text out.
 *
 * The markdown rules mirror TextToSpeech._clean_for_speech in mouth/tts.py,
 * which the server applies again to whatever it is sent (harmless: cleaned
 * text has nothing left to clean).
 */

/** Longest excerpt spoken for one reply. Also well under the server's
 * 2000-character limit for POST /api/speech. */
export const MAX_SPOKEN_CHARS = 600;

const ON_SCREEN = " The rest is on screen.";

export function cleanForSpeech(text: string): string {
  const cleaned = text
    .replace(/```[\s\S]*?```/g, " (code omitted) ")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1")
    .replace(/\bhttps?:\/\/\S+/g, "a link")
    .replace(/^[-*]\s/gm, "")
    .replace(/^\d+\.\s/gm, "")
    // Blank lines before the first word are not a pause.
    .replace(/^\s+/, "")
    // A line break is a pause: a full stop, unless one is already there. A run
    // of blank lines (even ones holding spaces) is one pause, not several.
    .replace(/([.!?:;])?\s*\n\s*/g, (_match, punctuation: string | undefined) => (punctuation ? `${punctuation} ` : ". "))
    .replace(/\s+/g, " ")
    .trim();
  // Punctuation and symbols on their own are not worth saying aloud.
  return /[\p{L}\p{N}]/u.test(cleaned) ? cleaned : "";
}

/** Cleaned text, cut at a sentence end (or, failing that, a word end) when
 * it is longer than `maxChars`. A cut excerpt says where the rest is. */
export function excerptForSpeech(text: string, maxChars: number = MAX_SPOKEN_CHARS): string {
  const clean = cleanForSpeech(text);
  if (clean.length <= maxChars) return clean;

  // Leave room for the closing full stop and the note about the rest.
  const room = Math.max(0, maxChars - ON_SCREEN.length - 1);
  const head = clean.slice(0, room);
  const sentenceEnds = [...head.matchAll(/[.!?](?=\s|$)/g)];
  const lastEnd = sentenceEnds.length > 0 ? sentenceEnds[sentenceEnds.length - 1] : undefined;
  if (lastEnd !== undefined && lastEnd.index !== undefined && lastEnd.index >= room * 0.4) {
    return head.slice(0, lastEnd.index + 1).trim() + ON_SCREEN;
  }
  const lastSpace = head.lastIndexOf(" ");
  const cut = (lastSpace > 0 ? head.slice(0, lastSpace) : head).replace(/[,;:\s]+$/, "");
  return cut + "." + ON_SCREEN;
}

export interface FinishedTask {
  status: string;
  result_text: string | null;
  error: string | null;
}

/** What to say once a voice task has finished, or null to stay silent
 * (a cancelled task, or one that is not finished). */
export function replyToSpeak(task: FinishedTask): string | null {
  if (task.status === "completed") {
    return excerptForSpeech(task.result_text ?? "") || "Done.";
  }
  if (task.status === "failed") {
    const detail = excerptForSpeech(task.error ?? task.result_text ?? "", 160);
    return detail ? `Sorry, that didn't work. ${detail}` : "Sorry, that didn't work.";
  }
  return null;
}

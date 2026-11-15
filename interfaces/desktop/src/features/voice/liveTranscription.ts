/**
 * Live speech recognition & wake word detection utilities.
 * Handles continuous real-time transcription and wake-word parsing ("hey sam" / "sam")
 * so the user gets simultaneous visual feedback and can rectify misheard text.
 */

export interface WakeWordResult {
  detected: boolean;
  wakeWordMatched: string;
  commandText: string;
}

/** Standard wake word aliases for SAM */
export const DEFAULT_WAKE_WORDS: readonly string[] = [
  "hey sam",
  "ok sam",
  "okay sam",
  "hi sam",
  "hello sam",
  "sam",
];

/**
 * Checks whether an incoming phrase begins with a wake word, and extracts
 * the trailing command text.
 */
export function detectWakeWord(
  phrase: string,
  customWakeWord?: string,
): WakeWordResult {
  if (!phrase || !phrase.trim()) {
    return { detected: false, wakeWordMatched: "", commandText: "" };
  }

  const normalized = phrase.trim().toLowerCase().replace(/[.,!?;:]+$/, "");
  const wakeWords = customWakeWord && customWakeWord.trim()
    ? [customWakeWord.trim().toLowerCase(), ...DEFAULT_WAKE_WORDS]
    : DEFAULT_WAKE_WORDS;

  for (const word of wakeWords) {
    // Check if phrase starts with the wake word
    if (normalized === word) {
      return { detected: true, wakeWordMatched: word, commandText: "" };
    }

    if (normalized.startsWith(word + " ") || normalized.startsWith(word + ", ") || normalized.startsWith(word + "! ")) {
      const matchLen = normalized.startsWith(word + ", ") || normalized.startsWith(word + "! ")
        ? word.length + 2
        : word.length + 1;
      const remainder = phrase.trim().slice(matchLen).trim();
      return {
        detected: true,
        wakeWordMatched: word,
        commandText: remainder,
      };
    }
  }

  return { detected: false, wakeWordMatched: "", commandText: "" };
}

/**
 * Normalizes live transcribed text: collapses duplicate spaces, trims,
 * and capitalizes the first character for clean presentation.
 */
export function formatTranscript(raw: string): string {
  const trimmed = raw.trim().replace(/\s+/g, " ");
  if (!trimmed) return "";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

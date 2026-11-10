import * as client from "@/api/client";

/**
 * The seam between the UI and SAM's voice, same shape as services/iqoo.ts
 * and services/brain.ts. Real: interfaces/api/server.py POST /api/speech,
 * which renders text with the Kokoro/Piper engines in mouth/tts.py. There is
 * no demo implementation behind it.
 */
export interface SpeechService {
  synthesize(text: string, signal?: AbortSignal): Promise<ArrayBuffer>;
}

export const speechService: SpeechService = {
  synthesize: client.synthesizeSpeech,
};

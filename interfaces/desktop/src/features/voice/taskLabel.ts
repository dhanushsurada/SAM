/**
 * How a voice task is named on screen. SAM's gateway keeps the instruction a
 * voice task was created with ("(voice command)"), and what the person
 * actually said exists only as the transcript carried by the task's
 * "perceiving" event. Wherever a task's instruction is shown, a voice task
 * shows what SAM heard instead (or "Voice message" until it has heard it).
 */

/** The instruction a touch-to-talk task is created with: the gateway needs a
 * non-empty one, and the words themselves come from the audio. Matches the
 * phone client's placeholder. */
export const VOICE_PLACEHOLDER = "(voice command)";

const VOICE_INPUT_TYPES: readonly string[] = ["voice", "image+voice"];

export interface LabelledTask {
  task_id: string;
  instruction: string;
  input_type: string;
}

export function isVoiceTask(task: { input_type: string }): boolean {
  return VOICE_INPUT_TYPES.includes(task.input_type);
}

export function taskLabel(task: LabelledTask, transcripts: Readonly<Record<string, string>>): string {
  if (!isVoiceTask(task)) return task.instruction;
  const heard = transcripts[task.task_id]?.trim();
  if (heard) return heard;
  const typed = task.instruction.trim();
  return typed && typed !== VOICE_PLACEHOLDER ? typed : "Voice message";
}

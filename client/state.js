/**
 * iQOO Phone Client — State (Phase 1)
 *
 * Deliberately tiny: no framework, no build step, per PDR 8.2 ("least
 * disruptive technology compatible with the current repository"). One
 * plain object plus a render() dispatcher that app.js calls after every
 * mutation.
 */

const STATE = {
  view: "home",           // "home" | "task"
  connected: false,        // last known /api/iqoo/health result
  taskId: null,
  instruction: "",
  status: null,            // queued|received|understanding|planning|executing|verifying|completed|failed|cancelled
  events: [],              // [{phase, message, timestamp}]
  resultText: null,
  errorText: null,
  pendingImage: null,      // Phase 1: captured but not yet submitted (see camera.js)
};

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);
const PHASE_ORDER = ["received", "understanding", "planning", "executing", "verifying"];

function resetTaskState() {
  STATE.taskId = null;
  STATE.status = null;
  STATE.events = [];
  STATE.resultText = null;
  STATE.errorText = null;
}

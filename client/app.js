/**
 * iQOO Phone Client — App (Phase 1)
 *
 * Wires state.js + api.js + events.js + camera.js + voice.js into the
 * markup in index.html. No framework, no build step — plain DOM.
 */

const EL = {};

function cacheElements() {
  EL.connDot = document.getElementById("conn-dot");
  EL.connLabel = document.getElementById("conn-label");
  EL.viewHome = document.getElementById("view-home");
  EL.viewTask = document.getElementById("view-task");
  EL.instruction = document.getElementById("instruction");
  EL.submitBtn = document.getElementById("submit-btn");
  EL.taskInstruction = document.getElementById("task-instruction");
  EL.phaseList = document.getElementById("phase-list");
  EL.eventLog = document.getElementById("event-log");
  EL.resultBox = document.getElementById("result-box");
  EL.resultStatus = document.getElementById("result-status");
  EL.resultText = document.getElementById("result-text");
  EL.cancelBtn = document.getElementById("cancel-btn");
  EL.retryBtn = document.getElementById("retry-btn");
  EL.newTaskBtn = document.getElementById("new-task-btn");
  EL.errorBanner = document.getElementById("error-banner");
}

function showError(message) {
  EL.errorBanner.textContent = message;
  EL.errorBanner.classList.remove("hidden");
  setTimeout(() => EL.errorBanner.classList.add("hidden"), 5000);
}

function render() {
  EL.viewHome.classList.toggle("hidden", STATE.view !== "home");
  EL.viewTask.classList.toggle("hidden", STATE.view !== "task");

  if (STATE.view !== "task") return;

  EL.taskInstruction.textContent = STATE.instruction;

  // Phase checklist
  [...EL.phaseList.children].forEach((li) => {
    const phase = li.dataset.phase;
    li.classList.remove("active", "done", "failed");
    const idx = PHASE_ORDER.indexOf(phase);
    const currentIdx = PHASE_ORDER.indexOf(STATE.status);
    if (STATE.status === "failed" || STATE.status === "cancelled") {
      if (idx <= currentIdx || currentIdx === -1) li.classList.add("failed");
    } else if (TERMINAL_STATUSES.has(STATE.status)) {
      li.classList.add("done");
    } else if (phase === STATE.status) {
      li.classList.add("active");
    } else if (currentIdx !== -1 && idx < currentIdx) {
      li.classList.add("done");
    }
  });

  EL.eventLog.innerHTML = STATE.events
    .map((e) => `<div>[${e.phase}] ${escapeHtml(e.message)}</div>`)
    .join("");
  EL.eventLog.scrollTop = EL.eventLog.scrollHeight;

  const finished = TERMINAL_STATUSES.has(STATE.status);
  EL.resultBox.classList.toggle("hidden", !finished);
  if (finished) {
    EL.resultStatus.textContent = STATE.status.toUpperCase();
    EL.resultStatus.className = `result-status ${STATE.status}`;
    EL.resultText.textContent = STATE.resultText || STATE.errorText || "";
  }

  EL.cancelBtn.classList.toggle("hidden", finished);
  EL.retryBtn.classList.toggle("hidden", !finished);
  EL.newTaskBtn.classList.toggle("hidden", !finished);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function refreshConnection() {
  try {
    const health = await API.health();
    STATE.connected = true;
    EL.connDot.classList.remove("offline");
    EL.connDot.classList.add("online");
    EL.connLabel.textContent = health.brain_reachable ? "connected" : "connected — brain unreachable";
  } catch (e) {
    STATE.connected = false;
    EL.connDot.classList.remove("online");
    EL.connDot.classList.add("offline");
    EL.connLabel.textContent = "disconnected";
  }
}

async function submitTask() {
  const instruction = EL.instruction.value.trim();
  if (!instruction) {
    showError("Type or speak an instruction first.");
    return;
  }

  EL.submitBtn.disabled = true;
  try {
    const record = await API.createTask(instruction, "text", []);
    resetTaskState();
    STATE.taskId = record.task_id;
    STATE.instruction = instruction;
    STATE.status = record.status;
    STATE.view = "task";
    render();

    EVENTS.subscribe(STATE.taskId, {
      onEvent: (event) => {
        STATE.status = event.phase;
        STATE.events.push(event);
        render();
      },
      onDone: (event) => {
        STATE.status = event.phase;
        if (event.phase === "completed") STATE.resultText = event.message;
        else STATE.errorText = event.message;
        render();
      },
      onError: () => showError("Lost connection to SAM — result will still be waiting when you reconnect."),
    });
  } catch (e) {
    showError(e.message || "Could not reach SAM.");
  } finally {
    EL.submitBtn.disabled = false;
  }
}

async function cancelTask() {
  if (!STATE.taskId) return;
  try {
    await API.cancelTask(STATE.taskId);
  } catch (e) {
    showError("Could not cancel — it may have already finished.");
  }
}

async function retryTask() {
  if (!STATE.taskId) return;
  try {
    const record = await API.retryTask(STATE.taskId);
    resetTaskState();
    STATE.taskId = record.task_id;
    STATE.status = record.status;
    render();
    EVENTS.subscribe(STATE.taskId, {
      onEvent: (event) => { STATE.status = event.phase; STATE.events.push(event); render(); },
      onDone: (event) => {
        STATE.status = event.phase;
        if (event.phase === "completed") STATE.resultText = event.message;
        else STATE.errorText = event.message;
        render();
      },
      onError: () => showError("Lost connection to SAM."),
    });
  } catch (e) {
    showError("Retry failed.");
  }
}

function newTask() {
  EVENTS.close();
  resetTaskState();
  STATE.view = "home";
  EL.instruction.value = "";
  CAMERA.reset();
  render();
}

function init() {
  cacheElements();
  CAMERA.init();
  VOICE.init();

  EL.submitBtn.addEventListener("click", submitTask);
  EL.cancelBtn.addEventListener("click", cancelTask);
  EL.retryBtn.addEventListener("click", retryTask);
  EL.newTaskBtn.addEventListener("click", newTask);

  refreshConnection();
  setInterval(refreshConnection, 8000);
  render();
}

document.addEventListener("DOMContentLoaded", init);

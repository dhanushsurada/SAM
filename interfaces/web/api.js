/**
 * iQOO Phone Client — API (Phase 1)
 *
 * Thin fetch() wrapper around the endpoints in interfaces/api/server.py. All paths
 * are relative so this works whether the client is served by SAM itself
 * (default) or opened separately and pointed at a different host during
 * development.
 */

const API = {
  base: "",

  async health() {
    const res = await fetch(`${this.base}/api/iqoo/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
  },

  async createTask(instruction, inputType = "text", attachments = []) {
    const res = await fetch(`${this.base}/api/iqoo/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction, input_type: inputType, attachments }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ? JSON.stringify(body.detail) : `Task creation failed: ${res.status}`);
    }
    return res.json();
  },

  async getTask(taskId) {
    const res = await fetch(`${this.base}/api/iqoo/tasks/${taskId}`);
    if (!res.ok) throw new Error(`Task not found: ${res.status}`);
    return res.json();
  },

  async cancelTask(taskId) {
    const res = await fetch(`${this.base}/api/iqoo/tasks/${taskId}/cancel`, { method: "POST" });
    if (!res.ok) throw new Error(`Cancel failed: ${res.status}`);
    return res.json();
  },

  async retryTask(taskId) {
    const res = await fetch(`${this.base}/api/iqoo/tasks/${taskId}/retry`, { method: "POST" });
    if (!res.ok) throw new Error(`Retry failed: ${res.status}`);
    return res.json();
  },
};

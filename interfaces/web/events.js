/**
 * iQOO Phone Client — Execution Events (Phase 1)
 *
 * Subscribes to GET /api/iqoo/tasks/{id}/events via EventSource (SSE).
 * Chosen over WebSocket per PDR 8.5 ("SSE or another appropriate
 * mechanism") — one-directional server->phone progress is all Phase 1
 * needs, and EventSource auto-reconnects on transient drops for free,
 * which matters over a real Office Kit / hotspot link.
 */

const EVENTS = {
  _source: null,

  subscribe(taskId, { onEvent, onDone, onError }) {
    this.close();
    const url = `${API.base}/api/iqoo/tasks/${taskId}/events`;
    const source = new EventSource(url);
    this._source = source;

    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        onEvent(event);
        if (TERMINAL_STATUSES.has(event.phase)) {
          this.close();
          onDone(event);
        }
      } catch (e) {
        console.error("Malformed SSE event", e, msg.data);
      }
    };

    source.onerror = () => {
      // EventSource retries automatically; if the task already finished
      // (server closed the stream on purpose) this fires once harmlessly.
      // Fall back to a single poll so the UI doesn't stall indefinitely
      // if the stream truly died mid-task.
      API.getTask(taskId)
        .then((record) => {
          if (TERMINAL_STATUSES.has(record.status)) {
            this.close();
            onDone({ phase: record.status, message: record.result_text || record.error || "" });
          } else if (onError) {
            onError();
          }
        })
        .catch(() => onError && onError());
    };
  },

  close() {
    if (this._source) {
      this._source.close();
      this._source = null;
    }
  },
};

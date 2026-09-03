// VEDA API client (M8-B).
//
// Plain JS, no JSX, no build step — loaded as a regular <script> before
// the text/babel files in index.html. Same-origin: api/app.py serves
// this whole frontend/ directory itself, so there is no base URL to
// configure and nothing here ever points off 127.0.0.1.
//
// Every function here maps 1:1 to one real endpoint from the M8 audit's
// endpoint map — nothing invented, nothing client-side that duplicates
// server logic. A non-2xx response's `detail` field (FastAPI's standard
// HTTPException shape) is surfaced as the thrown Error's message so the
// UI can show the real reason (e.g. "A task is already running...",
// "Unsupported file type '.exe'...") instead of a generic failure.

const Api = (() => {
  async function request(path, options = {}) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {
        /* response wasn't JSON — keep the status-line message */
      }
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  return {
    status: () => request('/api/status'),
    model: () => request('/api/model'),

    listDocuments: () => request('/api/documents'),
    uploadDocument: (file) => {
      const form = new FormData();
      form.append('file', file);
      return request('/api/documents', { method: 'POST', body: form });
    },

    searchKnowledge: (query, topK = 5) =>
      request('/api/knowledge/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: topK }),
      }),

    createTask: (task) =>
      request('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task }),
      }),
    getTask: (taskId) => request(`/api/tasks/${taskId}`),
    getSovereignty: (taskId) => request(`/api/sovereignty/${taskId}`),

    // Not a fetch — this is a real, direct download link for the
    // browser (used as an <a href> target), not JSON to parse.
    deliverableFileUrl: (taskId) => `/api/tasks/${taskId}/deliverable/file`,
  };
})();

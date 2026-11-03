/*
 * Thin client for the MeetWise FastAPI backend. In development, /api requests
 * are proxied by Vite; production builds can set VITE_APP_API_URL to the backend
 * origin. Errors are thrown as Error with the server's message.
 */
const apiBaseUrl = import.meta.env.VITE_APP_API_URL?.replace(/\/+$/, "") || "";

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${apiBaseUrl}/api${path}`, {
    ...options,
    headers: isForm || !options.body ? options.headers : { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let message = response.statusText || `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

export const api = {
  health: () => request("/health"),

  meetings: {
    list: () => request("/meetings"),
    get: (id) => request(`/meetings/${id}`),
    update: (id, patch) => request(`/meetings/${id}`, json("PATCH", patch)),
    upload: (formData) => request("/meetings", { method: "POST", body: formData }),
    // Utterances with stable IDs, used by citations and evidence links.
    transcript: (id) => request(`/meetings/${id}/transcript`),
  },

  tasks: {
    list: (params = {}) => {
      const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
      return request(`/tasks${query ? `?${query}` : ""}`);
    },
    update: (id, status) => request(`/tasks/${id}`, json("PATCH", { status })),
    history: (id) => request(`/tasks/${id}/history`),
  },

  people: {
    list: () => request("/people"),
    save: (person) => request(`/people/${person.id}`, json("PUT", person)),
    remove: (id) => request(`/people/${id}`, { method: "DELETE" }),
  },

  events: {
    range: (start, end) => request(`/events?start=${start}&end=${end}`),
    pending: () => request("/events/pending"),
    create: (body) => request("/events", json("POST", body)),
    update: (id, body) => request(`/events/${id}`, json("PATCH", body)),
    confirm: (id, body = {}) => request(`/events/${id}/confirm`, json("POST", body)),
    remove: (id) => request(`/events/${id}`, { method: "DELETE" }),
  },

  chat: {
    ask: (body) => request("/chat", json("POST", body)),
    sessions: () => request("/chat/sessions"),
    session: (id) => request(`/chat/sessions/${id}`),
  },

  search: (body) => request("/search", json("POST", body)),
};

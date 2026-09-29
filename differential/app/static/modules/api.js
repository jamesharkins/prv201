// Thin client for the FastAPI backend (differential/app/server.py).
// Same-origin only; no external requests.

export class ApiError extends Error {
  constructor(message, status = 0, detail = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function detailText(data) {
  if (!data) return "";
  if (typeof data === "string") {
    // FastAPI's default 500 body is the plain text "Internal Server Error".
    return data.length > 300 ? `${data.slice(0, 300)}…` : data;
  }
  const d = data.detail;
  if (Array.isArray(d)) {
    // Pydantic validation errors: [{loc, msg, type}, ...]
    return d.map((x) => (x && x.msg ? `${(x.loc || []).slice(1).join(".")}: ${x.msg}` : String(x))).join("; ");
  }
  if (typeof d === "string") return d;
  return "";
}

async function request(method, path, { json, form, timeout = 60000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const init = { method, signal: ctrl.signal, headers: { Accept: "application/json" } };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new ApiError("The server took too long to answer. Try again.", 0);
    }
    throw new ApiError("Cannot reach the Differential server. Check that it is running.", 0);
  } finally {
    clearTimeout(timer);
  }
  const type = res.headers.get("content-type") || "";
  let data = null;
  try {
    data = type.includes("application/json") ? await res.json() : await res.text();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = detailText(data);
    throw new ApiError(detail || `HTTP ${res.status}`, res.status, detail);
  }
  return data;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request("GET", "/api/health", { timeout: 15000 }),
  circuits: () => request("GET", "/api/circuits", { timeout: 30000 }),
  circuit: (cid) => request("GET", `/api/circuits/${enc(cid)}`, { timeout: 30000 }),
  newSession: (body) => request("POST", "/api/sessions", { json: body, timeout: 180000 }),
  state: (sid) => request("GET", `/api/sessions/${enc(sid)}`),
  message: (sid, text) => request("POST", `/api/sessions/${enc(sid)}/messages`,
    { json: { text }, timeout: 180000 }),
  measure: (sid, key) => request("POST", `/api/sessions/${enc(sid)}/measure`, { json: { key } }),
  reading: (sid, key, value) => request("POST", `/api/sessions/${enc(sid)}/readings`,
    { json: { key, value } }),
  discharge: (sid, readings) => request("POST", `/api/sessions/${enc(sid)}/discharge`,
    { json: { readings } }),
  approveRemoval: (sid, note) => request("POST", `/api/sessions/${enc(sid)}/approve_removal`,
    { json: { note } }),
  bringUp: (sid, method) => request("POST", `/api/sessions/${enc(sid)}/bring_up`,
    { json: { method } }),
  guess: (sid, key) => request("POST", `/api/sessions/${enc(sid)}/guess`, { json: { key } }),
  supervisor: (sid, name) => request("POST", `/api/sessions/${enc(sid)}/supervisor`, { json: { name } }),
  photo: (sid, file) => {
    const form = new FormData();
    form.append("file", file, file.name || "meter.jpg");
    return request("POST", `/api/sessions/${enc(sid)}/photos`, { form, timeout: 120000 });
  },
  confirmPhoto: (sid, pid, key, value) => request("POST",
    `/api/sessions/${enc(sid)}/photos/${enc(pid)}/confirm`, { json: { key, value } }),
  ticket: (sid) => request("GET", `/api/sessions/${enc(sid)}/ticket`),
  signoff: (sid, name) => request("POST", `/api/sessions/${enc(sid)}/ticket/signoff`,
    { json: { name } }),
  reveal: (sid, endSession = false) => request("POST", `/api/sessions/${enc(sid)}/reveal`,
    { json: { end_session: endSession } }),
  replays: () => request("GET", "/api/replays"),
  replay: (name) => request("GET", `/api/replays/${enc(name)}`),
};

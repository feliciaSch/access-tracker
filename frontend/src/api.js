// Every call from the browser to the backend goes through this one function.
// VITE_API_URL is set in Vercel's settings. Vite bakes it into the code at BUILD time,
// so if you change it you must redeploy.
export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

let lastRequestId = null;
const listeners = new Set();
export const onRequestId = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

export async function api(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // fetch only throws when there's no response at all: backend down/asleep, wrong URL, or CORS blocked.
    throw new Error(`Couldn't reach the API at ${API_URL}. It may be waking up (free tier) — try again in 30s.`);
  }

  // The backend tags each response with an ID that also appears in its logs.
  lastRequestId = res.headers.get("X-Request-ID");
  listeners.forEach((fn) => fn({ id: lastRequestId, method, path, status: res.status }));

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ");
    const err = new Error(msg || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

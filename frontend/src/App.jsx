import { useCallback, useEffect, useState } from "react";
import { api, API_URL, onRequestId } from "./api.js";

const STATUSES = ["all", "pending", "approved", "denied"];
const fmt = (iso) => new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" });

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem("session")) || null;
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(loadSession);

  const save = (s) => {
    setSession(s);
    try {
      if (s) localStorage.setItem("session", JSON.stringify(s));
      else localStorage.removeItem("session");
    } catch {
      /* storage unavailable — session just won't survive a reload */
    }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark">◆</span> Access Tracker
        </div>
        {session && (
          <div className="who">
            <span>{session.username}</span>
            <span className={`role role-${session.role}`}>{session.role}</span>
            <button className="ghost" onClick={() => save(null)}>Log out</button>
          </div>
        )}
      </header>
      <main>{session ? <Tracker session={session} onExpired={() => save(null)} /> : <Login onLogin={save} />}</main>
      <TraceBar />
    </div>
  );
}

function Login({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api(mode === "login" ? "/auth/login" : "/auth/register", {
        method: "POST",
        body: { username, password },
      });
      onLogin({ token: data.access_token, username: data.username, role: data.role });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <p className="muted">
        {mode === "login" ? "Approvers and requesters sign in here." : "New accounts are requesters."}
      </p>
      <label>
        Username
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={8}
          required
        />
      </label>
      {error && <div className="error">{error}</div>}
      <button className="primary" disabled={busy}>{busy ? "…" : mode === "login" ? "Sign in" : "Register"}</button>
      <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "No account? Register" : "Have an account? Sign in"}
      </button>
    </form>
  );
}

function Tracker({ session, onExpired }) {
  const [requests, setRequests] = useState([]);
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const isApprover = session.role === "approver";

  const call = useCallback(
    async (path, opts = {}) => {
      try {
        return await api(path, { ...opts, token: session.token });
      } catch (err) {
        if (err.status === 401) onExpired();
        throw err;
      }
    },
    [session.token, onExpired]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (status !== "all") params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    try {
      setRequests(await call(`/requests?${params}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [status, query, call]);

  useEffect(() => {
    const t = setTimeout(load, 250); // small delay so typing in search doesn't fire a request per keystroke
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="grid">
      <NewRequest call={call} onCreated={load} />
      <section className="card list">
        <div className="list-head">
          <h2>Requests</h2>
          <div className="filters">
            <div className="tabs">
              {STATUSES.map((s) => (
                <button key={s} className={s === status ? "tab active" : "tab"} onClick={() => setStatus(s)}>
                  {s}
                </button>
              ))}
            </div>
            <input
              className="search"
              placeholder="Search requester, resource, reason…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>
        {error && <div className="error">{error}</div>}
        {loading && requests.length === 0 ? (
          <p className="muted pad">Loading…</p>
        ) : requests.length === 0 ? (
          <p className="muted pad">No requests match.</p>
        ) : (
          <ul className="rows">
            {requests.map((r) => (
              <RequestRow key={r.id} r={r} call={call} isApprover={isApprover} onChanged={load} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function NewRequest({ call, onCreated }) {
  const blank = { resource: "", access_level: "read", justification: "" };
  const [form, setForm] = useState(blank);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const created = await call("/requests", { method: "POST", body: form });
      setForm(blank);
      setMsg({ ok: true, text: `Request #${created.id} submitted.` });
      onCreated();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card new" onSubmit={submit}>
      <h2>New access request</h2>
      <label>
        System / resource
        <input value={form.resource} onChange={set("resource")} placeholder="e.g. prod-postgres, GitHub org" required />
      </label>
      <label>
        Access level
        <select value={form.access_level} onChange={set("access_level")}>
          <option value="read">read</option>
          <option value="write">write</option>
          <option value="admin">admin</option>
        </select>
      </label>
      <label>
        Justification
        <textarea
          value={form.justification}
          onChange={set("justification")}
          rows={4}
          minLength={5}
          placeholder="Why do you need this, and for how long?"
          required
        />
      </label>
      {msg && <div className={msg.ok ? "ok" : "error"}>{msg.text}</div>}
      <button className="primary" disabled={busy}>{busy ? "Submitting…" : "Submit request"}</button>
    </form>
  );
}

function RequestRow({ r, call, isApprover, onChanged }) {
  const [open, setOpen] = useState(false);
  const [audit, setAudit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      try {
        setAudit(await call(`/requests/${r.id}/audit`));
      } catch (err) {
        setError(err.message);
      }
    }
  }

  async function changeStatus(newStatus) {
    const note = newStatus === "denied" ? window.prompt("Reason for denying (optional):") ?? undefined : undefined;
    setBusy(true);
    setError("");
    try {
      await call(`/requests/${r.id}/status`, { method: "PATCH", body: { status: newStatus, note } });
      onChanged();
      if (open) setAudit(await call(`/requests/${r.id}/audit`));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="row">
      <div className="row-main">
        <button className="row-toggle" onClick={toggle} aria-expanded={open}>
          <span className="id">#{r.id}</span>
          <span className="res">{r.resource}</span>
          <span className="lvl">{r.access_level}</span>
          <span className="by">{r.requester}</span>
          <span className="when">{fmt(r.created_at)}</span>
        </button>
        <span className={`pill pill-${r.status}`}>{r.status}</span>
        {isApprover && (
          <div className="actions">
            {r.status !== "approved" && (
              <button className="approve" disabled={busy} onClick={() => changeStatus("approved")}>Approve</button>
            )}
            {r.status !== "denied" && (
              <button className="deny" disabled={busy} onClick={() => changeStatus("denied")}>Deny</button>
            )}
          </div>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {open && (
        <div className="detail">
          <p className="just">{r.justification}</p>
          <h3>Audit trail</h3>
          {!audit ? (
            <p className="muted">Loading…</p>
          ) : (
            <ol className="audit">
              {audit.map((e) => (
                <li key={e.id}>
                  <time>{fmt(e.created_at)}</time>
                  <span>
                    <b>{e.actor}</b>{" "}
                    {e.action === "created" ? "submitted the request" : (
                      <>changed status <code>{e.old_status}</code> → <code>{e.new_status}</code></>
                    )}
                    {e.note && <em> — “{e.note}”</em>}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}

// Shows the last API call and its request ID, so in the demo you can copy the ID
// and find the exact same request in the backend's logs.
function TraceBar() {
  const [last, setLast] = useState(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => onRequestId(setLast), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(last.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard blocked; the ID is still visible */
    }
  }

  return (
    <footer className="trace">
      <span className="muted">API: {API_URL}</span>
      {last && (
        <span>
          last call <code>{last.method} {last.path.split("?")[0]}</code> → <code>{last.status}</code> · request id{" "}
          <button className="trace-id" onClick={copy} title="Copy">{copied ? "copied" : last.id}</button>
        </span>
      )}
    </footer>
  );
}

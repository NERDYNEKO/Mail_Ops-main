import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Contact, type Log, type Meta } from "./api";
import { Drawer } from "./Drawer";
import { Templates } from "./Templates";

function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({ mutationFn: () => api("/auth/login", "POST", { email, password }), onSuccess: onDone });
  return (
    <form className="login card" onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
      <h1>Mapster Outreach</h1>
      <input placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
      <input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {login.error && <p className="err">{(login.error as Error).message}</p>}
      <button className="btn pri" disabled={login.isPending}>Sign in</button>
    </form>
  );
}

const FILTERS = ["all", "new", "drafted", "approved", "sent", "replied", "stopped", "bounced"];

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api("/auth/me") });
  const authed = me.isSuccess;
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta"), enabled: authed });
  const contacts = useQuery({ queryKey: ["contacts"], queryFn: () => api<Contact[]>("/contacts"), enabled: authed, refetchInterval: 4000 });
  const activity = useQuery({ queryKey: ["activity"], queryFn: () => api<Log[]>("/activity"), enabled: authed, refetchInterval: 3000 });
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<string | "new" | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [toast, setToast] = useState("");

  const refresh = () => qc.invalidateQueries();
  const say = (m: string) => { setToast(m); setTimeout(() => setToast(""), 3500); };
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api<{ ok?: boolean; msg?: string }>(path, "POST", body ?? {}),
    onSuccess: (r) => { if (r?.msg === "none") say("Nothing ready to send"); refresh(); },
    onError: (e: Error) => say(e.message),
  });

  if (me.isPending) return null;
  if (!authed) return <Login onDone={refresh} />;

  const all = contacts.data ?? [];
  const rows = all.filter((c) => filter === "all" || c.status === filter);
  const counts = (s: string) => all.filter((c) => (s === "all" ? true : c.status === s)).length;
  const ids = [...selected];
  const bulk = (action: string) => act.mutate({ path: "/bulk", body: { action, ids } });
  const toggle = (id: string) => setSelected((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="app">
      <header>
        <h1>Mapster Outreach</h1>
        <div className="sp" />
        <label className="auto" title={`Checks every 30 min, sends ${meta.data?.window[0]}:00 to ${meta.data?.window[1]}:00`}>
          <input type="checkbox" checked={meta.data?.autopilot ?? false}
            onChange={async (e) => { await api("/settings/autopilot", "PUT", { on: e.target.checked }); refresh(); }} />
          Autopilot
        </label>
        <button className="btn" onClick={() => setShowTemplates(true)}>Follow up messages</button>
        <button className="btn" onClick={() => act.mutate({ path: "/run", body: { dry: true } })}>Dry run</button>
        <button className="btn pri" onClick={() => confirm("Send all approved emails and due follow ups now?") && act.mutate({ path: "/run", body: { dry: false } })}>Send approved</button>
        <button className="btn" onClick={async () => { await api("/auth/logout", "POST"); qc.clear(); location.reload(); }}>Sign out</button>
      </header>

      {meta.data && !meta.data.hasMailPassword && <div className="warn">GMAIL_APP_PASSWORD is not set, sending is disabled.</div>}
      {meta.data && !meta.data.hasLlmKey && <div className="warn">ANTHROPIC_API_KEY is not set, emails cannot be generated.</div>}

      <div className="bar">
        {FILTERS.map((f) => (
          <button key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>{f} <b>{counts(f)}</b></button>
        ))}
        <div className="sp" />
        <button className="btn pri" onClick={() => setOpen("new")}>Add contact</button>
      </div>

      {ids.length > 0 && (
        <div className="bar sel">
          <span>{ids.length} selected</span>
          {["generate", "approve", "unapprove", "stop", "resume"].map((a) => <button key={a} className="btn" onClick={() => bulk(a)}>{a}</button>)}
          <button className="btn pri" onClick={() => confirm(`Send ${ids.length} email(s) now?`) && bulk("send")}>send</button>
        </div>
      )}

      <table className="card">
        <thead><tr><th><input type="checkbox" checked={rows.length > 0 && rows.every((r) => selected.has(r.id))}
          onChange={(e) => setSelected(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())} /></th>
          <th>Contact</th><th>Event</th><th>Type</th><th>Status</th><th>Follow ups</th><th>Next</th></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} onClick={() => setOpen(c.id)}>
              <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} /></td>
              <td><b>{c.name || c.email}</b><div className="muted">{c.email}</div></td>
              <td>{c.event || c.org}</td>
              <td>{c.category}</td>
              <td><span className={`pill ${c.status}`}>{c.status}</span></td>
              <td>{c.followups}</td>
              <td className="muted">{c.nextDue ? new Date(c.nextDue).toLocaleString() : ""}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={7} className="muted empty">Nothing here yet.</td></tr>}
        </tbody>
      </table>

      <section className="log card">
        <h3>Activity</h3>
        <div>{(activity.data ?? []).slice().reverse().map((l) => (
          <div key={l._id} className={l.level === "error" ? "err" : ""}>
            <span className="muted">{new Date(l.createdAt).toLocaleTimeString()}</span> {l.message}
          </div>
        ))}</div>
      </section>

      {open && (
        <Drawer key={open} id={open === "new" ? null : open} contact={all.find((c) => c.id === open)} meta={meta.data}
          onClose={() => setOpen(null)} onChange={refresh} say={say} />
      )}
      {showTemplates && <Templates onClose={() => setShowTemplates(false)} say={say} />}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Contact, type Meta, type Preview } from "./api";

type Form = Pick<Contact, "name" | "email" | "category" | "org" | "event" | "coverName" | "website" | "about">;
const EMPTY: Form = { name: "", email: "", category: "client", org: "", event: "", coverName: "", website: "", about: "" };

interface Props {
  id: string | null; contact?: Contact; meta?: Meta; onClose: () => void; onChange: () => void; say: (m: string) => void;
}

export function Drawer({ id, contact, meta, onClose, onChange, say }: Props) {
  const [form, setForm] = useState<Form>(contact ?? EMPTY);
  const [subject, setSubject] = useState(contact?.subject ?? "");
  const [body, setBody] = useState(contact?.body ?? "");
  const [tab, setTab] = useState<"contact" | "email" | "preview">(contact && contact.status !== "new" ? "email" : "contact");
  const editable = !contact || ["new", "drafted", "approved"].includes(contact.status);
  const hasDraft = !!contact && contact.status !== "new";

  const preview = useQuery({ queryKey: ["preview", id, contact?.status, contact?.followups], queryFn: () => api<Preview>(`/contacts/${id}/preview`), enabled: tab === "preview" && hasDraft });

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); if (ok) say(ok); onChange(); } catch (e) { say((e as Error).message); }
  };
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const act = (a: string, ok?: string) => run(() => api(`/contacts/${id}/${a}`, "POST", {}), ok);
  const saveEmail = () => api(`/contacts/${id}/email`, "PUT", { subject, body });

  return (
    <aside className="drawer">
      <div className="dh">
        <h2>{id ? contact?.name || contact?.email : "New contact"}</h2>
        {contact && <span className={`pill ${contact.status}`}>{contact.status}</span>}
        <div className="sp" /><button className="btn" onClick={onClose}>Close</button>
      </div>
      {id && <div className="tabs">{(["contact", "email", "preview"] as const).map((t) => (
        <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t}</button>))}</div>}

      {tab === "contact" && (
        <div className="form">
          <label>Name<input value={form.name} onChange={set("name")} /></label>
          <label>Email<input type="email" value={form.email} onChange={set("email")} /></label>
          <label>Type<select value={form.category} onChange={set("category")}><option value="client">Client (proposal PDF)</option><option value="network">Network (pitch deck)</option></select></label>
          <label>Organisation<input value={form.org} onChange={set("org")} /></label>
          <label>Event<input value={form.event} onChange={set("event")} /></label>
          <label>Name on proposal cover<input value={form.coverName} placeholder="defaults to event" onChange={set("coverName")} /></label>
          <label>Website<input value={form.website} onChange={set("website")} /></label>
          <label>About them<textarea rows={4} value={form.about} onChange={set("about")} /></label>
          <div className="row">
            <button className="btn pri" onClick={() => run(async () => { await (id ? api(`/contacts/${id}`, "PUT", form) : api("/contacts", "POST", form)); if (!id) onClose(); }, "Saved")}>Save</button>
            {id && <button className="btn danger" onClick={() => confirm("Delete this contact?") && run(async () => { await api(`/contacts/${id}`, "DELETE"); onClose(); }, "Deleted")}>Delete</button>}
          </div>
        </div>
      )}

      {tab === "email" && id && (
        <div className="form">
          {!hasDraft ? (
            <button className="btn pri" onClick={() => act("generate", "Writing the email, about 20 seconds")}>Generate email</button>
          ) : (
            <>
              <label>Subject<input value={subject} disabled={!editable} onChange={(e) => setSubject(e.target.value)} /></label>
              <label>Body<textarea rows={11} value={body} disabled={!editable} onChange={(e) => setBody(e.target.value)} /></label>
              <pre className="sig muted">{meta?.signature}</pre>
              <div className="row">
                {editable && <button className="btn" onClick={() => run(saveEmail, "Saved")}>Save text</button>}
                {contact?.status === "drafted" && <button className="btn pri" onClick={() => run(async () => { await saveEmail(); await api(`/contacts/${id}/approve`, "POST", {}); }, "Approved")}>Approve</button>}
                {contact?.status === "approved" && <button className="btn" onClick={() => act("unapprove", "Back to draft")}>Unapprove</button>}
                {editable && <button className="btn" onClick={() => confirm("Discard and rewrite?") && act("redraft")}>Rewrite</button>}
                {contact && ["drafted", "approved"].includes(contact.status) && (
                  <button className="btn pri" onClick={() => confirm(`Send now to ${contact.email}? This cannot be undone.`) && run(async () => { await saveEmail(); await api(`/contacts/${id}/send`, "POST", {}); }, "Queued, sending shortly")}>Send now</button>)}
                {meta?.hasTestEmail && <button className="btn" onClick={() => act("test", "Test email queued")}>Test to myself</button>}
                {contact && ["approved", "sent"].includes(contact.status) && !contact.stopped && <button className="btn danger" onClick={() => act("stop", "Stopped")}>Stop</button>}
                {contact?.stopped && <button className="btn" onClick={() => act("resume", "Resumed")}>Resume</button>}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "preview" && (
        <div className="form">
          {!hasDraft && <p className="muted">No draft yet.</p>}
          {preview.data && (
            <>
              <div className="mail"><div className="muted">From {preview.data.from}<br />To {preview.data.to}</div><b>{preview.data.subject}</b><pre>{preview.data.body}</pre>
                <a href={`/api/contacts/${id}/attachment`} target="_blank" rel="noreferrer">📎 {preview.data.attachment}</a></div>
              <h4>Follow up {preview.data.followupN} (in the same thread)</h4>
              <div className="mail"><b>{preview.data.followupSubject}</b><pre>{preview.data.followupBody}</pre></div>
            </>
          )}
        </div>
      )}
    </aside>
  );
}

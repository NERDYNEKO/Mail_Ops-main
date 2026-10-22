import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";

type Pool = Record<string, string[]>;

/** Editable follow up pool. One message per paragraph, blank line between them. Placeholders: {first} {event} {org} {name}. */
export function Templates({ onClose, say }: { onClose: () => void; say: (m: string) => void }) {
  const { data } = useQuery({ queryKey: ["templates"], queryFn: () => api<Pool>("/templates") });
  const [text, setText] = useState<Record<string, string>>({});
  useEffect(() => {
    if (data) setText(Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v.join("\n\n")])));
  }, [data]);

  const save = async () => {
    const pool = Object.fromEntries(Object.entries(text).map(([k, v]) => [k, v.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean)]));
    try { await api("/templates", "PUT", pool); say("Saved"); onClose(); } catch (e) { say((e as Error).message); }
  };

  return (
    <div className="modal" onClick={onClose}>
      <div className="card box" onClick={(e) => e.stopPropagation()}>
        <h2>Follow up messages</h2>
        <p className="muted">One message per paragraph. Use {"{first}"}, {"{event}"}, {"{org}"}. Each contact gets them in their own order.</p>
        {Object.keys(text).map((k) => (
          <label key={k}>{k}<textarea rows={10} value={text[k]} onChange={(e) => setText({ ...text, [k]: e.target.value })} /></label>
        ))}
        <div className="row"><button className="btn pri" onClick={save}>Save</button><button className="btn" onClick={onClose}>Cancel</button></div>
      </div>
    </div>
  );
}

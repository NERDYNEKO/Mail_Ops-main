export interface Contact {
  id: string; email: string; name: string; category: "client" | "network"; org: string; event: string;
  coverName: string; website: string; about: string; status: string; stopped: boolean;
  subject: string; body: string; sent: string[]; followups: number; nextDue: string | null;
}
export interface Meta {
  cap: number; gapDays: number; window: [number, number]; hasMailPassword: boolean; hasTestEmail: boolean;
  hasLlmKey: boolean; autopilot: boolean; signature: string; sender: string;
}
export interface Preview {
  from: string; to: string; subject: string; body: string; attachment: string; cover: string;
  followupN: number; followupSubject: string; followupBody: string;
}
export interface Log { _id: string; message: string; level: "info" | "error"; createdAt: string }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = unknown>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method, credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new ApiError(res.status, data?.error ?? res.statusText);
  return data as T;
}

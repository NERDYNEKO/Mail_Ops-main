import { Router, type NextFunction, type Request, type RequestHandler, type Response } from "express";
import { parse } from "csv-parse/sync";
import { stringify } from "csv-stringify/sync";
import multer from "multer";
import rateLimit from "express-rate-limit";
import { z } from "zod";
import { login, logout, requireAuth } from "./auth.js";
import { env } from "./config.js";
import { Activity } from "./models/Activity.js";
import { Contact, type ContactDoc } from "./models/Contact.js";
import { getSetting, setSetting } from "./models/misc.js";
import { enqueueDraft, enqueueSends, enqueueTest, enqueueTick } from "./queue.js";
import { followupText, loadPool, savePool } from "./services/followups.js";
import { attachmentFor, coverName, followupDueAt, replySubject, withSignature } from "./services/pipeline.js";
import { clean } from "./services/text.js";
import { SIGNATURE } from "./services/writer.js";

const wrap = (fn: (req: Request, res: Response) => Promise<unknown>): RequestHandler => (req, res, next) =>
  void fn(req, res).catch(next);
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 2_000_000 } });

const ContactInput = z.object({
  email: z.string().email(),
  name: z.string().default(""),
  category: z.enum(["client", "network"]).default("client"),
  org: z.string().default(""),
  event: z.string().default(""),
  coverName: z.string().default(""),
  website: z.string().default(""),
  about: z.string().default(""),
});
const Ids = z.object({ ids: z.array(z.string()).min(1) });

const view = (c: ContactDoc) => ({
  id: String(c._id), email: c.email, name: c.name, category: c.category, org: c.org, event: c.event,
  coverName: c.coverName, website: c.website, about: c.about,
  status: c.stopped && ["approved", "sent"].includes(c.status) ? "stopped" : c.status,
  stopped: c.stopped, subject: c.subject, body: c.body, sent: c.sent, followups: c.followups,
  nextDue: c.status === "sent" && !c.stopped && c.followups < env.FOLLOWUP_MAX && c.sent.length ? followupDueAt(c) : null,
});

export function buildRouter() {
  const r = Router();
  const loginLimiter = rateLimit({ windowMs: 15 * 60_000, limit: 10, standardHeaders: true, legacyHeaders: false });

  r.get("/healthz", (_req, res) => void res.json({ ok: true }));

  // ---- auth ----
  r.post("/auth/login", loginLimiter, wrap(async (req, res) => {
    const { email, password } = z.object({ email: z.string(), password: z.string() }).parse(req.body);
    if (!(await login(email, password, res))) return void res.status(401).json({ error: "Wrong email or password" });
    res.json({ ok: true });
  }));
  r.post("/auth/logout", (_req, res) => { logout(res); res.json({ ok: true }); });

  r.use(requireAuth);
  r.get("/auth/me", (_req, res) => void res.json({ ok: true }));

  // ---- meta / settings ----
  r.get("/meta", wrap(async (_req, res) => {
    res.json({
      cap: env.DAILY_CAP, gapDays: env.FOLLOWUP_GAP_DAYS, window: [env.SEND_START_HOUR, env.SEND_END_HOUR],
      hasMailPassword: !!env.GMAIL_APP_PASSWORD, hasTestEmail: !!env.TEST_EMAIL, hasLlmKey: !!env.ANTHROPIC_API_KEY,
      autopilot: await getSetting("autopilot", false), signature: SIGNATURE, sender: env.GMAIL_USER,
    });
  }));
  r.put("/settings/autopilot", wrap(async (req, res) => {
    await setSetting("autopilot", z.object({ on: z.boolean() }).parse(req.body).on);
    res.json({ ok: true });
  }));
  r.get("/activity", wrap(async (_req, res) => {
    res.json((await Activity.find().sort({ createdAt: -1 }).limit(100).lean()).reverse());
  }));
  r.get("/templates", wrap(async (_req, res) => void res.json(await loadPool())));
  r.put("/templates", wrap(async (req, res) => {
    await savePool(z.record(z.string(), z.array(z.string())).parse(req.body));
    res.json({ ok: true });
  }));

  // ---- contacts ----
  r.get("/contacts", wrap(async (_req, res) => {
    res.json((await Contact.find().sort({ createdAt: 1 }).lean<ContactDoc[]>()).map(view));
  }));
  r.post("/contacts", wrap(async (req, res) => {
    const d = ContactInput.parse(req.body);
    if (await Contact.exists({ email: d.email.toLowerCase() })) return void res.status(409).json({ error: "That email already exists" });
    res.status(201).json(view((await Contact.create(d)).toObject() as ContactDoc));
  }));
  r.put("/contacts/:id", wrap(async (req, res) => {
    const d = ContactInput.parse(req.body);
    const c = await Contact.findByIdAndUpdate(req.params.id, d, { new: true, runValidators: true }).lean<ContactDoc>();
    c ? res.json(view(c)) : res.status(404).json({ error: "Not found" });
  }));
  r.delete("/contacts/:id", wrap(async (req, res) => {
    // contacts that already got mail are kept so follow ups and history are not lost
    const c = await Contact.findOneAndDelete({ _id: req.params.id, status: { $in: ["new", "drafted", "approved"] } });
    c ? res.json({ ok: true }) : res.status(409).json({ error: "Already contacted, use Stop instead" });
  }));
  r.post("/contacts/import", upload.single("file"), wrap(async (req, res) => {
    if (!req.file) return void res.status(400).json({ error: "No file" });
    const rows = parse(req.file.buffer, { columns: (h: string[]) => h.map((x) => x.trim().toLowerCase()), bom: true, skip_empty_lines: true, trim: true }) as Record<string, string>[];
    let added = 0, skipped = 0;
    for (const row of rows) {
      const p = ContactInput.safeParse({ ...row, coverName: row.cover_name ?? row.covername ?? "", category: row.category || "client" });
      if (!p.success || (await Contact.exists({ email: p.data.email.toLowerCase() }))) { skipped++; continue; }
      await Contact.create(p.data);
      added++;
    }
    res.json({ added, skipped });
  }));
  r.get("/contacts-export.csv", wrap(async (_req, res) => {
    const rows = await Contact.find().lean<ContactDoc[]>();
    res.type("text/csv").send(stringify(rows.map((c) => ({
      name: c.name, email: c.email, category: c.category, org: c.org, event: c.event, cover_name: c.coverName, website: c.website, about: c.about,
    })), { header: true }));
  }));

  // ---- email text ----
  r.put("/contacts/:id/email", wrap(async (req, res) => {
    const d = z.object({ subject: z.string(), body: z.string() }).parse(req.body);
    const c = await Contact.findOneAndUpdate({ _id: req.params.id, status: { $in: ["new", "drafted", "approved"] } }, { subject: clean(d.subject), body: clean(d.body) }, { new: true });
    c ? res.json({ ok: true }) : res.status(409).json({ error: "Already sent, cannot edit" });
  }));
  r.get("/contacts/:id/preview", wrap(async (req, res) => {
    const c = await Contact.findById(req.params.id);
    if (!c || c.status === "new") return void res.status(404).json({ error: "No draft yet. Generate the email first." });
    res.json({
      from: `${env.FROM_NAME} <${env.GMAIL_USER}>`, to: `${c.name} <${c.email}>`, subject: c.subject, body: withSignature(c.body),
      attachment: c.category === "network" ? "Mapster_Pitch_Deck.pdf" : "Mapster_Pilot_Proposal.pdf", cover: coverName(c),
      followupN: c.followups + 1, followupSubject: replySubject(c.subject), followupBody: withSignature(await followupText(c, c.followups + 1)),
    });
  }));
  r.get("/contacts/:id/attachment", wrap(async (req, res) => {
    const c = await Contact.findById(req.params.id);
    if (!c) return void res.status(404).end();
    res.type("application/pdf").sendFile((await attachmentFor(c)).path);
  }));

  // ---- actions on one contact ----
  const one = (action: string, fn: (c: ContactDoc, id: string) => Promise<unknown>) =>
    r.post(`/contacts/:id/${action}`, wrap(async (req, res) => {
      const c = await Contact.findById(req.params.id).lean<ContactDoc>();
      if (!c) return void res.status(404).json({ error: "Not found" });
      await fn(c, String(c._id));
      res.json({ ok: true });
    }));
  one("generate", (c, id) => (c.status === "new" ? enqueueDraft([id]) : Promise.resolve()));
  one("approve", (c) => Contact.updateOne({ _id: c._id, status: "drafted" }, { status: "approved" }));
  one("unapprove", (c) => Contact.updateOne({ _id: c._id, status: "approved" }, { status: "drafted" }));
  one("stop", (c) => Contact.updateOne({ _id: c._id }, { stopped: true }));
  one("resume", (c) => Contact.updateOne({ _id: c._id }, { stopped: false }));
  one("redraft", (c) => Contact.updateOne({ _id: c._id, status: { $in: ["drafted", "approved"] } }, { status: "new", subject: "", body: "" }));
  one("test", (_c, id) => enqueueTest(id));
  one("send", async (c, id) => {
    if (c.status === "drafted") await Contact.updateOne({ _id: c._id }, { status: "approved" });
    await enqueueSends([id], false);
  });

  // ---- bulk / run ----
  r.post("/bulk", wrap(async (req, res) => {
    const { ids } = Ids.parse(req.body);
    const action = z.enum(["generate", "approve", "unapprove", "stop", "resume", "send"]).parse(req.body.action);
    const in_ = { _id: { $in: ids } };
    if (action === "generate") await enqueueDraft((await Contact.find({ ...in_, status: "new" }).distinct("_id")).map(String));
    if (action === "approve" || action === "send") await Contact.updateMany({ ...in_, status: "drafted" }, { status: "approved" });
    if (action === "unapprove") await Contact.updateMany({ ...in_, status: "approved" }, { status: "drafted" });
    if (action === "stop" || action === "resume") await Contact.updateMany({ ...in_, status: { $in: ["approved", "sent"] } }, { stopped: action === "stop" });
    if (action === "send") {
      const ready = (await Contact.find({ ...in_, status: "approved", stopped: false }).distinct("_id")).map(String);
      if (!ready.length) return void res.json({ ok: false, msg: "none" });
      await enqueueSends(ready);
    }
    res.json({ ok: true });
  }));
  r.post("/run", wrap(async (req, res) => {
    const dry = z.object({ dry: z.boolean().default(false) }).parse(req.body).dry;
    if (dry) await (await import("./services/pipeline.js")).tick({ dry: true });
    else await enqueueTick(true);
    res.json({ ok: true });
  }));

  r.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof z.ZodError) return void res.status(400).json({ error: err.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ") });
    res.status(500).json({ error: err.message });
  });
  return r;
}

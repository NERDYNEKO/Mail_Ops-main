import { env } from "../config.js";
import { activity } from "../logger.js";
import { Contact, type ContactDoc } from "../models/Contact.js";
import { followupText } from "./followups.js";
import { checkReplies, sendMail } from "./mailer.js";
import { deckPath, makeProposal } from "./pdf.js";
import { SIGNATURE, writeFirst } from "./writer.js";

const DAY = 864e5;
type C = Pick<ContactDoc, "category" | "coverName" | "event" | "org" | "name">;

export const coverName = (c: C) => c.coverName || c.event || c.org || c.name || "";
export const withSignature = (body: string) => `${body}\n\n${SIGNATURE}`;
export const replySubject = (s: string) => (s.toLowerCase().startsWith("re:") ? s : `Re: ${s}`);

export async function attachmentFor(c: C) {
  return c.category === "network"
    ? { path: deckPath, filename: "Mapster_Pitch_Deck.pdf" }
    : { path: await makeProposal(coverName(c)), filename: "Mapster_Pilot_Proposal.pdf" };
}

export const followupDueAt = (c: Pick<ContactDoc, "sent">) =>
  new Date(c.sent[c.sent.length - 1].getTime() + env.FOLLOWUP_GAP_DAYS * DAY);

export const isFollowupDue = (c: Pick<ContactDoc, "status" | "stopped" | "followups" | "sent">) =>
  c.status === "sent" && !c.stopped && c.followups < env.FOLLOWUP_MAX && c.sent.length > 0 && followupDueAt(c) <= new Date();

export function inSendWindow(now = new Date()) {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: env.TZ_NAME }).format(now)) % 24;
  return hour >= env.SEND_START_HOUR && hour < env.SEND_END_HOUR;
}

export async function sentToday(): Promise<number> {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  const [r] = await Contact.aggregate([{ $unwind: "$sent" }, { $match: { sent: { $gte: start } } }, { $count: "n" }]);
  return r?.n ?? 0;
}

export async function draftContact(id: string) {
  const c = await Contact.findById(id);
  if (!c || c.status !== "new") return;
  await activity(`Writing email for ${c.email} ...`);
  try {
    const mail = await writeFirst(c);
    await Contact.updateOne({ _id: id, status: "new" }, { ...mail, status: "drafted" });
    await activity(`Drafted ${c.email}`);
  } catch (err) {
    await activity(`FAILED for ${c.email}: ${(err as Error).message}`, "error");
    throw err;
  }
}

/** Send the first email (approved) or the next follow up (sent and due). Claims the contact so it can never double send. */
export async function sendOne(id: string, opts: { testTo?: string } = {}) {
  const c = await Contact.findOneAndUpdate(
    { _id: id, sending: false, stopped: false, status: { $in: ["approved", "sent"] } },
    { sending: true },
    { new: true },
  );
  if (!c) return;
  try {
    const first = c.status === "approved";
    if (!first && !isFollowupDue(c)) return void (await Contact.updateOne({ _id: id }, { sending: false }));
    if ((await sentToday()) >= env.DAILY_CAP) {
      await activity(`Daily cap of ${env.DAILY_CAP} reached, ${c.email} waits until tomorrow`);
      return void (await Contact.updateOne({ _id: id }, { sending: false }));
    }
    const n = c.followups + 1;
    const messageId = first
      ? await sendMail({ to: c.email, subject: c.subject, text: withSignature(c.body), attachment: await attachmentFor(c) })
      : await sendMail({
          to: c.email,
          subject: replySubject(c.subject),
          text: withSignature(await followupText(c, n)),
          replyTo: { inReplyTo: c.messageIds[0], references: c.messageIds.slice(0, 1) },
        });
    await Contact.updateOne(
      { _id: id },
      { $set: { sending: false, ...(first ? { status: "sent" } : { followups: n }) }, $push: { sent: new Date(), messageIds: messageId } },
    );
    await activity(`Sent ${first ? "first email" : `follow up ${n}`} to ${c.email}`);
  } catch (err) {
    await Contact.updateOne({ _id: id }, { sending: false });
    await activity(`Send to ${c.email} failed: ${(err as Error).message}`, "error");
    throw err;
  }
}

export async function sendTest(id: string) {
  const c = await Contact.findById(id);
  if (!c) throw new Error("Contact not found");
  if (!env.TEST_EMAIL) throw new Error("Set TEST_EMAIL in the environment first");
  await sendMail({ to: env.TEST_EMAIL, subject: `[TEST] ${c.subject}`, text: withSignature(c.body), attachment: await attachmentFor(c) });
  await activity(`Test email sent to ${env.TEST_EMAIL}`);
}

/** Everything that should go out now: approved first emails and follow ups that are due. */
export async function collectDue(): Promise<string[]> {
  const candidates = await Contact.find({ stopped: false, sending: false, status: { $in: ["approved", "sent"] } }).sort({ createdAt: 1 });
  const due = candidates.filter((c) => c.status === "approved" || isFollowupDue(c));
  const budget = Math.max(0, env.DAILY_CAP - (await sentToday()));
  return due.slice(0, budget).map((c) => c.id as string);
}

export async function tick(opts: { force?: boolean; dry?: boolean } = {}): Promise<string[]> {
  if (!opts.force && !opts.dry && !inSendWindow()) {
    await activity(`Outside sending hours (${env.SEND_START_HOUR}:00 to ${env.SEND_END_HOUR}:00). Nothing sent.`);
    return [];
  }
  await checkReplies();
  const ids = await collectDue();
  if (opts.dry) {
    const docs = await Contact.find({ _id: { $in: ids } });
    for (const c of docs) await activity(`[dry] ${c.status === "approved" ? "first email" : `follow up ${c.followups + 1}`} for ${c.email}`);
    if (!docs.length) await activity("[dry] nothing due");
    return [];
  }
  if (!ids.length) await activity("Nothing to send.");
  return ids;
}

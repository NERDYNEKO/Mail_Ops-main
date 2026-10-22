import { randomUUID } from "node:crypto";
import { ImapFlow } from "imapflow";
import nodemailer from "nodemailer";
import { env } from "../config.js";
import { activity } from "../logger.js";
import { Contact } from "../models/Contact.js";

const transport = nodemailer.createTransport({
  host: "smtp.gmail.com",
  port: 465,
  secure: true,
  pool: true,
  auth: { user: env.GMAIL_USER, pass: env.GMAIL_APP_PASSWORD },
});

export interface Outgoing {
  to: string;
  subject: string;
  text: string;
  attachment?: { path: string; filename: string };
  replyTo?: { inReplyTo: string; references: string[] };
}

export async function sendMail(m: Outgoing): Promise<string> {
  if (!env.GMAIL_APP_PASSWORD) throw new Error("GMAIL_APP_PASSWORD is not set");
  const messageId = `<${randomUUID()}@gmail.com>`;
  await transport.sendMail({
    from: `${env.FROM_NAME} <${env.GMAIL_USER}>`,
    to: m.to,
    subject: m.subject,
    text: m.text,
    messageId,
    inReplyTo: m.replyTo?.inReplyTo,
    references: m.replyTo?.references,
    attachments: m.attachment ? [m.attachment] : [],
  });
  return messageId;
}

/** Mark contacts who replied or bounced so follow ups stop. */
export async function checkReplies() {
  if (!env.GMAIL_APP_PASSWORD) return;
  const waiting = await Contact.find({ status: "sent" }).lean();
  if (!waiting.length) return;
  const imap = new ImapFlow({
    host: "imap.gmail.com", port: 993, secure: true,
    auth: { user: env.GMAIL_USER, pass: env.GMAIL_APP_PASSWORD }, logger: false,
  });
  try {
    await imap.connect();
    const lock = await imap.getMailboxLock("INBOX");
    try {
      const since = new Date(Date.now() - 60 * 864e5);
      const open = new Map(waiting.map((c) => [c.email, c]));
      for await (const msg of imap.fetch({ since }, { envelope: true, source: { start: 0, maxLength: 3000 } })) {
        const from = msg.envelope?.from?.[0]?.address?.toLowerCase() ?? "";
        const subject = (msg.envelope?.subject ?? "").toLowerCase();
        const raw = msg.source?.toString("utf8").toLowerCase() ?? "";
        const date = msg.envelope?.date ?? new Date();
        for (const [email, c] of open) {
          if (date < (c.sent[0] ?? 0) || !raw.includes(email)) continue;
          const bounce = /mailer-daemon|postmaster/.test(from) || /undeliverable|delivery status|delivery failure/.test(subject);
          const status = bounce ? "bounced" : from === email ? "replied" : null;
          if (!status) continue;
          await Contact.updateOne({ email }, { status });
          open.delete(email);
          await activity(`${email}: ${status}`);
        }
      }
    } finally {
      lock.release();
    }
    await imap.logout();
  } catch (err) {
    await activity(`Reply check failed (continuing): ${(err as Error).message}`, "error");
  }
}

import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { env } from "../config.js";
import prompts from "../content/prompts.json" with { type: "json" };
import type { ContactDoc } from "../models/Contact.js";
import { clean, firstName } from "./text.js";

export const SIGNATURE = prompts.signature;
const client = env.ANTHROPIC_API_KEY ? new Anthropic({ apiKey: env.ANTHROPIC_API_KEY }) : null;
const Mail = z.object({ subject: z.string(), body: z.string() });
const siteCache = new Map<string, string>();

async function fetchSite(url: string, limit = 3000): Promise<string> {
  if (!url) return "";
  if (siteCache.has(url)) return siteCache.get(url)!;
  try {
    const res = await fetch(url.startsWith("http") ? url : `https://${url}`, {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(15_000),
    });
    const text = (await res.text())
      .replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, limit);
    siteCache.set(url, text);
    return text;
  } catch {
    return "";
  }
}

async function ask(system: string, user: string) {
  if (!client) throw new Error("ANTHROPIC_API_KEY is not set");
  const msg = await client.messages.create({
    model: env.WRITER_MODEL,
    max_tokens: 1000,
    system,
    messages: [{ role: "user", content: user }],
  });
  const raw = msg.content.map((b) => (b.type === "text" ? b.text : "")).join("");
  const parsed = Mail.parse(JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1)));
  let body = clean(parsed.body);
  const [head, ...rest] = body.split("\n");
  if (rest.length && head.startsWith("Hi ") && head.endsWith(",") && rest[0] !== "") {
    body = `${head}\n\n${rest.join("\n")}`; // blank line after the greeting
  }
  return { subject: clean(parsed.subject), body };
}

export async function writeFirst(c: Pick<ContactDoc, "name" | "org" | "event" | "about" | "website" | "category">) {
  const fn = firstName(c.name);
  const network = c.category === "network";
  const system = network
    ? `You write short personal emails for Rudraksh, founder of Mapster, to people who could help with advice, network or investment.\n${prompts.networkFacts}\n\n${prompts.style}`
    : `You write short personal outreach emails for Rudraksh, founder of Mapster, to exhibition organizers.\n${prompts.clientFacts}\n\n${prompts.style}`;
  const task = network
    ? `Write a first email of about 70 words (60 to 78, never more) in 3 short paragraphs:
1. "Hi ${fn}," then one or two sentences showing you know who they are and why you picked them (use only the details given).
2. Two sentences on what Mapster is and why it matters, plus that it is built and now looking for its first pilot.
3. Ask for a short call to get their thoughts, introductions or interest, and say the pitch deck is attached.`
    : `Write a first email of about 70 words (60 to 78, never more) in 3 short paragraphs:
1. "Hi ${fn}," then one or two sentences showing you understand what their event is and who it serves (use only the details given).
2. Two sentences on how Mapster helps THEM specifically, picking the 2 or 3 features that fit their event.
3. The free pilot offer (no cost, no long term commitment), say the proposal is attached, and ask for a quick demo call.`;
  const subj = network
    ? "Subject: plain, human, mentions Mapster and what you want (a quick conversation). Under 70 characters."
    : "Subject: specific to their event, plain and human, mentions the free pilot. Under 70 characters.";

  let user = `Recipient name: ${c.name}\nOrganization: ${c.org}\nEvent: ${c.event}
What they do / details (from our notes): ${c.about}
Website text (may be empty or noisy):\n${await fetchSite(c.website)}

${task}
Do NOT include a sign off or signature, it is added automatically. Count the words of the body. Going over 78 words is a failure. Keep sentences short.
${subj}
Reply ONLY with JSON: {"subject": "...", "body": "..."}`;

  let best: { subject: string; body: string } | null = null;
  for (let i = 0; i < 4; i++) {
    const mail = await ask(system, user);
    const n = mail.body.split(/\s+/).length;
    if (!best || n < best.body.split(/\s+/).length) best = mail;
    if (n <= 79) break;
    user += `\n\nYour last attempt was ${n} words. Rewrite it clearly under 78 words.`;
  }
  return best!;
}

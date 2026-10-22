import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";
import { env } from "../config.js";

export const assetsDir = path.resolve(env.ASSETS_DIR);
const outDir = path.resolve("out");
const template = path.join(assetsDir, "proposal.html");

const CANDIDATES = [
  env.CHROME_PATH,
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
];
const browserPath = () => CANDIDATES.find((p) => p && fs.existsSync(p));
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export const deckPath = path.join(assetsDir, "Mapster_PitchDeck.pdf");

/** Proposal PDF with the recipient's name on the cover. Cached by name + template version. */
export async function makeProposal(name: string): Promise<string> {
  const exe = browserPath();
  if (!exe) throw new Error("No Chrome/Edge found. Set CHROME_PATH.");
  const stamp = fs.statSync(template).mtimeMs;
  const key = createHash("sha1").update(`${name}|${stamp}`).digest("hex").slice(0, 12);
  const out = path.join(outDir, `proposal_${key}.pdf`);
  if (fs.existsSync(out)) return out;
  fs.mkdirSync(outDir, { recursive: true });

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mapster_pdf_"));
  try {
    for (const f of fs.readdirSync(assetsDir)) if (f.endsWith(".png")) fs.copyFileSync(path.join(assetsDir, f), path.join(tmp, f));
    const page = path.join(tmp, "p.html");
    fs.writeFileSync(page, fs.readFileSync(template, "utf8").replaceAll("{{NAME}}", esc(name)));
    const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ["--no-sandbox", "--disable-gpu"] });
    try {
      const p = await browser.newPage();
      await p.goto(pathToFileURL(page).href, { waitUntil: "networkidle0" });
      await p.pdf({ path: out, printBackground: true, preferCSSPageSize: true });
    } finally {
      await browser.close();
    }
    return out;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

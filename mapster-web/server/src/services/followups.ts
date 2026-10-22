import defaults from "../content/followups.json" with { type: "json" };
import { getSetting, setSetting } from "../models/misc.js";
import { clean, firstName } from "./text.js";

export type Pool = Record<string, string[]>;
export const loadPool = () => getSetting<Pool>("followupPool", defaults.pool);
export const savePool = (p: Pool) =>
  setSetting("followupPool", Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v.map((x) => x.trim()).filter(Boolean)])));

function crc32(s: string) {
  let c, crc = ~0;
  for (const b of Buffer.from(s)) {
    c = (crc ^ b) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xedb88320 : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return ~crc >>> 0;
}

/** Small seeded PRNG so each contact always gets the same, personal order. */
function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle<T>(arr: T[], rand: () => number) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

type C = { email: string; name?: string; category?: string; event?: string; org?: string };

/** Follow up number n (1 based). Order and greeting differ per person, closing messages come last. */
export async function followupText(c: C, n: number): Promise<string> {
  const all = await loadPool();
  const pool = all[c.category || "client"]?.length ? all[c.category || "client"] : defaults.pool.client;
  const seed = crc32((c.email || c.name || "x").toLowerCase());
  const isCloser = (t: string) => defaults.closerMarkers.some((k) => t.includes(k));
  const rand = rng(seed);
  const order = [...shuffle(pool.filter((t) => !isCloser(t)), rand), ...shuffle(pool.filter(isCloser), rand)];
  let t = order[(n - 1) % order.length];
  if (t.startsWith("Hi {first},")) {
    const greetings = defaults.greetings;
    t = greetings[Math.floor(rng(seed * 31 + n)() * greetings.length)] + t.slice("Hi {first},".length);
  }
  const vars: Record<string, string> = {
    first: firstName(c.name), name: c.name ?? "", event: c.event || c.org || "your event", org: c.org || "your organization",
  };
  return clean(t.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? ""));
}

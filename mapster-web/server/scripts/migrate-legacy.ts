/** One time import of the old Python data (legacy/state.json) into MongoDB. Run: npm run migrate:legacy */
import fs from "node:fs";
import path from "node:path";
import mongoose from "mongoose";
import { env } from "../src/config.js";
import { Contact } from "../src/models/Contact.js";
import { SIGNATURE } from "../src/services/writer.js";

const file = path.resolve("../../legacy/state.json");
const state = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, any>;
await mongoose.connect(env.MONGO_URL);
let n = 0;
for (const [email, s] of Object.entries(state)) {
  const c = s.contact ?? {};
  await Contact.updateOne(
    { email: email.toLowerCase() },
    { $setOnInsert: {
        email: email.toLowerCase(), name: c.name ?? "", category: c.category || "client", org: c.org ?? "", event: c.event ?? "",
        coverName: c.cover_name ?? "", website: c.website ?? "", about: c.about ?? "",
        status: s.status, subject: s.subject, body: String(s.body).replace(`\n\n${SIGNATURE}`, "").trim(),
        sent: (s.sent ?? []).map((t: string) => new Date(t.replace(" ", "T"))), messageIds: s.message_ids ?? [],
        followups: s.followups ?? 0, stopped: !!s.stopped,
    } },
    { upsert: true },
  );
  n++;
}
console.log(`Imported ${n} contact(s)`);
await mongoose.disconnect();

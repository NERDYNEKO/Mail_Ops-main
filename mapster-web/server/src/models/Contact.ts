import { Schema, model, type Types } from "mongoose";

export const STATUSES = ["new", "drafted", "approved", "sent", "replied", "bounced"] as const;
export type Status = (typeof STATUSES)[number];

/** One document per recipient: contact details plus the whole outreach state. */
export interface ContactShape {
  email: string; name: string; category: "client" | "network"; org: string; event: string;
  coverName: string; website: string; about: string;
  status: Status; subject: string; body: string; sent: Date[]; messageIds: string[];
  followups: number; stopped: boolean; sending: boolean;
}

const schema = new Schema<ContactShape>(
  {
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    name: { type: String, default: "", trim: true },
    category: { type: String, enum: ["client", "network"], default: "client" },
    org: { type: String, default: "", trim: true },
    event: { type: String, default: "", trim: true },
    coverName: { type: String, default: "", trim: true },
    website: { type: String, default: "", trim: true },
    about: { type: String, default: "", trim: true },

    status: { type: String, enum: STATUSES, default: "new", index: true },
    subject: { type: String, default: "" },
    body: { type: String, default: "" }, // without signature, it is appended on send
    sent: { type: [Date], default: [] },
    messageIds: { type: [String], default: [] },
    followups: { type: Number, default: 0 },
    stopped: { type: Boolean, default: false },
    sending: { type: Boolean, default: false }, // claim flag so a message is never sent twice
  },
  { timestamps: true },
);

export type ContactDoc = ContactShape & { _id: Types.ObjectId };
export const Contact = model<ContactShape>("Contact", schema);

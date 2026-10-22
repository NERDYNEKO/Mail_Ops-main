import { Schema, model } from "mongoose";

const schema = new Schema(
  {
    message: { type: String, required: true },
    level: { type: String, enum: ["info", "error"], default: "info" },
    createdAt: { type: Date, default: Date.now, expires: 60 * 60 * 24 * 7 },
  },
  { versionKey: false },
);

export const Activity = model("Activity", schema);

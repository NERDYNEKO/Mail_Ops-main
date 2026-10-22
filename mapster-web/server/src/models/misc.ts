import { Schema, model } from "mongoose";

export const User = model(
  "User",
  new Schema({ email: { type: String, unique: true, lowercase: true }, passwordHash: String }, { timestamps: true }),
);

/** Single document holding runtime settings and the editable follow up pool. */
export const Setting = model(
  "Setting",
  new Schema({ key: { type: String, unique: true }, value: Schema.Types.Mixed }, { versionKey: false }),
);

export async function getSetting<T>(key: string, fallback: T): Promise<T> {
  const d = await Setting.findOne({ key }).lean();
  return (d?.value as T) ?? fallback;
}
export const setSetting = (key: string, value: unknown) =>
  Setting.updateOne({ key }, { $set: { value } }, { upsert: true });

import pino from "pino";
import { isProd } from "./config.js";
import { Activity } from "./models/Activity.js";

export const logger = pino({
  level: process.env.LOG_LEVEL ?? "info",
  transport: isProd ? undefined : { target: "pino-pretty", options: { colorize: true } },
});

/** Human readable line shown in the panel's activity log (kept 7 days). */
export async function activity(message: string, level: "info" | "error" = "info") {
  logger[level](message);
  try {
    await Activity.create({ message, level });
  } catch {
    /* logging must never break a job */
  }
}

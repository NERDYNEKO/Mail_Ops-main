import "dotenv/config";
import { z } from "zod";

const Env = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.coerce.number().default(8080),
  MONGO_URL: z.string().default("mongodb://127.0.0.1:27017/mapster"),
  REDIS_URL: z.string().default("redis://127.0.0.1:6379"),
  JWT_SECRET: z.string().min(16, "JWT_SECRET must be at least 16 characters"),
  ADMIN_EMAIL: z.string().email(),
  ADMIN_PASSWORD: z.string().min(8),
  CORS_ORIGIN: z.string().default("http://localhost:5173"),

  GMAIL_USER: z.string().default("mapster.officials@gmail.com"),
  GMAIL_APP_PASSWORD: z.string().default(""),
  TEST_EMAIL: z.string().default(""),

  ANTHROPIC_API_KEY: z.string().default(""),
  WRITER_MODEL: z.string().default("claude-sonnet-5-5"),

  DAILY_CAP: z.coerce.number().default(25),
  DELAY_MIN_SEC: z.coerce.number().default(90),
  DELAY_MAX_SEC: z.coerce.number().default(240),
  FOLLOWUP_GAP_DAYS: z.coerce.number().default(2),
  FOLLOWUP_MAX: z.coerce.number().default(10),
  SEND_START_HOUR: z.coerce.number().default(9),
  SEND_END_HOUR: z.coerce.number().default(19),
  TZ_NAME: z.string().default("Asia/Kolkata"),
  AUTOPILOT_EVERY_MIN: z.coerce.number().default(30),

  CHROME_PATH: z.string().default(""),
  ASSETS_DIR: z.string().default("../assets"),
  FROM_NAME: z.string().default("MAPSTER"),
});

const parsed = Env.safeParse(process.env);
if (!parsed.success) {
  console.error("Invalid environment:\n" + parsed.error.issues.map((i) => `  ${i.path.join(".")}: ${i.message}`).join("\n"));
  process.exit(1);
}
export const env = parsed.data;
export const isProd = env.NODE_ENV === "production";

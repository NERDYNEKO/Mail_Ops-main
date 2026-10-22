import path from "node:path";
import fs from "node:fs";
import cookieParser from "cookie-parser";
import cors from "cors";
import express from "express";
import helmet from "helmet";
import mongoose from "mongoose";
import { pinoHttp } from "pino-http";
import { seedAdmin } from "./auth.js";
import { env, isProd } from "./config.js";
import { logger } from "./logger.js";
import { shutdownQueue, startWorker } from "./queue.js";
import { buildRouter } from "./routes.js";

await mongoose.connect(env.MONGO_URL);
await seedAdmin();
const worker = startWorker();

const app = express();
app.set("trust proxy", 1);
app.use(helmet({ contentSecurityPolicy: { directives: { "default-src": ["'self'"], "style-src": ["'self'", "'unsafe-inline'"], "frame-src": ["'self'"], "object-src": ["'self'"] } } }));
app.use(cors({ origin: env.CORS_ORIGIN, credentials: true }));
app.use(express.json({ limit: "200kb" }));
app.use(cookieParser());
app.use(pinoHttp({ logger, autoLogging: { ignore: (req) => req.url === "/api/healthz" } }));
app.use("/api", buildRouter());

// In production the built React app is served by this same server.
const client = path.resolve(process.env.CLIENT_DIR ?? "../client/dist");
if (isProd && fs.existsSync(client)) {
  app.use(express.static(client));
  app.get(/^(?!\/api).*/, (_req, res) => void res.sendFile(path.join(client, "index.html")));
}

const server = app.listen(env.PORT, () => logger.info(`Mapster listening on :${env.PORT}`));

async function stop() {
  server.close();
  await worker.close();
  await shutdownQueue();
  await mongoose.disconnect();
  process.exit(0);
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);

import { Queue, Worker } from "bullmq";
import { Redis } from "ioredis";
import { env } from "./config.js";
import { logger } from "./logger.js";
import { getSetting } from "./models/misc.js";
import { draftContact, sendOne, sendTest, tick } from "./services/pipeline.js";

const connection = new Redis(env.REDIS_URL, { maxRetriesPerRequest: null });
export const queue = new Queue("outreach", {
  connection,
  defaultJobOptions: { attempts: 3, backoff: { type: "exponential", delay: 60_000 }, removeOnComplete: 500, removeOnFail: 1000 },
});

const rand = (a: number, b: number) => a + Math.floor(Math.random() * (b - a + 1));

export const enqueueDraft = (ids: string[]) =>
  Promise.all(ids.map((id) => queue.add("draft", { id }, { jobId: `draft-${id}-${Date.now()}`, attempts: 2 })));

export const enqueueTest = (id: string) => queue.add("test", { id }, { attempts: 1 });

/** Sends are spread out with a random 90 to 240 s gap so the account looks human and stays under Gmail limits. */
export async function enqueueSends(ids: string[], spread = true) {
  let delay = 0;
  for (const id of ids) {
    await queue.add("send", { id }, { delay, jobId: `send-${id}-${Date.now()}` });
    if (spread) delay += rand(env.DELAY_MIN_SEC, env.DELAY_MAX_SEC) * 1000;
  }
}

export async function enqueueTick(force: boolean) {
  await queue.add("tick", { force }, { attempts: 1 });
}

export function startWorker() {
  const worker = new Worker(
    "outreach",
    async (job) => {
      switch (job.name) {
        case "draft": return draftContact(job.data.id);
        case "send": return sendOne(job.data.id);
        case "test": return sendTest(job.data.id);
        case "tick": {
          const auto = job.data.auto as boolean | undefined;
          if (auto && !(await getSetting("autopilot", false))) return;
          return enqueueSends(await tick({ force: !!job.data.force }));
        }
      }
    },
    { connection, concurrency: 1 },
  );
  worker.on("failed", (job, err) => logger.error({ job: job?.name, err: err.message }, "job failed"));
  // Autopilot heartbeat. A repeatable scheduler survives restarts and never duplicates.
  void queue.upsertJobScheduler("autopilot", { every: env.AUTOPILOT_EVERY_MIN * 60_000 }, { name: "tick", data: { auto: true } });
  return worker;
}

export async function shutdownQueue() {
  await queue.close();
  await connection.quit();
}

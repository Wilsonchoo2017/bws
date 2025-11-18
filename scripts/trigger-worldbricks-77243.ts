/**
 * Simple script to trigger a WorldBricks scrape for set 77243
 * The worker running in the main app will process this job
 */

import { getQueueService } from "../services/queue/QueueService.ts";

async function triggerScrape() {
  console.log("Triggering WorldBricks scrape for set 77243...\n");

  const queueService = getQueueService();
  await queueService.initialize();

  try {
    const job = await queueService.addWorldBricksJob({
      setNumber: "77243",
      saveToDb: false,
    });

    console.log(`✅ Job added: ${job.id}`);
    console.log("   The worker will process this job shortly.");
    console.log("   Check the main application logs to see the SetNotFoundError handling.");
  } finally {
    await queueService.close();
  }
}

triggerScrape();

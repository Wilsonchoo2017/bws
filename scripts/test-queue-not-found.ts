/**
 * Test script to verify queue handles SetNotFoundError correctly
 * Tests that set 77243 triggers proper permanent failure handling
 */

import { getQueueService, JOB_TYPES } from "../services/queue/QueueService.ts";

async function testQueueSetNotFoundHandling() {
  console.log("Testing Queue SetNotFoundError handling for set 77243...\n");

  const queueService = getQueueService();
  await queueService.initialize();

  try {
    console.log("Adding WorldBricks scrape job for set 77243 to the queue...");

    const job = await queueService.addWorldBricksJob({
      setNumber: "77243",
      saveToDb: false,
    });

    console.log(`✅ Job added: ${job.id}\n`);
    console.log("⏳ Waiting 15 seconds for worker to process the job...");

    // Wait for job to be processed
    await new Promise(resolve => setTimeout(resolve, 15000));

    const jobState = await job.getState();
    console.log("\n📊 Job State:", jobState);

    if (jobState === "completed") {
      console.log("\n✅ PASS: Job completed successfully (SetNotFoundError handled as expected)");
      console.log("   This means the error was caught and handled as a permanent failure,");
      console.log("   not as a retryable error that would keep failing.");

      const returnValue = await job.returnvalue;
      if (returnValue) {
        console.log("   Return Value:", JSON.stringify(returnValue, null, 2));
      }
    } else if (jobState === "failed") {
      console.log("\n❌ FAIL: Job failed (should have been handled as completed)");
      const failedReason = await job.failedReason;
      console.log("   Failed Reason:", failedReason);
    } else {
      console.log("\n⚠️  Job is still in state:", jobState);
    }

    console.log("\n🔍 Checking if 90-day retry was scheduled...");
    const jobs = await queueService["queue"]!.getJobs(["delayed"]);
    const futureRetry = jobs.find(j =>
      j.name === JOB_TYPES.SCRAPE_WORLDBRICKS &&
      j.data.setNumber === "77243" &&
      j.id !== job.id
    );

    if (futureRetry) {
      const delay = futureRetry.opts.delay || 0;
      const delayDays = Math.round(delay / (24 * 60 * 60 * 1000));
      console.log(`✅ Found delayed retry job scheduled in ~${delayDays} days`);
      console.log(`   Job ID: ${futureRetry.id}`);

      // Clean up the delayed job
      await futureRetry.remove();
      console.log("   (Cleaned up test job)");
    } else {
      console.log("⚠️  No delayed retry job found (this might be expected if already processed)");
    }

  } catch (error) {
    console.error("\n❌ Error during test:", error);
    throw error;
  } finally {
    await queueService.close();
    console.log("\n✅ Queue service closed");
  }
}

testQueueSetNotFoundHandling();

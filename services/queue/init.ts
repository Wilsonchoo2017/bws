/**
 * Queue initialization module
 * This module initializes the BullMQ worker when the application starts
 */

import { closeQueueService, getQueueService } from "./QueueService.ts";

// Re-export for convenience
export { closeQueueService, getQueueService } from "./QueueService.ts";

/**
 * Initialize the queue service
 * Should be called when the application starts
 */
export async function initializeQueue(): Promise<void> {
  try {
    console.log("🚀 Initializing BullMQ queue service...");

    // Close any existing instance first (important for hot reload)
    await closeQueueService();

    const queueService = getQueueService();
    await queueService.initialize();

    console.log("✅ Queue service initialized successfully");

    // Add graceful shutdown handler
    const shutdownHandler = async () => {
      console.log("🛑 Shutting down queue service...");
      await queueService.close();
      console.log("✅ Queue service shut down successfully");
      Deno.exit(0);
    };

    // Handle shutdown signals
    Deno.addSignalListener("SIGINT", shutdownHandler);
    Deno.addSignalListener("SIGTERM", shutdownHandler);
  } catch (error) {
    console.error("❌ Failed to initialize queue service:", error);
    // Don't throw - allow app to start even if Redis is not available
    // This allows development without Redis
    console.warn(
      "⚠️ Queue service not available. Scraping jobs will not be processed.",
    );
  }
}

/**
 * Check if queue is available and ready
 */
export function isQueueReady(): boolean {
  try {
    const queueService = getQueueService();
    return queueService.isReady();
  } catch {
    return false;
  }
}

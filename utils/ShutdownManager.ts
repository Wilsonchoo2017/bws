/**
 * Centralized graceful shutdown manager
 * Coordinates cleanup of all services on SIGTERM/SIGINT
 */

interface ShutdownService {
  name: string;
  close: () => Promise<void> | void;
}

class ShutdownManager {
  private services: ShutdownService[] = [];
  private timers: number[] = [];
  private isShuttingDown = false;
  private shutdownTimeout = 30000; // 30 seconds

  /**
   * Register a service to be closed during shutdown
   */
  registerService(name: string, close: () => Promise<void> | void) {
    this.services.push({ name, close });
  }

  /**
   * Register a timer/interval to be cleared during shutdown
   */
  registerTimer(timerId: number) {
    this.timers.push(timerId);
  }

  /**
   * Initialize signal handlers for graceful shutdown
   */
  initialize() {
    const handleShutdown = (signal: string) => {
      if (this.isShuttingDown) {
        console.log("Forced shutdown, exiting immediately");
        Deno.exit(1);
      }
      this.isShuttingDown = true;
      console.log(`\nReceived ${signal}, starting graceful shutdown...`);
      this.shutdown();
    };

    Deno.addSignalListener("SIGTERM", () => handleShutdown("SIGTERM"));
    Deno.addSignalListener("SIGINT", () => handleShutdown("SIGINT"));
  }

  /**
   * Perform graceful shutdown with timeout
   */
  private async shutdown() {
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(
        () => reject(new Error("Shutdown timeout exceeded")),
        this.shutdownTimeout,
      );
    });

    try {
      await Promise.race([this.performShutdown(), timeoutPromise]);
      console.log("Graceful shutdown completed successfully");
      Deno.exit(0);
    } catch (error) {
      console.error("Error during shutdown:", error);
      Deno.exit(1);
    }
  }

  /**
   * Execute shutdown sequence
   */
  private async performShutdown() {
    // Step 1: Clear all timers/intervals
    console.log("Clearing timers...");
    for (const timerId of this.timers) {
      clearInterval(timerId);
    }

    // Step 2: Close all registered services in reverse order
    // (last registered = first to close, like a stack)
    console.log("Closing services...");
    for (let i = this.services.length - 1; i >= 0; i--) {
      const service = this.services[i];
      try {
        console.log(`  Closing ${service.name}...`);
        await service.close();
        console.log(`  ✓ ${service.name} closed`);
      } catch (error) {
        console.error(`  ✗ Error closing ${service.name}:`, error);
      }
    }
  }
}

// Singleton instance
export const shutdownManager = new ShutdownManager();

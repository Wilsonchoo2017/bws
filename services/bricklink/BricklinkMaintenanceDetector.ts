import { MaintenanceError } from "../../types/errors/MaintenanceError.ts";
import { MAINTENANCE_CONFIG } from "../../config/scraper.config.ts";

/**
 * Detects and parses Bricklink maintenance pages.
 *
 * Bricklink maintenance page contains:
 * - Text: "System Unavailable"
 * - Message: "Daily maintenance is running. The site will be available in X minute(s)."
 */
export class BricklinkMaintenanceDetector {
  private static readonly MAINTENANCE_INDICATORS = [
    "System Unavailable",
    "Daily maintenance is running",
  ];

  private static readonly DURATION_REGEX =
    /will be available in (\d+)\s*(minute|minutes|hour|hours|second|seconds)/i;

  /**
   * Check if the HTML response is a maintenance page
   */
  static isMaintenancePage(html: string): boolean {
    return this.MAINTENANCE_INDICATORS.some((indicator) =>
      html.includes(indicator)
    );
  }

  /**
   * Parse the estimated maintenance duration from the HTML
   * Returns duration in milliseconds with safety buffer applied
   */
  static parseMaintenanceDuration(html: string): number {
    const match = html.match(this.DURATION_REGEX);

    if (!match) {
      console.warn(
        "Could not parse maintenance duration, using default delay",
      );
      return MAINTENANCE_CONFIG.DEFAULT_DELAY_MS;
    }

    const value = parseInt(match[1], 10);
    const unit = match[2].toLowerCase();

    let durationMs: number;

    switch (unit) {
      case "second":
      case "seconds":
        durationMs = value * 1000;
        break;
      case "minute":
      case "minutes":
        durationMs = value * 60 * 1000;
        break;
      case "hour":
      case "hours":
        durationMs = value * 60 * 60 * 1000;
        break;
      default:
        console.warn(`Unknown time unit: ${unit}, using default delay`);
        return MAINTENANCE_CONFIG.DEFAULT_DELAY_MS;
    }

    // Apply safety buffer: multiply by factor and add fixed buffer
    const safeDuration = durationMs * MAINTENANCE_CONFIG.SAFETY_MULTIPLIER +
      MAINTENANCE_CONFIG.SAFETY_BUFFER_MS;

    console.log(
      `Parsed maintenance duration: ${value} ${unit} (${durationMs}ms) -> ${safeDuration}ms with safety buffer`,
    );

    return Math.round(safeDuration);
  }

  /**
   * Check HTML response and throw MaintenanceError if maintenance is detected
   */
  static checkAndThrow(html: string): void {
    if (!this.isMaintenancePage(html)) {
      return;
    }

    const durationMs = this.parseMaintenanceDuration(html);
    const durationMinutes = Math.ceil(durationMs / 60000);

    throw new MaintenanceError(
      `Bricklink is currently under maintenance. Estimated duration: ${durationMinutes} minute(s)`,
      durationMs,
    );
  }
}

/**
 * Error thrown when Bricklink is undergoing maintenance.
 * This error should not count toward circuit breaker thresholds
 * or retry limits, as it's a temporary scheduled downtime.
 */
export class MaintenanceError extends Error {
  public readonly isMaintenanceError = true;
  public readonly detectedAt: Date;
  public readonly estimatedDurationMs: number;

  constructor(message: string, estimatedDurationMs: number) {
    super(message);
    this.name = "MaintenanceError";
    this.detectedAt = new Date();
    this.estimatedDurationMs = estimatedDurationMs;

    // Maintains proper stack trace for where error was thrown
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, MaintenanceError);
    }
  }

  /**
   * Calculate when the maintenance is expected to end
   */
  getEstimatedEndTime(): Date {
    return new Date(this.detectedAt.getTime() + this.estimatedDurationMs);
  }

  /**
   * Type guard to check if an error is a MaintenanceError
   */
  static isMaintenanceError(error: unknown): error is MaintenanceError {
    return (
      error instanceof MaintenanceError ||
      (typeof error === "object" &&
        error !== null &&
        "isMaintenanceError" in error &&
        error.isMaintenanceError === true)
    );
  }
}

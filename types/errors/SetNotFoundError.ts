/**
 * Error thrown when a LEGO set cannot be found in a scraper's database.
 * This error indicates a permanent failure (set doesn't exist) and should not
 * trigger retries, as retrying will not change the outcome.
 *
 * Use cases:
 * - Set number doesn't exist in WorldBricks/BrickLink/etc.
 * - Search returns no results for the given set
 * - Set has been removed or never existed
 *
 * This error should:
 * - NOT count toward circuit breaker thresholds
 * - NOT trigger automatic retries
 * - Be logged and handled as a permanent failure
 */
export class SetNotFoundError extends Error {
  public readonly isSetNotFoundError = true;
  public readonly setNumber: string;
  public readonly source: string;
  public readonly detectedAt: Date;

  constructor(message: string, setNumber: string, source: string) {
    super(message);
    this.name = "SetNotFoundError";
    this.setNumber = setNumber;
    this.source = source;
    this.detectedAt = new Date();

    // Maintains proper stack trace for where error was thrown
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, SetNotFoundError);
    }
  }

  /**
   * Type guard to check if an error is a SetNotFoundError
   */
  static isSetNotFoundError(error: unknown): error is SetNotFoundError {
    return (
      error instanceof SetNotFoundError ||
      (typeof error === "object" &&
        error !== null &&
        "isSetNotFoundError" in error &&
        error.isSetNotFoundError === true)
    );
  }
}

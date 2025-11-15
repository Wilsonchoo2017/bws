/**
 * Error thrown when a scraper receives a 403 (Forbidden) response,
 * indicating rate limiting or access restrictions.
 * This error should not count toward circuit breaker thresholds
 * or retry limits, as it's a temporary rate limit condition.
 */
export class RateLimitError extends Error {
  public readonly isRateLimitError = true;
  public readonly detectedAt: Date;
  public readonly delayMs: number;
  public readonly consecutive403Count: number;
  public readonly domain: string;

  constructor(
    message: string,
    domain: string,
    consecutive403Count: number,
    delayMs: number,
  ) {
    super(message);
    this.name = "RateLimitError";
    this.detectedAt = new Date();
    this.domain = domain;
    this.consecutive403Count = consecutive403Count;
    this.delayMs = delayMs;

    // Maintains proper stack trace for where error was thrown
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, RateLimitError);
    }
  }

  /**
   * Calculate when the rate limit should be lifted and retry can occur
   */
  getRetryTime(): Date {
    return new Date(this.detectedAt.getTime() + this.delayMs);
  }

  /**
   * Get human-readable delay duration
   */
  getDelayDescription(): string {
    const hours = Math.floor(this.delayMs / (1000 * 60 * 60));
    const minutes = Math.floor((this.delayMs % (1000 * 60 * 60)) / (1000 * 60));

    if (hours > 0) {
      return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
    }
    return `${minutes}m`;
  }

  /**
   * Type guard to check if an error is a RateLimitError
   */
  static isRateLimitError(error: unknown): error is RateLimitError {
    return (
      error instanceof RateLimitError ||
      (typeof error === "object" &&
        error !== null &&
        "isRateLimitError" in error &&
        error.isRateLimitError === true)
    );
  }
}

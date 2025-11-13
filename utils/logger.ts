/**
 * Centralized logging utility with file-based logging
 * Uses Winston for structured logging with daily rotation
 */

import winston from "npm:winston@3.11.0";
import DailyRotateFile from "npm:winston-daily-rotate-file@4.7.1";
import { existsSync } from "https://deno.land/std@0.224.0/fs/mod.ts";

// Ensure logs directory exists
const LOGS_DIR = "./logs";
if (!existsSync(LOGS_DIR)) {
  Deno.mkdirSync(LOGS_DIR, { recursive: true });
}

/**
 * Custom format for console output - colorized and readable
 */
const consoleFormat = winston.format.combine(
  winston.format.colorize(),
  winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
  winston.format.printf(({ timestamp, level, message, ...meta }) => {
    const metaStr = Object.keys(meta).length
      ? `\n${JSON.stringify(meta, null, 2)}`
      : "";
    return `${timestamp} [${level}]: ${message}${metaStr}`;
  }),
);

/**
 * Custom format for file output - JSON structured logging
 */
const fileFormat = winston.format.combine(
  winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
  winston.format.errors({ stack: true }),
  winston.format.json(),
);

/**
 * Main application logger
 */
export const logger = winston.createLogger({
  level: Deno.env.get("LOG_LEVEL") || "info",
  transports: [
    // Console output for development
    new winston.transports.Console({
      format: consoleFormat,
    }),
    // Combined log file - all logs
    new DailyRotateFile({
      filename: `${LOGS_DIR}/app-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      maxSize: "20m",
      maxFiles: "14d",
      format: fileFormat,
    }),
    // Error log file - errors only
    new DailyRotateFile({
      filename: `${LOGS_DIR}/error-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      level: "error",
      maxSize: "20m",
      maxFiles: "30d",
      format: fileFormat,
    }),
  ],
});

/**
 * Queue-specific logger
 */
export const queueLogger = winston.createLogger({
  level: Deno.env.get("LOG_LEVEL") || "info",
  transports: [
    // Console output
    new winston.transports.Console({
      format: consoleFormat,
    }),
    // Queue-specific log file
    new DailyRotateFile({
      filename: `${LOGS_DIR}/queue-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      maxSize: "20m",
      maxFiles: "14d",
      format: fileFormat,
    }),
    // Error log file
    new DailyRotateFile({
      filename: `${LOGS_DIR}/error-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      level: "error",
      maxSize: "20m",
      maxFiles: "30d",
      format: fileFormat,
    }),
  ],
});

/**
 * Scraper-specific logger
 */
export const scraperLogger = winston.createLogger({
  level: Deno.env.get("LOG_LEVEL") || "info",
  transports: [
    // Console output
    new winston.transports.Console({
      format: consoleFormat,
    }),
    // Scraper-specific log file
    new DailyRotateFile({
      filename: `${LOGS_DIR}/scraper-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      maxSize: "20m",
      maxFiles: "14d",
      format: fileFormat,
    }),
    // Error log file
    new DailyRotateFile({
      filename: `${LOGS_DIR}/error-%DATE%.log`,
      datePattern: "YYYY-MM-DD",
      level: "error",
      maxSize: "20m",
      maxFiles: "30d",
      format: fileFormat,
    }),
  ],
});

/**
 * Helper to create a child logger with additional context
 */
export function createContextLogger(
  baseLogger: winston.Logger,
  context: Record<string, unknown>,
) {
  return baseLogger.child(context);
}

/**
 * Log levels:
 * - error: Error events that might still allow the application to continue
 * - warn: Warning messages for potentially harmful situations
 * - info: Informational messages highlighting application progress
 * - http: HTTP request logging
 * - verbose: Detailed information for debugging
 * - debug: Fine-grained information for diagnosing problems
 * - silly: Most detailed logging level
 */

export default logger;

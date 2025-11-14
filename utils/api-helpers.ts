/**
 * Shared API utilities for consistent error handling and response formatting.
 * Follows DRY principle by centralizing common API patterns.
 */

import { db } from "../db/client.ts";
import { products, scrapeSessions } from "../db/schema.ts";
import { eq } from "drizzle-orm";
import { imageDownloadService } from "../services/image/ImageDownloadService.ts";
import { imageStorageService } from "../services/image/ImageStorageService.ts";
import { scraperLogger } from "./logger.ts";

/**
 * Creates a standardized JSON response
 * @param data - Data to serialize to JSON
 * @param status - HTTP status code (default: 200)
 * @returns Response object with JSON content type
 */
export function createJsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Creates a standardized error response
 * @param error - Error object or unknown error
 * @param customMessage - Optional custom error message
 * @returns Response object with error details
 */
export function createErrorResponse(
  error: unknown,
  customMessage?: string,
): Response {
  const errorMessage = error instanceof Error ? error.message : "Unknown error";
  console.error(customMessage || "API Error:", error);

  return createJsonResponse(
    {
      error: customMessage || errorMessage,
      message: errorMessage,
    },
    500,
  );
}

/**
 * Creates a validation error response
 * @param message - Validation error message
 * @returns Response object with 400 status
 */
export function createValidationErrorResponse(message: string): Response {
  return createJsonResponse(
    { error: message },
    400,
  );
}

/**
 * Creates a not found error response
 * @param resource - Name of the resource that wasn't found
 * @returns Response object with 404 status
 */
export function createNotFoundResponse(resource: string): Response {
  return createJsonResponse(
    { error: `${resource} not found` },
    404,
  );
}

/**
 * Wraps an async handler with standardized error handling
 * @param handler - Async function that returns data
 * @returns Promise resolving to Response object
 */
export async function handleApiRequest<T>(
  handler: () => Promise<T>,
): Promise<Response> {
  try {
    const data = await handler();
    return createJsonResponse(data);
  } catch (error) {
    return createErrorResponse(error);
  }
}

/**
 * Pagination metadata structure
 */
export interface PaginationMeta {
  page: number;
  limit: number;
  totalCount: number;
  totalPages: number;
  hasNextPage: boolean;
  hasPrevPage: boolean;
}

/**
 * Calculates pagination metadata
 * @param page - Current page number (1-indexed)
 * @param limit - Items per page
 * @param totalCount - Total number of items
 * @returns Pagination metadata object
 */
export function calculatePagination(
  page: number,
  limit: number,
  totalCount: number,
): PaginationMeta {
  const totalPages = Math.ceil(totalCount / limit);
  const hasNextPage = page < totalPages;
  const hasPrevPage = page > 1;

  return {
    page,
    limit,
    totalCount,
    totalPages,
    hasNextPage,
    hasPrevPage,
  };
}

/**
 * Paginated response structure
 */
export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationMeta;
}

/**
 * Creates a paginated response
 * @param items - Array of items for current page
 * @param page - Current page number
 * @param limit - Items per page
 * @param totalCount - Total number of items
 * @returns Paginated response object
 */
export function createPaginatedResponse<T>(
  items: T[],
  page: number,
  limit: number,
  totalCount: number,
): PaginatedResponse<T> {
  return {
    items,
    pagination: calculatePagination(page, limit, totalCount),
  };
}

// ============================================================================
// Parser API Route Helpers (DRY Refactoring)
// ============================================================================

/**
 * Result of extracting HTML from a request
 */
export interface HtmlExtractionResult {
  html: string;
  sourceUrl?: string;
}

/**
 * Extract HTML content from a request
 * Handles both application/json and text/html content types
 *
 * @param req - The incoming request
 * @returns HTML content and optional source URL, or an error Response
 */
export async function extractHtmlFromRequest(
  req: Request,
): Promise<HtmlExtractionResult | Response> {
  const contentType = req.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const body = await req.json();
    if (!body.html) {
      return new Response(
        JSON.stringify({ error: "Missing 'html' field in JSON body" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
    return {
      html: body.html,
      sourceUrl: body.source_url,
    };
  } else if (contentType.includes("text/html")) {
    return {
      html: await req.text(),
    };
  } else {
    return new Response(
      JSON.stringify({
        error:
          "Invalid content type. Use 'application/json' with {html: '...', source_url: '...'} or 'text/html'",
      }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}

/**
 * Validate that the request method is POST
 *
 * @param req - The incoming request
 * @returns Error Response if method is not POST, null otherwise
 */
export function requirePostMethod(req: Request): Response | null {
  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method not allowed. Use POST." }),
      {
        status: 405,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
  return null;
}

/**
 * Options for downloading and storing a product image
 */
export interface DownloadImageOptions {
  productId: string;
  imageUrl: string;
  source: string;
}

/**
 * Download and store a product image locally
 * Handles errors gracefully and updates database status
 *
 * @param options - Image download options
 * @returns Promise that resolves when download is complete (or fails gracefully)
 */
export async function downloadAndStoreProductImage(
  options: DownloadImageOptions,
): Promise<void> {
  const { productId, imageUrl, source } = options;

  try {
    scraperLogger.info("Downloading image for product", {
      productId,
      imageUrl,
      source,
    });

    // Download the image
    const imageData = await imageDownloadService.download(imageUrl);

    // Store the image locally
    const storageResult = await imageStorageService.store(
      imageData.data,
      imageData.url,
      imageData.extension,
      productId,
    );

    // Update the product with local image path
    await db.update(products).set({
      localImagePath: storageResult.relativePath,
      imageDownloadedAt: new Date(),
      imageDownloadStatus: "completed",
    }).where(eq(products.productId, productId));

    scraperLogger.info("Successfully downloaded and stored image", {
      productId,
      localPath: storageResult.relativePath,
      source,
    });
  } catch (imageError) {
    // Log error but don't fail the entire product save
    scraperLogger.error("Error downloading/storing image", {
      productId,
      error: (imageError as Error).message,
      source,
    });

    // Mark as failed in database
    try {
      await db.update(products).set({
        imageDownloadStatus: "failed",
      }).where(eq(products.productId, productId));
    } catch (_updateError) {
      // Ignore errors updating status
    }
  }
}

/**
 * Options for handling parser API errors
 */
export interface HandleParserApiErrorOptions {
  error: unknown;
  sessionId: number | null;
  source: string;
  context?: Record<string, unknown>;
}

/**
 * Handle parser API errors consistently
 * Logs the error, updates session status, and returns error response
 *
 * @param options - Error handling options
 * @returns Error Response
 */
export async function handleParserApiError(
  options: HandleParserApiErrorOptions,
): Promise<Response> {
  const { error, sessionId, source, context = {} } = options;

  const errorMessage = error instanceof Error ? error.message : "Unknown error";

  scraperLogger.error(`Error in ${source} parser API`, {
    error: errorMessage,
    stack: error instanceof Error ? error.stack : undefined,
    sessionId,
    source,
    ...context,
  });

  // Update session with error if we have a session ID
  if (sessionId) {
    try {
      await db.update(scrapeSessions).set({
        status: "failed",
        errorMessage,
      }).where(eq(scrapeSessions.id, sessionId));
    } catch (_updateError) {
      // Ignore errors updating session
    }
  }

  return new Response(
    JSON.stringify({
      success: false,
      session_id: sessionId,
      error: errorMessage,
    }),
    {
      status: 500,
      headers: { "Content-Type": "application/json" },
    },
  );
}

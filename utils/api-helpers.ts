/**
 * Shared API utilities for consistent error handling and response formatting.
 * Follows DRY principle by centralizing common API patterns.
 */

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

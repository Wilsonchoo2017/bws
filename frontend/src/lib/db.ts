/**
 * Database access is now handled by the Python FastAPI backend.
 * Frontend API routes proxy to http://localhost:8005.
 *
 * This file is kept as a placeholder -- do not import DuckDB here,
 * as it will hold a file lock that blocks the Python backend.
 */

export const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

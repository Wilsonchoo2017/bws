/**
 * Raw Data Service exports
 * Provides singleton instance for dependency injection
 */

import { ScrapeRawDataRepository } from "../../db/repositories/ScrapeRawDataRepository.ts";
import { RawDataService } from "./RawDataService.ts";

// Singleton instance for global use
export const rawDataService = new RawDataService(
  new ScrapeRawDataRepository(),
);

// Export types and classes for testing
export { RawDataService } from "./RawDataService.ts";
export type { SaveRawDataOptions } from "./RawDataService.ts";

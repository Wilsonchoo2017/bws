/**
 * Repository interface exports
 *
 * SOLID PRINCIPLES APPLIED:
 * - Dependency Inversion Principle: Depend on abstractions, not concretions
 * - Interface Segregation Principle: Focused interfaces for specific data access needs
 * - Single Responsibility Principle: Each repository handles one data source
 */

export type { IProductRepository } from "./IProductRepository.ts";

export type {
  ConditionMetrics,
  IBricklinkRepository,
  PastSalesStatistics,
  TrendMetrics,
} from "./IBricklinkRepository.ts";

export type {
  IWorldBricksRepository,
  WorldBricksSet,
} from "./IWorldBricksRepository.ts";

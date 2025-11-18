import type { Product } from "../../../../db/schema.ts";

/**
 * Product repository interface (DIP - Dependency Inversion Principle)
 * Single Responsibility: Product data access abstraction
 *
 * Benefits:
 * - Allows mocking in tests
 * - Decouples business logic from database implementation
 * - Enables swapping database providers without changing business logic
 */
export interface IProductRepository {
  /**
   * Find a single product by its unique product ID
   */
  findByProductId(productId: string): Promise<Product | null>;

  /**
   * Find all products matching a LEGO set number
   * Note: Can return multiple products (e.g., different sources for same set)
   */
  findByLegoSetNumber(setNumber: string): Promise<Product[]>;

  /**
   * Batch operation: Find multiple products by IDs
   * Solves N+1 query problem by fetching all in one query
   */
  findByProductIds(productIds: string[]): Promise<Product[]>;
}

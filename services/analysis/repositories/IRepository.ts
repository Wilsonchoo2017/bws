/**
 * Repository interfaces following SOLID principles
 * Provides abstraction layer for data access (Dependency Inversion Principle)
 */

import type {
  BricklinkItem,
  BrickrankerRetirementItem,
  Product,
  RedditSearchResult,
} from "../../../db/schema.ts";

/**
 * Product repository interface
 * Single Responsibility: Product data access only
 */
export interface IProductRepository {
  findByProductId(productId: string): Promise<Product | null>;
  findByLegoSetNumber(setNumber: string): Promise<Product[]>;
}

/**
 * Bricklink repository interface
 * Single Responsibility: Bricklink data access only
 */
export interface IBricklinkRepository {
  findByLegoSetNumber(setNumber: string): Promise<BricklinkItem | null>;
  findByItemId(itemId: string): Promise<BricklinkItem | null>;
}

/**
 * Reddit repository interface
 * Single Responsibility: Reddit data access only
 */
export interface IRedditRepository {
  findByLegoSetNumber(setNumber: string): Promise<RedditSearchResult | null>;
}

/**
 * Retirement repository interface
 * Single Responsibility: Retirement data access only
 */
export interface IRetirementRepository {
  findByLegoSetNumber(
    setNumber: string,
  ): Promise<BrickrankerRetirementItem | null>;
}

/**
 * Drizzle ORM implementation of IProductRepository
 * Single Responsibility: Product data access using Drizzle ORM
 */

import { eq, inArray } from "drizzle-orm";
import type { DrizzleD1Database } from "drizzle-orm/d1";
import { db } from "../../../../db/client.ts";
import { type Product, products } from "../../../../db/schema.ts";
import type { IProductRepository } from "../interfaces/IProductRepository.ts";

export class DrizzleProductRepository implements IProductRepository {
  constructor(
    private readonly database: DrizzleD1Database<Record<string, never>> = db,
  ) {}

  /**
   * Find product by productId
   */
  async findByProductId(productId: string): Promise<Product | null> {
    try {
      const result = await this.database
        .select()
        .from(products)
        .where(eq(products.productId, productId))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      console.error(
        `[DrizzleProductRepository] Failed to fetch product ${productId}:`,
        error instanceof Error ? error.message : error,
      );
      throw error; // Re-throw for service layer to handle
    }
  }

  /**
   * Find products by LEGO set number
   */
  async findByLegoSetNumber(setNumber: string): Promise<Product[]> {
    try {
      return await this.database
        .select()
        .from(products)
        .where(eq(products.legoSetNumber, setNumber));
    } catch (error) {
      console.error(
        `[DrizzleProductRepository] Failed to fetch products for set ${setNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return []; // Return empty array on error
    }
  }

  /**
   * Find multiple products by productIds (batch operation)
   * Solves N+1 query problem by fetching all products in one query
   */
  async findByProductIds(productIds: string[]): Promise<Product[]> {
    if (productIds.length === 0) return [];

    try {
      return await this.database
        .select()
        .from(products)
        .where(inArray(products.productId, productIds));
    } catch (error) {
      console.error(
        `[DrizzleProductRepository] Failed to fetch products by IDs (count: ${productIds.length}):`,
        error instanceof Error ? error.message : error,
      );
      return []; // Return empty array on error
    }
  }
}

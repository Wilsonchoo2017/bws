/**
 * ProductRepository - Data access layer for products
 * Single Responsibility: Product database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq, inArray } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { type Product, products } from "../../../db/schema.ts";
import type { IProductRepository } from "./IRepository.ts";

export class ProductRepository implements IProductRepository {
  /**
   * Find product by productId
   */
  async findByProductId(productId: string): Promise<Product | null> {
    try {
      const result = await db
        .select()
        .from(products)
        .where(eq(products.productId, productId))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      console.error(
        `[ProductRepository] Failed to fetch product ${productId}:`,
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
      return await db
        .select()
        .from(products)
        .where(eq(products.legoSetNumber, setNumber));
    } catch (error) {
      console.error(
        `[ProductRepository] Failed to fetch products for set ${setNumber}:`,
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
      return await db
        .select()
        .from(products)
        .where(inArray(products.productId, productIds));
    } catch (error) {
      console.error(
        `[ProductRepository] Failed to fetch products by IDs (count: ${productIds.length}):`,
        error instanceof Error ? error.message : error,
      );
      return []; // Return empty array on error
    }
  }
}

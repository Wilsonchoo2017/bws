/**
 * WorldBricksRepository - Database access layer for WorldBricks LEGO sets
 *
 * Responsibilities (Single Responsibility Principle):
 * - CRUD operations for worldbricks_sets table
 * - Query building and execution
 * - Upsert operations (insert or update)
 * - Filtering and searching
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for WorldBricks data
 */

import { db } from "../../db/client.ts";
import {
  type WorldbricksSet,
  worldbricksSets,
  type NewWorldbricksSet,
} from "../../db/schema.ts";
import { eq, sql, and, or, isNull, inArray } from "drizzle-orm";

/**
 * Interface for update data
 */
export interface UpdateWorldBricksSetData {
  setName?: string | null;
  description?: string | null;
  yearReleased?: number | null;
  yearRetired?: number | null;
  designer?: string | null;
  partsCount?: number | null;
  dimensions?: string | null;
  imageUrl?: string | null;
  localImagePath?: string | null;
  imageDownloadedAt?: Date;
  imageDownloadStatus?: string;
  sourceUrl?: string | null;
  lastScrapedAt?: Date;
  scrapeStatus?: string;
  updatedAt?: Date;
}

/**
 * WorldBricksRepository - Handles all database operations for WorldBricks sets
 */
export class WorldBricksRepository {
  /**
   * Find set by set number
   */
  async findBySetNumber(setNumber: string): Promise<WorldbricksSet | undefined> {
    return await db.query.worldbricksSets.findFirst({
      where: eq(worldbricksSets.setNumber, setNumber),
    });
  }

  /**
   * Find set by database ID
   */
  async findById(id: number): Promise<WorldbricksSet | undefined> {
    return await db.query.worldbricksSets.findFirst({
      where: eq(worldbricksSets.id, id),
    });
  }

  /**
   * Find multiple sets by set numbers
   */
  async findBySetNumbers(setNumbers: string[]): Promise<WorldbricksSet[]> {
    if (setNumbers.length === 0) {
      return [];
    }

    return await db.select()
      .from(worldbricksSets)
      .where(inArray(worldbricksSets.setNumber, setNumbers));
  }

  /**
   * Create a new set
   */
  async create(data: NewWorldbricksSet): Promise<WorldbricksSet> {
    const [set] = await db.insert(worldbricksSets)
      .values(data)
      .returning();

    return set;
  }

  /**
   * Update an existing set
   */
  async update(
    setNumber: string,
    data: UpdateWorldBricksSetData,
  ): Promise<WorldbricksSet | undefined> {
    const [updated] = await db.update(worldbricksSets)
      .set({
        ...data,
        updatedAt: new Date(),
      })
      .where(eq(worldbricksSets.setNumber, setNumber))
      .returning();

    return updated;
  }

  /**
   * Upsert (insert or update) a set
   * If set exists, update it; otherwise, create it
   */
  async upsert(
    setNumber: string,
    data: Omit<NewWorldbricksSet, "setNumber">,
  ): Promise<WorldbricksSet> {
    const existing = await this.findBySetNumber(setNumber);

    if (existing) {
      // Update existing record
      const updated = await this.update(setNumber, data);
      if (!updated) {
        throw new Error(`Failed to update set ${setNumber}`);
      }
      return updated;
    } else {
      // Create new record
      return await this.create({
        setNumber,
        ...data,
      });
    }
  }

  /**
   * Delete a set
   */
  async delete(setNumber: string): Promise<boolean> {
    await db.delete(worldbricksSets)
      .where(eq(worldbricksSets.setNumber, setNumber));

    return true;
  }

  /**
   * Get all sets
   */
  async findAll(): Promise<WorldbricksSet[]> {
    return await db.query.worldbricksSets.findMany();
  }

  /**
   * Find sets with missing year_released data
   * Useful for identifying sets that need re-scraping
   */
  async findSetsWithMissingYearReleased(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(isNull(worldbricksSets.yearReleased));
  }

  /**
   * Find sets with missing year_retired data
   * Useful for identifying sets that need additional data sources
   */
  async findSetsWithMissingYearRetired(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(isNull(worldbricksSets.yearRetired));
  }

  /**
   * Find sets with missing parts_count data
   */
  async findSetsWithMissingPartsCount(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(isNull(worldbricksSets.partsCount));
  }

  /**
   * Find sets by year released
   */
  async findByYearReleased(year: number): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(eq(worldbricksSets.yearReleased, year));
  }

  /**
   * Find sets by year range
   */
  async findByYearRange(startYear: number, endYear: number): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(
        and(
          sql`${worldbricksSets.yearReleased} >= ${startYear}`,
          sql`${worldbricksSets.yearReleased} <= ${endYear}`,
        ),
      );
  }

  /**
   * Find sets with failed scrapes
   * Useful for retry logic
   */
  async findFailedScrapes(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(eq(worldbricksSets.scrapeStatus, "failed"));
  }

  /**
   * Find sets that haven't been scraped yet or failed
   * Useful for initial scraping or retries
   */
  async findSetsNeedingScraping(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(
        or(
          isNull(worldbricksSets.lastScrapedAt),
          eq(worldbricksSets.scrapeStatus, "failed"),
        ),
      );
  }

  /**
   * Get count of sets in database
   */
  async count(): Promise<number> {
    const result = await db.select({ count: sql<number>`count(*)::int` })
      .from(worldbricksSets);

    return result[0]?.count || 0;
  }

  /**
   * Get count of sets with year_released data
   */
  async countWithYearReleased(): Promise<number> {
    const result = await db.select({ count: sql<number>`count(*)::int` })
      .from(worldbricksSets)
      .where(sql`${worldbricksSets.yearReleased} IS NOT NULL`);

    return result[0]?.count || 0;
  }

  /**
   * Get count of sets with year_retired data
   */
  async countWithYearRetired(): Promise<number> {
    const result = await db.select({ count: sql<number>`count(*)::int` })
      .from(worldbricksSets)
      .where(sql`${worldbricksSets.yearRetired} IS NOT NULL`);

    return result[0]?.count || 0;
  }

  /**
   * Update image download status
   */
  async updateImageStatus(
    setNumber: string,
    status: string,
    localPath?: string,
  ): Promise<void> {
    await db.update(worldbricksSets)
      .set({
        imageDownloadStatus: status,
        localImagePath: localPath || null,
        imageDownloadedAt: status === "completed" ? new Date() : undefined,
        updatedAt: new Date(),
      })
      .where(eq(worldbricksSets.setNumber, setNumber));
  }

  /**
   * Find sets with images that need downloading
   */
  async findSetsNeedingImageDownload(): Promise<WorldbricksSet[]> {
    return await db.select()
      .from(worldbricksSets)
      .where(
        and(
          sql`${worldbricksSets.imageUrl} IS NOT NULL`,
          or(
            isNull(worldbricksSets.imageDownloadStatus),
            eq(worldbricksSets.imageDownloadStatus, "pending"),
            eq(worldbricksSets.imageDownloadStatus, "failed"),
          ),
        ),
      );
  }

  /**
   * Bulk upsert sets
   * Useful for batch operations
   */
  async bulkUpsert(sets: NewWorldbricksSet[]): Promise<number> {
    if (sets.length === 0) {
      return 0;
    }

    let successCount = 0;

    for (const set of sets) {
      try {
        await this.upsert(set.setNumber, set);
        successCount++;
      } catch (error) {
        console.error(`Failed to upsert set ${set.setNumber}:`, error);
      }
    }

    return successCount;
  }

  /**
   * Get statistics about the WorldBricks data
   */
  async getStats(): Promise<{
    total: number;
    withYearReleased: number;
    withYearRetired: number;
    withPartsCount: number;
    withImages: number;
    failedScrapes: number;
  }> {
    const [
      total,
      withYearReleased,
      withYearRetired,
      failedScrapes,
    ] = await Promise.all([
      this.count(),
      this.countWithYearReleased(),
      this.countWithYearRetired(),
      db.select({ count: sql<number>`count(*)::int` })
        .from(worldbricksSets)
        .where(eq(worldbricksSets.scrapeStatus, "failed"))
        .then((r) => r[0]?.count || 0),
    ]);

    const withPartsCountResult = await db.select({ count: sql<number>`count(*)::int` })
      .from(worldbricksSets)
      .where(sql`${worldbricksSets.partsCount} IS NOT NULL`);
    const withPartsCount = withPartsCountResult[0]?.count || 0;

    const withImagesResult = await db.select({ count: sql<number>`count(*)::int` })
      .from(worldbricksSets)
      .where(eq(worldbricksSets.imageDownloadStatus, "completed"));
    const withImages = withImagesResult[0]?.count || 0;

    return {
      total,
      withYearReleased,
      withYearRetired,
      withPartsCount,
      withImages,
      failedScrapes,
    };
  }
}

/**
 * Singleton instance for reuse across the application
 */
let repositoryInstance: WorldBricksRepository | null = null;

/**
 * Get the singleton WorldBricksRepository instance
 */
export function getWorldBricksRepository(): WorldBricksRepository {
  if (!repositoryInstance) {
    repositoryInstance = new WorldBricksRepository();
  }
  return repositoryInstance;
}

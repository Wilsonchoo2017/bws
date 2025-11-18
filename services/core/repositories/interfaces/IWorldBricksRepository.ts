/**
 * WorldBricks set data
 * Contains official LEGO release information
 */
export interface WorldBricksSet {
  setNumber: string;
  setName: string | null;
  yearReleased: number | null;
  yearRetired: number | null;
  partsCount: number | null;
  designer: string | null;
  dimensions: string | null;
}

/**
 * WorldBricks repository interface (DIP - Dependency Inversion Principle)
 * Single Responsibility: WorldBricks set data access abstraction
 *
 * WorldBricks provides:
 * - Official LEGO release/retirement years
 * - Parts count
 * - Designer information
 *
 * Benefits:
 * - Allows mocking in tests
 * - Decouples business logic from data source
 * - Enables caching or alternative data sources
 */
export interface IWorldBricksRepository {
  /**
   * Find WorldBricks set data by LEGO set number
   */
  findBySetNumber(setNumber: string): Promise<WorldBricksSet | null>;

  /**
   * Batch operation: Find multiple sets
   * Returns Map for O(1) lookup
   * Solves N+1 query problem
   */
  findBySetNumbers(setNumbers: string[]): Promise<Map<string, WorldBricksSet>>;
}

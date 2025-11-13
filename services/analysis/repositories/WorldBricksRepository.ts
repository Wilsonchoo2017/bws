/**
 * WorldBricksRepository - Adapter for WorldBricks data access
 * Single Responsibility: Adapt WorldBricks repository to analysis interface
 * Follows Adapter Pattern to bridge interface differences
 */

import { WorldBricksRepository as CoreWorldBricksRepository } from "../../worldbricks/WorldBricksRepository.ts";
import type { IWorldBricksRepository, WorldBricksSet } from "./IRepository.ts";

/**
 * Adapter that wraps the core WorldBricksRepository and implements IWorldBricksRepository
 * Converts undefined returns to null for interface consistency
 */
export class WorldBricksRepository implements IWorldBricksRepository {
  private coreRepo: CoreWorldBricksRepository;

  constructor() {
    this.coreRepo = new CoreWorldBricksRepository();
  }

  /**
   * Find set by set number
   * Converts undefined to null for interface compliance
   */
  async findBySetNumber(setNumber: string): Promise<WorldBricksSet | null> {
    const result = await this.coreRepo.findBySetNumber(setNumber);
    return result ?? null;
  }

  /**
   * Find multiple sets by set numbers
   * Returns a Map for efficient lookup
   */
  async findBySetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, WorldBricksSet>> {
    const results = await this.coreRepo.findBySetNumbers(setNumbers);

    // Convert array to Map, filtering out undefined values
    const map = new Map<string, WorldBricksSet>();
    for (const result of results) {
      if (result) {
        map.set(result.setNumber, result as WorldBricksSet);
      }
    }

    return map;
  }
}

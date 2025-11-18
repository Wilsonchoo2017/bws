/**
 * Unit tests for DemandScoringService
 * Tests the unified demand scoring logic before merging duplicates
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { DemandScoringService } from "../../../services/core/scoring/DemandScoringService.ts";
import type { DemandScoringInput } from "../../../services/core/scoring/DemandScoringService.ts";

Deno.test("DemandScoringService - Unit Tests", async (t) => {
  const service = new DemandScoringService();

  await t.step("should instantiate service", () => {
    assertExists(service);
  });

  await t.step("should calculate score for high-velocity sales", () => {
    const input: DemandScoringInput = {
      salesVelocity: 0.5, // 0.5 sales per day = excellent
      timesSold: 90, // 90 sales
      observationDays: 180, // over 6 months
      availableLots: 20,
      availableQty: 50, // Limited supply
    };

    const result = service.calculateScore(input);

    assertExists(result);
    assertEquals(result.score >= 60, true, `High velocity should score >= 60, got ${result.score}`);
    assertEquals(result.confidence > 0.4, true, `Should have reasonable confidence, got ${result.confidence}`);
  });

  await t.step("should calculate score for low-velocity sales", () => {
    const input: DemandScoringInput = {
      salesVelocity: 0.01, // 0.01 sales per day = poor
      timesSold: 2,
      observationDays: 180,
      availableLots: 100, // Many sellers, low demand
    };

    const result = service.calculateScore(input);

    assertExists(result);
    assertEquals(result.score <= 50, true, `Low velocity should score <= 50, got ${result.score}`);
    // Verify it's significantly lower than high-velocity
    assertEquals(result.score < 60, true, "Low velocity should score < 60");
  });

  await t.step("should boost score for positive price momentum", () => {
    const inputWithoutMomentum: DemandScoringInput = {
      salesVelocity: 0.2,
      timesSold: 36,
      observationDays: 180,
      currentPrice: 10000, // $100
    };

    const inputWithMomentum: DemandScoringInput = {
      ...inputWithoutMomentum,
      firstPrice: 8000, // Started at $80
      lastPrice: 10000, // Now $100 (25% increase)
    };

    const withoutResult = service.calculateScore(inputWithoutMomentum);
    const withResult = service.calculateScore(inputWithMomentum);

    // Positive price momentum should increase score
    assertEquals(
      withResult.score > withoutResult.score,
      true,
      "Positive momentum should increase score",
    );
  });

  await t.step("should reduce score for negative price momentum", () => {
    const input: DemandScoringInput = {
      salesVelocity: 0.2,
      timesSold: 36,
      observationDays: 180,
      firstPrice: 12000, // Started at $120
      lastPrice: 10000, // Now $100 (declining)
    };

    const result = service.calculateScore(input);

    assertExists(result);
    assertExists(result.components?.priceMomentum);
    assertEquals(
      result.components.priceMomentum.score < 50,
      true,
      "Declining prices should score below 50",
    );
  });

  await t.step("should penalize oversupply (many sellers)", () => {
    const fewSellers: DemandScoringInput = {
      salesVelocity: 0.2,
      timesSold: 36,
      observationDays: 180,
      availableLots: 5, // Few sellers
    };

    const manySellers: DemandScoringInput = {
      salesVelocity: 0.2,
      timesSold: 36,
      observationDays: 180,
      availableLots: 100, // Many sellers
    };

    const fewResult = service.calculateScore(fewSellers);
    const manyResult = service.calculateScore(manySellers);

    // More sellers = lower demand score (supply exceeds demand)
    assertEquals(
      manyResult.score < fewResult.score,
      true,
      "Many sellers should reduce demand score",
    );
  });

  await t.step("should handle missing data gracefully", () => {
    const minimalInput: DemandScoringInput = {
      // Only sales velocity
      salesVelocity: 0.2,
    };

    const result = service.calculateScore(minimalInput);

    assertExists(result);
    assertEquals(result.score >= 0 && result.score <= 100, true);
    assertEquals(
      result.confidence < 0.5,
      true,
      "Should have low confidence with minimal data",
    );
  });

  await t.step("should return zero score for no demand data", () => {
    const noData: DemandScoringInput = {};

    const result = service.calculateScore(noData);

    assertExists(result);
    assertEquals(result.score, 0, "No data should return 0 score");
    assertEquals(result.confidence, 0, "No data should have 0 confidence");
  });

  await t.step("should calculate supply/demand ratio correctly", () => {
    const balancedSupply: DemandScoringInput = {
      salesVelocity: 0.2, // 0.2 sales/day
      timesSold: 36,
      observationDays: 180,
      availableQty: 40, // 40 units / 0.2 sales per day = 200 days supply
    };

    const lowSupply: DemandScoringInput = {
      salesVelocity: 0.2,
      timesSold: 36,
      observationDays: 180,
      availableQty: 10, // 10 units / 0.2 sales per day = 50 days supply (scarce!)
    };

    const balancedResult = service.calculateScore(balancedSupply);
    const lowSupplyResult = service.calculateScore(lowSupply);

    // Lower supply = higher demand score
    assertEquals(
      lowSupplyResult.score > balancedResult.score,
      true,
      "Scarce supply should increase demand score",
    );
  });

  await t.step("should provide detailed component breakdown", () => {
    const input: DemandScoringInput = {
      salesVelocity: 0.3,
      timesSold: 54,
      observationDays: 180,
      firstPrice: 8000,
      lastPrice: 10000,
      availableLots: 15,
      availableQty: 30,
    };

    const result = service.calculateScore(input);

    assertExists(result.components);
    assertExists(result.components.salesVelocity);
    assertExists(result.components.priceMomentum);
    assertExists(result.components.marketDepth);
    assertExists(result.components.supplyDemandRatio);

    // Each component should have expected fields
    assertEquals(typeof result.components.salesVelocity.score, "number");
    assertEquals(typeof result.components.salesVelocity.weight, "number");
    assertEquals(
      typeof result.components.salesVelocity.weightedScore,
      "number",
    );
  });

  await t.step("should validate score is within 0-100 range", () => {
    const extremeInputs: DemandScoringInput[] = [
      { salesVelocity: 10.0, timesSold: 1800, observationDays: 180 }, // Extreme high
      { salesVelocity: 0.0001, timesSold: 0, observationDays: 180 }, // Extreme low
      { salesVelocity: -1 }, // Invalid negative
    ];

    for (const input of extremeInputs) {
      const result = service.calculateScore(input);
      assertEquals(
        result.score >= 0 && result.score <= 100,
        true,
        `Score should be clamped to 0-100, got ${result.score}`,
      );
    }
  });
});

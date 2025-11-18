/**
 * Unit tests for ScarcityMultiplierCalculator
 * Tests TRUE scarcity (supply vs demand)
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { ScarcityMultiplierCalculator } from "../../../services/core/calculators/ScarcityMultiplierCalculator.ts";

Deno.test("ScarcityMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new ScarcityMultiplierCalculator();

  await t.step("should return 1.0 (neutral) with no data", () => {
    const result = calculator.calculate({});
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle extremely scarce (< 1 month inventory)", () => {
    const result = calculator.calculate({
      availableQty: 10,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier >= 1.09, true);
    assertEquals(result.tier, "extremely_scarce");
  });

  await t.step("should handle very scarce (1-3 months)", () => {
    const result = calculator.calculate({
      availableQty: 30,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier >= 1.05 && result.multiplier < 1.10, true);
  });

  await t.step("should handle moderately scarce (3-6 months)", () => {
    const result = calculator.calculate({
      availableQty: 100,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier >= 1.02 && result.multiplier <= 1.07, true);
  });

  await t.step("should handle neutral (6-12 months)", () => {
    const result = calculator.calculate({
      availableQty: 200,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier >= 0.98 && result.multiplier <= 1.02, true);
  });

  await t.step("should handle abundant (12-24 months)", () => {
    const result = calculator.calculate({
      availableQty: 500,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier < 1.0, true);
  });

  await t.step("should fall back to qty/lots scoring without velocity", () => {
    const result = calculator.calculate({
      availableQty: 5,
      availableLots: 2,
    });
    assertEquals(result.multiplier > 1.0, true);
    assertEquals(result.monthsOfInventory, null);
  });

  await t.step("should clamp to range (0.95-1.10)", () => {
    const tests = [
      { availableQty: 1, salesVelocity: 1.0 },
      { availableQty: 1000, salesVelocity: 0.01 },
      { availableQty: 5, availableLots: 1 },
    ];

    for (const input of tests) {
      const result = calculator.calculate(input);
      assertEquals(
        result.multiplier >= 0.95 && result.multiplier <= 1.10,
        true,
        `Multiplier ${result.multiplier} should be in range 0.95-1.10`,
      );
    }
  });

  await t.step("should provide detailed explanation", () => {
    const result = calculator.calculate({
      availableQty: 10,
      salesVelocity: 0.5,
    });
    assertExists(result.explanation);
  });
});

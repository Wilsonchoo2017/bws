/**
 * Unit tests for SaturationMultiplierCalculator
 * Tests market saturation multiplier using months of inventory
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { SaturationMultiplierCalculator } from "../../../services/core/calculators/SaturationMultiplierCalculator.ts";

Deno.test("SaturationMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new SaturationMultiplierCalculator();

  await t.step("should return 1.0 (neutral) with no data", () => {
    const result = calculator.calculate({});
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle dead inventory (> 24 months)", () => {
    const result = calculator.calculate({
      availableQty: 5000,
      salesVelocity: 0.005,
    });
    assertEquals(result.multiplier, 0.50);
    assertEquals(result.monthsOfInventory !== undefined && result.monthsOfInventory > 24, true);
  });

  await t.step("should handle oversupplied market (12-24 months)", () => {
    const result = calculator.calculate({
      availableQty: 500,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier < 1.0 && result.multiplier > 0.50, true);
  });

  await t.step("should handle healthy inventory (3-12 months)", () => {
    const result = calculator.calculate({
      availableQty: 200,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle low inventory with premium (1-3 months)", () => {
    const result = calculator.calculate({
      availableQty: 50,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier >= 1.0 && result.multiplier <= 1.05, true);
  });

  await t.step("should handle very scarce inventory (< 1 month)", () => {
    const result = calculator.calculate({
      availableQty: 10,
      salesVelocity: 0.5,
    });
    assertEquals(result.multiplier, 1.05);
  });

  await t.step("should fall back to lots/qty scoring without velocity", () => {
    const result = calculator.calculate({
      availableQty: 1500,
      availableLots: 150,
    });
    assertEquals(result.multiplier < 1.0, true);
    assertEquals(result.monthsOfInventory, null);
  });

  await t.step("should provide detailed explanation", () => {
    const result = calculator.calculate({
      availableQty: 200,
      salesVelocity: 0.5,
    });
    assertExists(result.explanation);
  });
});

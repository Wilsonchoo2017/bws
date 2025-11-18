/**
 * Unit tests for LiquidityMultiplierCalculator
 * Tests liquidity multiplier based on sales velocity
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { LiquidityMultiplierCalculator } from "../../../services/core/calculators/LiquidityMultiplierCalculator.ts";

Deno.test("LiquidityMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new LiquidityMultiplierCalculator();

  await t.step("should return default (1.0) with no data", () => {
    const result = calculator.calculate({});
    assertEquals(result.multiplier, 1.0);
    assertEquals(result.liquidityScore, 50);
  });

  await t.step("should handle high velocity (>= 0.5 sales/day)", () => {
    const result = calculator.calculate({ salesVelocity: 0.6 });
    assertEquals(result.multiplier >= 1.04, true);
    assertEquals(result.liquidityScore >= 85, true);
  });

  await t.step("should handle medium velocity (0.1 - 0.5 sales/day)", () => {
    const result = calculator.calculate({ salesVelocity: 0.2 });
    assertEquals(result.multiplier >= 0.85 && result.multiplier <= 1.0, true);
  });

  await t.step("should handle low velocity (0.033 - 0.1 sales/day)", () => {
    const result = calculator.calculate({ salesVelocity: 0.05 });
    assertEquals(result.multiplier >= 0.70 && result.multiplier <= 0.90, true);
  });

  await t.step("should handle dead inventory (< 0.01 sales/day)", () => {
    const result = calculator.calculate({ salesVelocity: 0.005 });
    assertEquals(result.multiplier <= 0.70, true);
    assertEquals(result.liquidityScore <= 20, true);
  });

  await t.step("should handle avgDaysBetweenSales: fast (< 7 days)", () => {
    const result = calculator.calculate({ avgDaysBetweenSales: 5 });
    assertEquals(result.multiplier >= 1.04, true);
  });

  await t.step("should handle avgDaysBetweenSales: medium (7-30 days)", () => {
    const result = calculator.calculate({ avgDaysBetweenSales: 20 });
    assertEquals(result.multiplier >= 0.80 && result.multiplier <= 1.0, true);
  });

  await t.step("should handle avgDaysBetweenSales: slow (30-90 days)", () => {
    const result = calculator.calculate({ avgDaysBetweenSales: 60 });
    assertEquals(result.multiplier >= 0.70 && result.multiplier <= 0.90, true);
  });

  await t.step("should handle avgDaysBetweenSales: very slow (> 180 days)", () => {
    const result = calculator.calculate({ avgDaysBetweenSales: 200 });
    assertEquals(result.multiplier <= 0.70, true);
  });

  await t.step("should prefer salesVelocity over avgDaysBetweenSales", () => {
    const result = calculator.calculate({
      salesVelocity: 0.6,
      avgDaysBetweenSales: 200,
    });
    assertEquals(result.multiplier >= 1.04, true);
    assertEquals(result.explanation.toLowerCase().includes("sales/day"), true);
  });

  await t.step("should clamp multiplier to range (0.60 - 1.10)", () => {
    const tests = [
      { salesVelocity: 0.001 },
      { salesVelocity: 0.05 },
      { salesVelocity: 0.5 },
      { salesVelocity: 1.0 },
      { avgDaysBetweenSales: 1 },
      { avgDaysBetweenSales: 30 },
      { avgDaysBetweenSales: 300 },
    ];

    for (const input of tests) {
      const result = calculator.calculate(input);
      assertEquals(
        result.multiplier >= 0.60 && result.multiplier <= 1.10,
        true,
        `Multiplier ${result.multiplier} should be in range 0.60-1.10`,
      );
    }
  });

  await t.step("should provide detailed explanation", () => {
    const result = calculator.calculate({ salesVelocity: 0.6 });
    assertExists(result.explanation);
    assertEquals(result.tier !== undefined, true);
  });
});

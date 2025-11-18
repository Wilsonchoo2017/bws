/**
 * Unit tests for PPDMultiplierCalculator
 * Tests Parts-Per-Dollar quality multiplier
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { PPDMultiplierCalculator } from "../../../services/core/calculators/PPDMultiplierCalculator.ts";
import type { Cents } from "../../../types/price.ts";

Deno.test("PPDMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new PPDMultiplierCalculator();

  await t.step("should return 1.0 (neutral) with no data", () => {
    const result = calculator.calculate({});
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle excellent PPD (>= 10)", () => {
    const result = calculator.calculate({
      partsCount: 1000,
      msrp: 10000 as Cents,
    });
    assertEquals(result.multiplier, 1.10);
    assertEquals(result.ppd, 10);
    assertEquals(result.tier, "excellent");
  });

  await t.step("should handle good PPD (8-10)", () => {
    const result = calculator.calculate({
      partsCount: 900,
      msrp: 10000 as Cents,
    });
    assertEquals(result.multiplier, 1.05);
    assertEquals(result.tier, "good");
  });

  await t.step("should handle fair PPD (6-8)", () => {
    const result = calculator.calculate({
      partsCount: 700,
      msrp: 10000 as Cents,
    });
    assertEquals(result.multiplier, 1.00);
    assertEquals(result.tier, "fair");
  });

  await t.step("should handle poor PPD (< 6)", () => {
    const result = calculator.calculate({
      partsCount: 500,
      msrp: 10000 as Cents,
    });
    assertEquals(result.multiplier, 0.95);
    assertEquals(result.tier, "poor");
  });

  await t.step("should handle zero MSRP gracefully", () => {
    const result = calculator.calculate({
      partsCount: 1000,
      msrp: 0 as Cents,
    });
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle missing parts count", () => {
    const result = calculator.calculate({
      msrp: 10000 as Cents,
    });
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should provide detailed explanation", () => {
    const result = calculator.calculate({
      partsCount: 1000,
      msrp: 10000 as Cents,
    });
    assertExists(result.explanation);
    assertEquals(result.explanation.includes("10.0"), true);
  });

  await t.step("should clamp to range (0.95-1.10)", () => {
    const tests = [
      { partsCount: 100, msrp: 10000 as Cents },
      { partsCount: 2000, msrp: 10000 as Cents },
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
});

/**
 * Unit tests for ThemeMultiplierCalculator
 * Tests theme-based multiplier logic before extraction
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { ThemeMultiplierCalculator } from "../../../services/core/calculators/ThemeMultiplierCalculator.ts";

Deno.test("ThemeMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new ThemeMultiplierCalculator();

  await t.step("should return premium multiplier for Star Wars", () => {
    const result = calculator.calculate("Star Wars");
    assertEquals(result.multiplier >= 1.20, true, "Star Wars should be premium");
    assertExists(result.theme);
    assertEquals(result.theme, "Star Wars");
  });

  await t.step("should return premium multiplier for Harry Potter", () => {
    const result = calculator.calculate("Harry Potter");
    assertEquals(result.multiplier >= 1.15, true);
  });

  await t.step("should return premium multiplier for Architecture", () => {
    const result = calculator.calculate("Architecture");
    assertEquals(result.multiplier >= 1.20, true);
  });

  await t.step("should return default multiplier for unknown theme", () => {
    const result = calculator.calculate("Unknown Theme");
    assertEquals(result.multiplier, 1.0);
    assertEquals(result.theme, "Default");
  });

  await t.step("should return default multiplier for undefined theme", () => {
    const result = calculator.calculate(undefined);
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle case-insensitive theme names", () => {
    const result1 = calculator.calculate("star wars");
    const result2 = calculator.calculate("STAR WARS");
    const result3 = calculator.calculate("Star Wars");

    assertEquals(result1.multiplier, result2.multiplier);
    assertEquals(result2.multiplier, result3.multiplier);
  });

  await t.step("should handle theme aliases (Star Wars variations)", () => {
    const result = calculator.calculate("Star Wars: The Clone Wars");
    assertEquals(result.multiplier >= 1.20, true, "Should match Star Wars alias");
  });

  await t.step("should return lower multiplier for budget themes", () => {
    const friendsResult = calculator.calculate("Friends");
    const duploResult = calculator.calculate("Duplo");

    assertEquals(friendsResult.multiplier <= 1.0, true);
    assertEquals(duploResult.multiplier <= 1.0, true);
  });

  await t.step("should provide explanation", () => {
    const result = calculator.calculate("Star Wars");
    assertExists(result.explanation);
    assertEquals(result.explanation.includes("Star Wars"), true);
    assertEquals(result.explanation.includes("1."), true, "Should include multiplier value");
  });

  await t.step("should validate multiplier range", () => {
    const themes = [
      "Star Wars",
      "Harry Potter",
      "Architecture",
      "City",
      "Friends",
      "Duplo",
      "Unknown",
    ];

    for (const theme of themes) {
      const result = calculator.calculate(theme);
      assertEquals(
        result.multiplier >= 0.7 && result.multiplier <= 1.5,
        true,
        `${theme} multiplier should be in range 0.7-1.5, got ${result.multiplier}`,
      );
    }
  });

  await t.step("should handle whitespace and special characters", () => {
    const result1 = calculator.calculate("  Star Wars  ");
    const result2 = calculator.calculate("Star Wars");

    assertEquals(result1.multiplier, result2.multiplier);
  });
});

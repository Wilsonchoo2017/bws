/**
 * Unit tests for RetirementMultiplierCalculator
 * Tests time-decayed retirement multiplier logic with demand gating
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { RetirementMultiplierCalculator } from "../../../services/core/calculators/RetirementMultiplierCalculator.ts";

Deno.test("RetirementMultiplierCalculator - Unit Tests", async (t) => {
  const calculator = new RetirementMultiplierCalculator();

  await t.step("should return 1.0 for active sets", () => {
    const result = calculator.calculate({
      retirementStatus: "active",
      yearsPostRetirement: 0,
      demandScore: 70,
    });

    assertEquals(result.multiplier, 1.0);
    assertExists(result.explanation);
    assertEquals(result.explanation.toLowerCase().includes("active"), true);
  });

  await t.step("should return 1.08 for retiring soon sets", () => {
    const result = calculator.calculate({
      retirementStatus: "retiring_soon",
      demandScore: 70,
    });

    assertEquals(result.multiplier, 1.08);
    assertEquals(result.explanation.toLowerCase().includes("retiring soon"), true);
  });

  await t.step("should apply J-curve: Year 0-1 (market flooded)", () => {
    const result = calculator.calculate({
      retirementStatus: "retired",
      yearsPostRetirement: 0.5,
      demandScore: 70,
    });

    assertEquals(result.multiplier, 0.95);
  });

  await t.step("should apply J-curve: Year 2-5 (early appreciation)", () => {
    const result = calculator.calculate({
      retirementStatus: "retired",
      yearsPostRetirement: 3,
      demandScore: 70,
    });

    assertEquals(result.multiplier, 1.15);
  });

  await t.step("should apply J-curve: Year 10+ (vintage status)", () => {
    const result = calculator.calculate({
      retirementStatus: "retired",
      yearsPostRetirement: 15,
      demandScore: 70,
    });

    assertEquals(result.multiplier, 2.0);
  });

  await t.step("should gate retirement premium with low demand", () => {
    const result = calculator.calculate({
      retirementStatus: "retired",
      yearsPostRetirement: 10,
      demandScore: 30,
    });

    assertEquals(result.multiplier, 1.02);
  });
});

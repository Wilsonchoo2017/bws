/**
 * Unit tests for ValueInputValidator
 * Tests validation and sanitization of IntrinsicValueInputs
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { ValueInputValidator } from "../../../services/core/validation/ValueInputValidator.ts";
import type { IntrinsicValueInputs } from "../../../types/value-investing.ts";
import type { Cents } from "../../../types/price.ts";

Deno.test("ValueInputValidator - Unit Tests", async (t) => {
  await t.step("should validate complete, valid inputs", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      currentRetailPrice: 9000 as Cents,
      demandScore: 75,
      qualityScore: 80,
      salesVelocity: 0.5,
      availableQty: 100,
      availableLots: 20,
      retirementStatus: "retired",
      yearsPostRetirement: 3,
      theme: "Star Wars",
      partsCount: 1000,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, true);
    assertEquals(result.missingCritical.length, 0);
    assertEquals(result.warnings.length, 0);
    assertExists(result.sanitizedData);
  });

  await t.step("should detect missing critical pricing data", () => {
    const inputs: IntrinsicValueInputs = {
      // No pricing at all
      demandScore: 75,
      qualityScore: 80,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, false);
    assertEquals(result.missingCritical.length > 0, true);
    assertEquals(
      result.missingCritical[0].includes("pricing"),
      true,
      "Should identify missing pricing",
    );
  });

  await t.step("should accept MSRP as sufficient pricing", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, true, "MSRP alone should be valid");
    assertEquals(result.missingCritical.length, 0);
  });

  await t.step("should accept currentRetailPrice as sufficient pricing", () => {
    const inputs: IntrinsicValueInputs = {
      currentRetailPrice: 9000 as Cents,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, true);
    assertEquals(result.missingCritical.length, 0);
  });

  await t.step("should accept bricklinkAvgPrice as sufficient pricing", () => {
    const inputs: IntrinsicValueInputs = {
      bricklinkAvgPrice: 12000 as Cents,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, true);
    assertEquals(result.missingCritical.length, 0);
  });

  await t.step("should identify missing optional fields", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      // Missing scores, liquidity, saturation
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, true, "Should be valid with just pricing");
    assertEquals(
      result.missingOptional.length > 0,
      true,
      "Should identify missing optional fields",
    );
    assertEquals(
      result.missingOptional.some((f) => f.includes("demandScore")),
      true,
    );
  });

  await t.step("should sanitize negative prices", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: -10000 as Cents, // Invalid negative
      currentRetailPrice: 9000 as Cents,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true, "Should warn about negative price");
    assertEquals(
      result.warnings[0].includes("negative"),
      true,
    );
    // Should use currentRetailPrice instead
    assertExists(result.sanitizedData);
    assertEquals(result.sanitizedData.msrp, undefined);
    assertEquals(result.sanitizedData.currentRetailPrice, 9000 as Cents);
  });

  await t.step("should sanitize extreme outlier prices", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 20000000 as Cents, // $200k (unrealistic)
      currentRetailPrice: 9000 as Cents,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertEquals(
      result.warnings[0].includes("exceeds maximum") ||
      result.warnings[0].includes("outlier"),
      true,
    );
  });

  await t.step("should sanitize negative sales velocity", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      salesVelocity: -0.5, // Invalid negative
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertExists(result.sanitizedData);
    assertEquals(
      result.sanitizedData.salesVelocity,
      0,
      "Should clamp to 0",
    );
  });

  await t.step("should sanitize unrealistic sales velocity", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      salesVelocity: 50, // 50 sales/day is unrealistic
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertEquals(
      result.warnings[0].includes("exceeds maximum") ||
      result.warnings[0].includes("unrealistic"),
      true,
    );
  });

  await t.step("should sanitize negative availability", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      availableQty: -100,
      availableLots: -20,
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertExists(result.sanitizedData);
    assertEquals(result.sanitizedData.availableQty, 0);
    assertEquals(result.sanitizedData.availableLots, 0);
  });

  await t.step("should sanitize invalid scores", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 150, // > 100
      qualityScore: -10, // < 0
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length >= 2, true);
    assertExists(result.sanitizedData);
    assertEquals(result.sanitizedData.demandScore, 100, "Should clamp to 100");
    assertEquals(result.sanitizedData.qualityScore, 0, "Should clamp to 0");
  });

  await t.step("should sanitize invalid parts count", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      partsCount: -100, // Negative
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertExists(result.sanitizedData);
    assertEquals(
      result.sanitizedData.partsCount,
      undefined,
      "Should reject negative parts",
    );
  });

  await t.step("should sanitize extreme parts count", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      partsCount: 50000, // Way too high
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
  });

  await t.step("should validate years post retirement", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      yearsPostRetirement: -5, // Negative
    };

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.warnings.length > 0, true);
    assertExists(result.sanitizedData);
    assertEquals(result.sanitizedData.yearsPostRetirement, 0);
  });

  await t.step("should handle empty inputs", () => {
    const inputs: IntrinsicValueInputs = {};

    const result = ValueInputValidator.validate(inputs);

    assertEquals(result.isValid, false);
    assertEquals(result.missingCritical.length > 0, true);
  });

  await t.step("should not mutate input data", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 75,
    };

    const inputsCopy = JSON.parse(JSON.stringify(inputs));

    ValueInputValidator.validate(inputs);

    assertEquals(
      JSON.stringify(inputs),
      JSON.stringify(inputsCopy),
      "Should not mutate input",
    );
  });

  await t.step("should provide detailed breakdown", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      salesVelocity: -0.5, // Will be sanitized
      demandScore: 150, // Will be clamped
    };

    const result = ValueInputValidator.validate(inputs);

    assertExists(result.sanitizedData);
    assertExists(result.warnings);
    assertExists(result.missingCritical);
    assertExists(result.missingOptional);
    assertEquals(typeof result.isValid, "boolean");
  });

  await t.step("should validate with sanitize=false option", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: -10000 as Cents, // Invalid
      // No other pricing (so invalid overall)
    };

    const result = ValueInputValidator.validate(inputs, { sanitize: false });

    assertEquals(result.isValid, false, "Should be invalid with only bad pricing");
    assertEquals(result.warnings.length > 0, true);
    assertEquals(
      result.missingCritical.length > 0,
      true,
      "Should have missing critical data",
    );
  });

  await t.step("should respect strictMode option", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      // Missing scores in strict mode should fail
    };

    const normalResult = ValueInputValidator.validate(inputs);
    const strictResult = ValueInputValidator.validate(inputs, {
      strictMode: true,
    });

    assertEquals(normalResult.isValid, true, "Normal mode should pass");
    assertEquals(
      strictResult.isValid,
      false,
      "Strict mode should require scores",
    );
  });
});

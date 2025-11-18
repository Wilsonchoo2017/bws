/**
 * Unit tests for IntrinsicValueInputMapper
 * Tests centralized data transformation logic
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { IntrinsicValueInputMapper } from "../../../services/core/mapping/IntrinsicValueInputMapper.ts";
import type { ValueInputSourceData } from "../../../services/core/mapping/IntrinsicValueInputMapper.ts";

Deno.test("IntrinsicValueInputMapper - Unit Tests", async (t) => {
  await t.step("should map complete source data", () => {
    const source: ValueInputSourceData = {
      pricing: {
        msrp: 10000,
        currentRetailPrice: 9000,
        bricklinkCurrentNewAvg: 12000,
      },
      retirement: {
        status: "retired",
        yearsPostRetirement: 3,
        yearReleased: 2020,
      },
      market: {
        salesVelocity: 0.5,
        availableQty: 100,
        availableLots: 20,
      },
      product: {
        theme: "Star Wars",
        partsCount: 1000,
      },
      scores: {
        demandScore: 75,
        qualityScore: 80,
      },
    };

    const result = IntrinsicValueInputMapper.map(source);

    assertExists(result);
    assertEquals(result.msrp, 10000);
    assertEquals(result.currentRetailPrice, 9000);
    assertEquals(result.bricklinkAvgPrice, 12000);
    assertEquals(result.retirementStatus, "retired");
    assertEquals(result.yearsPostRetirement, 3);
    assertEquals(result.salesVelocity, 0.5);
    assertEquals(result.theme, "Star Wars");
    assertEquals(result.partsCount, 1000);
    assertEquals(result.demandScore, 75);
    assertEquals(result.qualityScore, 80);
  });

  await t.step("should handle minimal source data", () => {
    const source: ValueInputSourceData = {
      pricing: {
        msrp: 10000,
      },
    };

    const result = IntrinsicValueInputMapper.map(source);

    assertExists(result);
    assertEquals(result.msrp, 10000);
    // Other fields should be undefined (not included)
    assertEquals(result.demandScore, undefined);
    assertEquals(result.qualityScore, undefined);
  });

  await t.step("should apply fallback values", () => {
    const source: ValueInputSourceData = {
      pricing: {
        currentRetailPrice: 9000,
      },
    };

    const result = IntrinsicValueInputMapper.map(source, {
      fallbacks: {
        demandScore: 50,
        qualityScore: 50,
      },
    });

    assertExists(result);
    assertEquals(result.currentRetailPrice, 9000);
    assertEquals(result.demandScore, 50, "Should use fallback");
    assertEquals(result.qualityScore, 50, "Should use fallback");
  });

  await t.step("should prefer MSRP over retail when available", () => {
    const source: ValueInputSourceData = {
      pricing: {
        msrp: 10000,
        originalRetailPrice: 8000,
      },
    };

    const result = IntrinsicValueInputMapper.map(source, {
      preferMsrpOverRetail: true,
    });

    assertEquals(result.msrp, 10000, "Should use MSRP");
    assertEquals(result.originalRetailPrice, 8000, "Should still include original retail");
  });

  await t.step("should use originalRetailPrice as MSRP fallback", () => {
    const source: ValueInputSourceData = {
      pricing: {
        originalRetailPrice: 8000,
        // No MSRP
      },
    };

    const result = IntrinsicValueInputMapper.map(source, {
      preferMsrpOverRetail: true,
    });

    assertEquals(result.msrp, 8000, "Should use original retail as MSRP");
  });

  await t.step("should include optional fields when requested", () => {
    const source: ValueInputSourceData = {
      pricing: {
        msrp: 10000,
        // bricklinkCurrentNewAvg is undefined
      },
    };

    const withoutOptional = IntrinsicValueInputMapper.map(source, {
      includeOptionalFields: false,
    });

    const withOptional = IntrinsicValueInputMapper.map(source, {
      includeOptionalFields: true,
    });

    assertEquals(withoutOptional.bricklinkAvgPrice, undefined);
    assertEquals(withOptional.bricklinkAvgPrice, undefined); // Still undefined, but field exists
  });

  await t.step("should map from AnalysisInput format", () => {
    const analysisInput = {
      pricing: {
        originalRetailPrice: 10000,
        currentRetailPrice: 9000,
        bricklink: {
          current: {
            newAvg: 12000,
            newMax: 15000,
          },
        },
      },
      demand: {
        bricklinkSalesVelocity: 0.5,
        bricklinkAvgDaysBetweenSales: 2,
        bricklinkSixMonthNewTimesSold: 90,
        bricklinkTimesSold: undefined,
        bricklinkPriceVolatility: 0.1,
        bricklinkCurrentNewQty: 100,
        bricklinkCurrentNewLots: 20,
      },
      availability: {
        yearReleased: 2020,
      },
      quality: {
        theme: "Star Wars",
        partsCount: 1000,
      },
    };

    const scores = {
      demandScore: 75,
      qualityScore: 80,
      availabilityScore: 60,
    };

    const retirement = {
      status: "retired" as const,
      yearsPostRetirement: 3,
    };

    const result = IntrinsicValueInputMapper.fromAnalysisInput(
      analysisInput,
      scores,
      retirement,
    );

    assertExists(result);
    assertEquals(result.msrp, 10000);
    assertEquals(result.currentRetailPrice, 9000);
    assertEquals(result.bricklinkAvgPrice, 12000);
    assertEquals(result.salesVelocity, 0.5);
    assertEquals(result.timesSold, 90);
    assertEquals(result.theme, "Star Wars");
    assertEquals(result.demandScore, 75);
    assertEquals(result.retirementStatus, "retired");
  });

  await t.step("should handle timesSold fallback", () => {
    const analysisInput = {
      pricing: {},
      demand: {
        bricklinkSixMonthNewTimesSold: undefined,
        bricklinkTimesSold: 50, // Fallback
      },
      availability: {},
      quality: {},
    };

    const result = IntrinsicValueInputMapper.fromAnalysisInput(analysisInput);

    assertEquals(result.timesSold, 50, "Should use fallback timesSold");
  });

  await t.step("should validate inputs correctly", () => {
    const validInputs = {
      msrp: 10000,
      demandScore: 75,
    };

    const invalidInputs = {
      // No pricing at all
      theme: "Star Wars",
    };

    const validResult = IntrinsicValueInputMapper.validate(validInputs);
    const invalidResult = IntrinsicValueInputMapper.validate(invalidInputs);

    assertEquals(validResult.isValid, true);
    assertEquals(validResult.missingCritical.length, 0);

    assertEquals(invalidResult.isValid, false);
    assertEquals(invalidResult.missingCritical.length > 0, true);
    assertEquals(
      invalidResult.missingCritical[0].includes("pricing"),
      true,
    );
  });

  await t.step("should identify missing optional fields", () => {
    const inputs = {
      msrp: 10000, // Has critical pricing
      // Missing optional scores
    };

    const result = IntrinsicValueInputMapper.validate(inputs);

    assertEquals(result.isValid, true, "Should be valid with just pricing");
    assertEquals(result.missingOptional.length > 0, true, "Should identify missing optional fields");
    assertEquals(
      result.missingOptional.some((f) => f.includes("demandScore")),
      true,
    );
  });

  await t.step("should handle empty source data", () => {
    const source: ValueInputSourceData = {};

    const result = IntrinsicValueInputMapper.map(source);

    assertExists(result);
    // Should return empty object (all undefined)
    assertEquals(Object.keys(result).length, 0);
  });

  await t.step("should not mutate source data", () => {
    const source: ValueInputSourceData = {
      pricing: {
        msrp: 10000,
      },
    };

    const sourceCopy = JSON.parse(JSON.stringify(source));

    IntrinsicValueInputMapper.map(source);

    assertEquals(
      JSON.stringify(source),
      JSON.stringify(sourceCopy),
      "Source should not be mutated",
    );
  });
});

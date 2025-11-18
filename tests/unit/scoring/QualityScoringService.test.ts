/**
 * Unit tests for QualityScoringService
 * Tests the unified quality scoring logic before merging duplicates
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { QualityScoringService } from "../../../services/core/scoring/QualityScoringService.ts";
import type { QualityScoringInput } from "../../../services/core/scoring/QualityScoringService.ts";

Deno.test("QualityScoringService - Unit Tests", async (t) => {
  const service = new QualityScoringService();

  await t.step("should instantiate service", () => {
    assertExists(service);
  });

  await t.step("should score high parts-per-dollar (PPD) sets highly", () => {
    const input: QualityScoringInput = {
      partsCount: 1000,
      msrp: 10000, // $100 = 10 parts per dollar (excellent)
    };

    const result = service.calculateScore(input);

    assertExists(result);
    assertEquals(result.score >= 70, true, `High PPD should score >= 70, got ${result.score}`);
    assertExists(result.components?.ppdScore);
    assertEquals(result.components.ppdScore.score >= 80, true, "PPD component should be high");
  });

  await t.step("should score low parts-per-dollar (PPD) sets poorly", () => {
    const input: QualityScoringInput = {
      partsCount: 100,
      msrp: 10000, // $100 = 1 part per dollar (poor value)
    };

    const result = service.calculateScore(input);

    assertExists(result);
    assertEquals(result.score <= 50, true, `Low PPD should score <= 50, got ${result.score}`);
  });

  await t.step("should boost score for premium themes", () => {
    const genericInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      theme: "Generic",
    };

    const premiumInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      theme: "Star Wars",
    };

    const genericResult = service.calculateScore(genericInput);
    const premiumResult = service.calculateScore(premiumInput);

    assertEquals(
      premiumResult.score > genericResult.score,
      true,
      "Premium theme should increase score",
    );
  });

  await t.step("should score complex sets (many parts) higher", () => {
    const simpleInput: QualityScoringInput = {
      partsCount: 100,
      msrp: 2000, // $20
    };

    const complexInput: QualityScoringInput = {
      partsCount: 2000,
      msrp: 20000, // $200
    };

    const simpleResult = service.calculateScore(simpleInput);
    const complexResult = service.calculateScore(complexInput);

    // Complex sets generally score higher (more engaging build)
    assertEquals(
      complexResult.score >= simpleResult.score,
      true,
      "Complex sets should score at least as high as simple ones",
    );
  });

  await t.step("should boost score for scarce sets (few sellers)", () => {
    const commonInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      availableLots: 100, // Many sellers
    };

    const scarceInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      availableLots: 5, // Few sellers = scarce
    };

    const commonResult = service.calculateScore(commonInput);
    const scarceResult = service.calculateScore(scarceInput);

    assertEquals(
      scarceResult.score > commonResult.score,
      true,
      "Scarce sets should score higher",
    );
  });

  await t.step("should boost score for limited edition sets", () => {
    const regularInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      limitedEdition: false,
    };

    const limitedInput: QualityScoringInput = {
      partsCount: 500,
      msrp: 10000,
      limitedEdition: true,
    };

    const regularResult = service.calculateScore(regularInput);
    const limitedResult = service.calculateScore(limitedInput);

    assertEquals(
      limitedResult.score > regularResult.score,
      true,
      "Limited edition should increase score",
    );
  });

  await t.step("should handle missing data gracefully", () => {
    const minimalInput: QualityScoringInput = {
      partsCount: 500, // Only parts count
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

  await t.step("should return default score for no quality data", () => {
    const noData: QualityScoringInput = {};

    const result = service.calculateScore(noData);

    assertExists(result);
    assertEquals(result.score, 50, "No data should return neutral 50 score");
    assertEquals(result.confidence, 0, "No data should have 0 confidence");
  });

  await t.step("should provide detailed component breakdown", () => {
    const input: QualityScoringInput = {
      partsCount: 1000,
      msrp: 10000,
      theme: "Star Wars",
      availableLots: 10,
      limitedEdition: false,
    };

    const result = service.calculateScore(input);

    assertExists(result.components);
    assertExists(result.components.ppdScore);
    assertExists(result.components.complexityScore);
    assertExists(result.components.themePremium);
    assertExists(result.components.scarcityScore);

    // Each component should have expected fields
    assertEquals(typeof result.components.ppdScore.score, "number");
    assertEquals(typeof result.components.ppdScore.weight, "number");
    assertEquals(typeof result.components.ppdScore.weightedScore, "number");
  });

  await t.step("should validate score is within 0-100 range", () => {
    const extremeInputs: QualityScoringInput[] = [
      { partsCount: 10000, msrp: 1000 }, // Extreme PPD
      { partsCount: 10, msrp: 100000 }, // Poor PPD
      { partsCount: -100, msrp: 10000 }, // Invalid negative
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

  await t.step("should calculate PPD correctly", () => {
    const testCases = [
      { parts: 1000, msrp: 10000, expectedPPD: 10 }, // $100 / 1000 parts
      { parts: 500, msrp: 5000, expectedPPD: 10 }, // $50 / 500 parts
      { parts: 2000, msrp: 15000, expectedPPD: 13.33 }, // $150 / 2000 parts
    ];

    for (const testCase of testCases) {
      const result = service.calculateScore({
        partsCount: testCase.parts,
        msrp: testCase.msrp,
      });

      // PPD should be reflected in the component notes
      assertExists(result.components?.ppdScore.notes);
      assertEquals(
        result.components.ppdScore.notes.includes(testCase.expectedPPD.toFixed(1)),
        true,
        `Should calculate PPD of ${testCase.expectedPPD}`,
      );
    }
  });
});

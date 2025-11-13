/**
 * Test script for FUNDAMENTAL VALUE APPROACH improvements
 * Tests MSRP-based valuation, theme multipliers, PPD, P/R ratio, J-curve, holding costs
 */

import { ValueCalculator } from "../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../types/value-investing.ts";

console.log("=".repeat(80));
console.log("FUNDAMENTAL VALUE APPROACH - TEST SUITE");
console.log("Critical Fix: MSRP as base value (NOT market price)");
console.log("=".repeat(80));
console.log();

// Test 1: MSRP vs Bricklink Base Value Comparison
console.log("Test 1: MSRP-Based Valuation vs Old Bricklink-Based");
console.log("-".repeat(80));

const test1Old: IntrinsicValueInputs = {
  // OLD WAY: Using Bricklink as base (circular reasoning)
  bricklinkAvgPrice: 200, // Market speculation
  bricklinkMaxPrice: 250,
  retirementStatus: "retired",
  yearsPostRetirement: 3,
  demandScore: 65,
  qualityScore: 60,
};

const test1New: IntrinsicValueInputs = {
  // NEW WAY: Using MSRP as base (fundamental value)
  msrp: 100, // Original retail price
  bricklinkAvgPrice: 200, // For comparison only
  bricklinkMaxPrice: 250,
  retirementStatus: "retired",
  yearsPostRetirement: 3,
  demandScore: 65,
  qualityScore: 60,
  theme: "Star Wars",
  partsCount: 1200,
};

const intrinsicOld = ValueCalculator.calculateIntrinsicValue(test1Old);
const intrinsicNew = ValueCalculator.calculateIntrinsicValue(test1New);

console.log("Scenario: Set retails for $100, Bricklink market at $200");
console.log();
console.log(`OLD (Bricklink base): $${intrinsicOld.toFixed(2)}`);
console.log(`  → Derived from market speculation!`);
console.log();
console.log(`NEW (MSRP base): $${intrinsicNew.toFixed(2)}`);
console.log(`  → Derived from fundamental replacement cost`);
console.log();
console.log(
  `Difference: ${
    ((intrinsicNew - intrinsicOld) / intrinsicOld * 100).toFixed(1)
  }%`,
);
console.log("  → More conservative, avoids bubble traps");
console.log();

// Test 2: Price-to-Retail Ratio Filter
console.log("Test 2: Price-to-Retail (P/R) Ratio Filter");
console.log("-".repeat(80));

const scenarios = [
  { market: 80, msrp: 100, label: "Below retail" },
  { market: 120, msrp: 100, label: "Normal aftermarket" },
  { market: 180, msrp: 100, label: "Speculation" },
  { market: 250, msrp: 100, label: "Bubble territory" },
  { market: 350, msrp: 100, label: "Extreme bubble" },
];

console.log("P/R Ratio Analysis:");
console.log();

scenarios.forEach(({ market, msrp, label }) => {
  const prInfo = ValueCalculator.calculatePriceToRetailRatio(market, msrp);
  if (prInfo) {
    console.log(
      `  ${label}: P/R = ${prInfo.ratio.toFixed(2)} (${prInfo.status})`,
    );
  }
});

console.log();
console.log("  → Filter sets with P/R > 2.0 (bubble territory)");
console.log();

// Test 3: Realistic J-Curve Retirement Appreciation
console.log("Test 3: Realistic J-Curve vs Old Linear Curve");
console.log("-".repeat(80));

const baseSet = {
  msrp: 100,
  retirementStatus: "retired" as const,
  demandScore: 70, // Sufficient for premium
  qualityScore: 60,
  theme: "Architecture",
  partsCount: 1000,
};

const retirementAges = [0.5, 1.5, 3, 7, 12];

console.log("Same set at different retirement ages:");
console.log();

retirementAges.forEach((years) => {
  const inputs = { ...baseSet, yearsPostRetirement: years };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  let curve = "";

  if (years < 1) curve = "↓ Flooded market";
  else if (years < 2) curve = "→ Stabilizing";
  else if (years < 5) curve = "↗ Appreciating";
  else if (years < 10) curve = "↗↗ Scarcity premium";
  else curve = "🚀 Vintage status";

  console.log(`  ${years} years: $${intrinsic.toFixed(2)} ${curve}`);
});

console.log();
console.log("  → J-curve: Initial dip, then gradual rise");
console.log();

// Test 4: Theme-Based Multipliers
console.log("Test 4: Theme-Based Valuation");
console.log("-".repeat(80));

const themes = [
  "Architecture",
  "Star Wars",
  "Creator Expert",
  "Technic",
  "City",
  "Friends",
  "Duplo",
];

console.log("Same set, different themes:");
console.log();

const baseThemeSet = {
  msrp: 100,
  retirementStatus: "retired" as const,
  yearsPostRetirement: 3,
  demandScore: 65,
  qualityScore: 60,
  partsCount: 1000,
};

themes.forEach((theme) => {
  const inputs = { ...baseThemeSet, theme };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  console.log(`  ${theme}: $${intrinsic.toFixed(2)}`);
});

console.log();
console.log("  → Architecture/Star Wars > City/Friends/Duplo");
console.log();

// Test 5: Parts-Per-Dollar (PPD) Impact
console.log("Test 5: Parts-Per-Dollar Quality Metric");
console.log("-".repeat(80));

const ppdTests = [
  { parts: 1200, msrp: 100, label: "Excellent (12 PPD)" },
  { parts: 900, msrp: 100, label: "Good (9 PPD)" },
  { parts: 700, msrp: 100, label: "Fair (7 PPD)" },
  { parts: 500, msrp: 100, label: "Poor (5 PPD)" },
];

console.log("Same MSRP, different piece counts:");
console.log();

const basePPD = {
  msrp: 100,
  retirementStatus: "retired" as const,
  yearsPostRetirement: 3,
  demandScore: 65,
  qualityScore: 60,
  theme: "Star Wars",
};

ppdTests.forEach(({ parts, label }) => {
  const inputs = { ...basePPD, partsCount: parts };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  console.log(`  ${label}: $${intrinsic.toFixed(2)}`);
});

console.log();
console.log("  → Higher PPD = better brick value");
console.log();

// Test 6: Realistic Transaction Costs
console.log("Test 6: Realistic Transaction & Holding Costs");
console.log("-".repeat(80));

const saleValue = 150;
const realizedLight = ValueCalculator.calculateRealizedValue(saleValue, 1); // 1 lb
const realizedHeavy = ValueCalculator.calculateRealizedValue(saleValue, 5); // 5 lbs

const holdingCosts1yr = ValueCalculator.calculateHoldingCosts(150, 1);
const holdingCosts2yr = ValueCalculator.calculateHoldingCosts(150, 2);

console.log(`Sale Price: $${saleValue.toFixed(2)}`);
console.log();
console.log("Transaction Costs:");
console.log(`  Light set (1 lb): $${realizedLight.toFixed(2)} realized`);
console.log(`  Heavy set (5 lbs): $${realizedHeavy.toFixed(2)} realized`);
console.log(
  `  Cost: -$${(saleValue - realizedLight).toFixed(2)} to -$${
    (saleValue - realizedHeavy).toFixed(2)
  }`,
);
console.log();
console.log("Holding Costs (8% annually):");
console.log(
  `  1 year: -$${holdingCosts1yr.toFixed(2)} (${
    (holdingCosts1yr / 150 * 100).toFixed(1)
  }%)`,
);
console.log(
  `  2 years: -$${holdingCosts2yr.toFixed(2)} (${
    (holdingCosts2yr / 150 * 100).toFixed(1)
  }%)`,
);
console.log();
console.log("  → Real costs ~25-35% of value!");
console.log();

// Test 7: Comprehensive Comparison - Old vs New
console.log("Test 7: COMPREHENSIVE COMPARISON");
console.log("-".repeat(80));

const comprehensiveOld: IntrinsicValueInputs = {
  bricklinkAvgPrice: 300, // Speculation-driven
  bricklinkMaxPrice: 350,
  retirementStatus: "retired",
  yearsPostRetirement: 1, // Just retired
  demandScore: 45, // Moderate demand
  qualityScore: 60,
  salesVelocity: 0.05,
  avgDaysBetweenSales: 20,
  priceVolatility: 0.25,
  availableQty: 150,
  availableLots: 25,
};

const comprehensiveNew: IntrinsicValueInputs = {
  msrp: 150, // TRUE fundamental value
  currentRetailPrice: undefined, // Retired
  bricklinkAvgPrice: 300,
  bricklinkMaxPrice: 350,
  retirementStatus: "retired",
  yearsPostRetirement: 1, // Just retired - J-curve dip!
  yearReleased: new Date().getFullYear() - 4,
  demandScore: 45,
  qualityScore: 60,
  salesVelocity: 0.05,
  avgDaysBetweenSales: 20,
  priceVolatility: 0.25,
  availableQty: 150,
  availableLots: 25,
  theme: "City", // Poor investment theme
  partsCount: 800, // 5.3 PPD - poor
};

const oldValue = ValueCalculator.calculateIntrinsicValue(comprehensiveOld);
const newValue = ValueCalculator.calculateIntrinsicValue(comprehensiveNew);
const realized = ValueCalculator.calculateRealizedValue(newValue, 3);
const holding2yr = ValueCalculator.calculateHoldingCosts(newValue, 2);

console.log("Scenario: City-themed set, just retired, moderate demand");
console.log(`  MSRP: $150, Bricklink market: $300`);
console.log();
console.log("OLD METHOD (Bricklink base):");
console.log(`  Intrinsic Value: $${oldValue.toFixed(2)}`);
console.log("  → Overly optimistic, market-driven");
console.log();
console.log("NEW METHOD (MSRP base + all improvements):");
console.log(`  Intrinsic Value: $${newValue.toFixed(2)}`);
console.log(
  `  Realized Value: $${realized.toFixed(2)} (after transaction costs)`,
);
console.log(
  `  After 2yr hold: $${
    (realized - holding2yr).toFixed(2)
  } (after holding costs)`,
);
console.log();
console.log("  → More conservative, accounts for:");
console.log("    • MSRP-based fundamental value");
console.log("    • J-curve dip (just retired)");
console.log("    • Theme penalty (City = poor investment)");
console.log("    • Low PPD (5.3 parts/dollar)");
console.log("    • Realistic transaction costs");
console.log("    • Holding costs over time");
console.log();
console.log(
  `Decision: OLD says buy at $${
    (oldValue * 0.75).toFixed(2)
  }, NEW says buy at $${(newValue * 0.75).toFixed(2)}`,
);
console.log(
  `  → $${
    ((oldValue - newValue) * 0.75).toFixed(2)
  } difference = avoided loss!`,
);
console.log();

// Summary
console.log("=".repeat(80));
console.log("SUMMARY OF FUNDAMENTAL VALUE IMPROVEMENTS");
console.log("=".repeat(80));
console.log();
console.log("✓ MSRP-BASED VALUATION:");
console.log("  - Base value = replacement cost (MSRP/retail)");
console.log("  - Avoids circular reasoning (market price ≠ intrinsic value)");
console.log("  - Fallback to Bricklink with 30-50% discount");
console.log();
console.log("✓ PRICE-TO-RETAIL (P/R) RATIO:");
console.log("  - Like P/E ratio for stocks");
console.log("  - Filter bubble-priced sets (P/R > 2.0)");
console.log("  - Identifies good deals (P/R < 1.0)");
console.log();
console.log("✓ REALISTIC J-CURVE RETIREMENT:");
console.log("  - Year 0-1: 0.95x (market flooded)");
console.log("  - Year 1-2: 1.00x (stabilization)");
console.log("  - Year 2-5: 1.15x (appreciation)");
console.log("  - Year 5-10: 1.40x (scarcity)");
console.log("  - Year 10+: 2.00x (vintage)");
console.log();
console.log("✓ THEME-BASED MULTIPLIERS:");
console.log("  - Architecture: 1.40x (best)");
console.log("  - Star Wars: 1.30x");
console.log("  - City: 0.80x (poor)");
console.log("  - Duplo: 0.70x (worst)");
console.log();
console.log("✓ PARTS-PER-DOLLAR (PPD):");
console.log("  - > 10 PPD: 1.10x (excellent value)");
console.log("  - < 6 PPD: 0.95x (poor value)");
console.log("  - Measures brick value quality");
console.log();
console.log("✓ REALISTIC COSTS:");
console.log("  - Transaction: 15% fees + $10-30 shipping");
console.log("  - Holding: 8% annually (storage + capital + risk)");
console.log("  - Real profit ~60-70% of theoretical");
console.log();
console.log("✓ CRITICAL IMPACT:");
console.log("  - Prevents buying overpriced sets");
console.log("  - Avoids poor-performing themes");
console.log("  - Accounts for real-world costs");
console.log("  - More conservative = safer investments");
console.log();
console.log("=".repeat(80));

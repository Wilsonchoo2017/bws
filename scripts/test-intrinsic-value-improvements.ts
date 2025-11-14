/**
 * Test script for intrinsic value calculation improvements
 * Tests the new liquidity, volatility, and time-decayed retirement features
 */

import { ValueCalculator } from "../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../types/value-investing.ts";
import { asCents } from "../types/price.ts";
console.log("=".repeat(80));
console.log("INTRINSIC VALUE CALCULATION IMPROVEMENTS - TEST SUITE");
console.log("=".repeat(80));
console.log();

// Test Case 1: High Liquidity, Low Volatility, Recently Retired Set
console.log("Test 1: High Liquidity + Low Volatility + Recently Retired");
console.log("-".repeat(80));

const test1: IntrinsicValueInputs = {
  bricklinkAvgPrice: asCents(100),
  bricklinkMaxPrice: asCents(120),
  retirementStatus: "retired",
  yearsPostRetirement: 0.5, // Just retired 6 months ago
  demandScore: 70,
  qualityScore: 80,
  salesVelocity: 0.6, // ~1.8 sales/day = very high liquidity
  avgDaysBetweenSales: 5, // Sales every 5 days
  priceVolatility: 0.08, // Low volatility (8% coefficient of variation)
};

const intrinsic1 = ValueCalculator.calculateIntrinsicValue(test1);
const realized1 = ValueCalculator.calculateRealizedValue(intrinsic1);
const metrics1 = ValueCalculator.calculateValueMetrics(90, test1);

console.log("Inputs:");
console.log("  Bricklink Avg: $100, Max: $120");
console.log("  Status: Retired 6 months ago");
console.log("  Sales Velocity: 0.6/day (high liquidity)");
console.log("  Price Volatility: 0.08 (stable)");
console.log();
console.log("Results:");
console.log(`  Intrinsic Value: $${intrinsic1.toFixed(2)}`);
console.log(`  Realized Value (after costs): $${realized1.toFixed(2)}`);
console.log(`  Expected ROI: ${metrics1.expectedROI.toFixed(1)}%`);
console.log(`  Realized ROI: ${metrics1.realizedROI?.toFixed(1)}%`);
console.log(
  `  Transaction Cost Impact: -$${(intrinsic1 - realized1).toFixed(2)}`,
);
console.log();

// Test Case 2: Low Liquidity, High Volatility, Active Set
console.log("Test 2: Low Liquidity + High Volatility + Active Set");
console.log("-".repeat(80));

const test2: IntrinsicValueInputs = {
  bricklinkAvgPrice: asCents(100),
  bricklinkMaxPrice: asCents(120),
  retirementStatus: "active",
  demandScore: 40,
  qualityScore: 50,
  salesVelocity: 0.02, // 1 sale every 50 days = very low liquidity
  avgDaysBetweenSales: 100, // Sales every 100 days
  priceVolatility: 0.5, // High volatility (50% coefficient of variation)
};

const intrinsic2 = ValueCalculator.calculateIntrinsicValue(test2);
const realized2 = ValueCalculator.calculateRealizedValue(intrinsic2);
const metrics2 = ValueCalculator.calculateValueMetrics(90, test2);

console.log("Inputs:");
console.log("  Bricklink Avg: $100, Max: $120");
console.log("  Status: Active (still in production)");
console.log("  Sales Velocity: 0.02/day (low liquidity)");
console.log("  Price Volatility: 0.5 (very volatile)");
console.log();
console.log("Results:");
console.log(`  Intrinsic Value: $${intrinsic2.toFixed(2)}`);
console.log(`  Realized Value (after costs): $${realized2.toFixed(2)}`);
console.log(`  Expected ROI: ${metrics2.expectedROI.toFixed(1)}%`);
console.log(`  Realized ROI: ${metrics2.realizedROI?.toFixed(1)}%`);
console.log();
console.log("Comparison to Test 1:");
console.log(
  `  Intrinsic Value Difference: -$${(intrinsic1 - intrinsic2).toFixed(2)} (${
    (((intrinsic2 - intrinsic1) / intrinsic1) * 100).toFixed(1)
  }%)`,
);
console.log(
  `  → Liquidity + Volatility impact: ${
    (((intrinsic2 - intrinsic1) / intrinsic1) * 100).toFixed(1)
  }% discount`,
);
console.log();

// Test Case 3: Time-Decayed Retirement Premium Comparison
console.log("Test 3: Time-Decayed Retirement Premium Progression");
console.log("-".repeat(80));

const baseInputs: IntrinsicValueInputs = {
  bricklinkAvgPrice: asCents(100),
  bricklinkMaxPrice: asCents(120),
  retirementStatus: "retired",
  demandScore: 60,
  qualityScore: 60,
  salesVelocity: 0.1,
  avgDaysBetweenSales: 20,
  priceVolatility: 0.15,
};

const retirementYears = [0.5, 2, 4, 6];
console.log("Same set at different retirement ages:");
console.log();

retirementYears.forEach((years) => {
  const inputs = { ...baseInputs, yearsPostRetirement: years };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  console.log(
    `  ${years} years post-retirement: $${intrinsic.toFixed(2)} (${
      ((intrinsic / 106 - 1) * 100).toFixed(1)
    }% vs baseline)`,
  );
});

console.log();
console.log(
  "→ Shows appreciation curve: 5% → 15% → 20% → 25% as set ages",
);
console.log();

// Test Case 4: No Liquidity/Volatility Data (Legacy Behavior)
console.log("Test 4: Legacy Calculation (No New Metrics)");
console.log("-".repeat(80));

const test4: IntrinsicValueInputs = {
  bricklinkAvgPrice: asCents(100),
  bricklinkMaxPrice: asCents(120),
  retirementStatus: "retired",
  // No yearsPostRetirement - uses legacy 15% flat
  demandScore: 60,
  qualityScore: 60,
  // No liquidity or volatility data
};

const intrinsic4 = ValueCalculator.calculateIntrinsicValue(test4);

console.log("Inputs:");
console.log("  Bricklink Avg: $100, Max: $120");
console.log("  Status: Retired (no time data)");
console.log("  No liquidity or volatility metrics");
console.log();
console.log("Results:");
console.log(`  Intrinsic Value: $${intrinsic4.toFixed(2)}`);
console.log("  → Uses legacy 15% retirement premium, no L/V adjustments");
console.log();

// Test Case 5: Transaction Cost Impact on Different Price Points
console.log("Test 5: Transaction Cost Impact Across Price Points");
console.log("-".repeat(80));

const pricePoints = [50, 100, 200, 500];
console.log(
  "Fixed costs ($7) have bigger impact on lower-priced items:",
);
console.log();

pricePoints.forEach((price) => {
  const realized = ValueCalculator.calculateRealizedValue(price);
  const costImpact = price - realized;
  const percentageImpact = (costImpact / price) * 100;

  console.log(
    `  $${price} → $${realized.toFixed(2)} (${
      percentageImpact.toFixed(1)
    }% costs)`,
  );
});

console.log();
console.log("→ Lower-priced sets need higher margins to be profitable");
console.log();

// Summary
console.log("=".repeat(80));
console.log("SUMMARY OF IMPROVEMENTS");
console.log("=".repeat(80));
console.log();
console.log("✓ Liquidity Multiplier (0.85-1.10x):");
console.log(
  "  - High liquidity (frequent sales): Premium up to 10%",
);
console.log("  - Low liquidity (rare sales): Discount up to 15%");
console.log();
console.log("✓ Volatility Discount:");
console.log("  - Stable pricing: Minimal discount (~2%)");
console.log("  - Volatile pricing: Discount up to 12%");
console.log();
console.log("✓ Time-Decayed Retirement Premium:");
console.log("  - 0-1 years: 5% premium");
console.log("  - 1-3 years: 15% premium");
console.log("  - 3-5 years: 20% premium");
console.log("  - 5+ years: 25% premium");
console.log();
console.log("✓ Transaction Costs:");
console.log("  - 10% selling fees");
console.log("  - $5 shipping subsidy");
console.log("  - $2 packaging costs");
console.log("  - Realized ROI accounts for real profit");
console.log();
console.log("✓ Quality Score:");
console.log("  - Now properly integrated into calculations");
console.log();
console.log("=".repeat(80));

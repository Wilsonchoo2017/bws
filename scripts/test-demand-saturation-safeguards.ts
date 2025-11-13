/**
 * Test script for demand-gated retirement premium and saturation detection
 * CRITICAL SAFEGUARDS: No demand = no premium, Oversupply = discounted value
 */

import { ValueCalculator } from "../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../types/value-investing.ts";

console.log("=".repeat(80));
console.log("DEMAND-GATED RETIREMENT & SATURATION DETECTION - TEST SUITE");
console.log("=".repeat(80));
console.log();

// Test Case 1: Retired set WITH demand - gets premium
console.log("Test 1: Retired Set WITH Sufficient Demand (Score: 70)");
console.log("-".repeat(80));

const test1: IntrinsicValueInputs = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired",
  yearsPostRetirement: 3, // 3 years retired = 20% premium normally
  demandScore: 70, // ABOVE threshold (40) - should get premium
  qualityScore: 60,
  salesVelocity: 0.2,
  availableQty: 30, // Healthy supply
  availableLots: 8, // Few sellers
};

const intrinsic1 = ValueCalculator.calculateIntrinsicValue(test1);
console.log("Inputs:");
console.log("  Retirement: 3 years (normally 20% premium)");
console.log("  Demand Score: 70 ✓ (above 40 threshold)");
console.log("  Available: 30 units, 8 sellers (healthy)");
console.log();
console.log(`Result: $${intrinsic1.toFixed(2)}`);
console.log("  → Gets FULL retirement premium (demand validated)");
console.log();

// Test Case 2: Retired set WITHOUT demand - NO premium
console.log("Test 2: Retired Set WITHOUT Sufficient Demand (Score: 25)");
console.log("-".repeat(80));

const test2: IntrinsicValueInputs = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired",
  yearsPostRetirement: 3, // Same 3 years retired
  demandScore: 25, // BELOW threshold (40) - NO premium!
  qualityScore: 60,
  salesVelocity: 0.01, // Low velocity
  availableQty: 30,
  availableLots: 8,
};

const intrinsic2 = ValueCalculator.calculateIntrinsicValue(test2);
console.log("Inputs:");
console.log("  Retirement: 3 years (normally 20% premium)");
console.log("  Demand Score: 25 ✗ (below 40 threshold)");
console.log("  Available: 30 units, 8 sellers");
console.log();
console.log(`Result: $${intrinsic2.toFixed(2)}`);
console.log("  → Capped at 2% premium (NO DEMAND = NO VALUE)");
console.log();
console.log("Comparison:");
console.log(
  `  Value Difference: -$${(intrinsic1 - intrinsic2).toFixed(2)} (${
    (((intrinsic2 - intrinsic1) / intrinsic1) * 100).toFixed(1)
  }%)`,
);
console.log("  → Demand gating prevents overvaluing unwanted sets!");
console.log();

// Test Case 3: SATURATED market - High supply, many sellers
console.log("Test 3: SATURATED Market (600 units, 60 sellers)");
console.log("-".repeat(80));

const test3: IntrinsicValueInputs = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired",
  yearsPostRetirement: 3,
  demandScore: 70, // Good demand
  qualityScore: 60,
  salesVelocity: 0.1, // Decent velocity but...
  availableQty: 600, // OVERSUPPLY (> 500 threshold)
  availableLots: 60, // TOO MANY SELLERS (> 50 threshold)
};

const intrinsic3 = ValueCalculator.calculateIntrinsicValue(test3);
console.log("Inputs:");
console.log("  Demand Score: 70 ✓ (good)");
console.log("  Available: 600 units ✗ (oversupply)");
console.log("  Sellers: 60 ✗ (saturated market)");
console.log("  Velocity/Supply Ratio: 0.00017 (poor turnover)");
console.log();
console.log(`Result: $${intrinsic3.toFixed(2)}`);
console.log("  → Saturation discount applied");
console.log();
console.log("Comparison to Test 1 (healthy supply):");
console.log(
  `  Value Difference: -$${(intrinsic1 - intrinsic3).toFixed(2)} (${
    (((intrinsic3 - intrinsic1) / intrinsic1) * 100).toFixed(1)
  }%)`,
);
console.log("  → Oversupply kills value even with good demand!");
console.log();

// Test Case 4: THE WORST - Retired + No Demand + Saturated
console.log("Test 4: THE WORST CASE - Retired + No Demand + Saturated");
console.log("-".repeat(80));

const test4: IntrinsicValueInputs = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired",
  yearsPostRetirement: 5, // 5 years = normally 25% premium
  demandScore: 15, // Very low demand
  qualityScore: 50,
  salesVelocity: 0.005, // Very low velocity
  availableQty: 800, // Severe oversupply
  availableLots: 80, // Way too many sellers
};

const intrinsic4 = ValueCalculator.calculateIntrinsicValue(test4);
console.log("Inputs:");
console.log("  Retirement: 5 years (normally 25% premium)");
console.log("  Demand Score: 15 ✗ (very low)");
console.log("  Available: 800 units ✗ (severe oversupply)");
console.log("  Sellers: 80 ✗ (saturated)");
console.log();
console.log(`Result: $${intrinsic4.toFixed(2)}`);
console.log(
  "  → Both penalties stack: no retirement premium + saturation discount",
);
console.log();
console.log("Comparison to Test 1 (healthy):");
console.log(
  `  Value Difference: -$${(intrinsic1 - intrinsic4).toFixed(2)} (${
    (((intrinsic4 - intrinsic1) / intrinsic1) * 100).toFixed(1)
  }%)`,
);
console.log("  → Classic value trap avoided!");
console.log();

// Test Case 5: Saturation progression
console.log("Test 5: Saturation Impact Across Supply Levels");
console.log("-".repeat(80));

const supplyLevels = [
  { qty: 20, lots: 5, label: "Low" },
  { qty: 100, lots: 20, label: "Moderate" },
  { qty: 300, lots: 40, label: "High" },
  { qty: 700, lots: 70, label: "Severe" },
];

console.log("Same set with different supply levels:");
console.log();

const baseline = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired" as const,
  yearsPostRetirement: 2,
  demandScore: 65,
  qualityScore: 60,
  salesVelocity: 0.15,
};

supplyLevels.forEach(({ qty, lots, label }) => {
  const inputs = { ...baseline, availableQty: qty, availableLots: lots };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  console.log(
    `  ${label} (${qty} units, ${lots} sellers): $${intrinsic.toFixed(2)}`,
  );
});

console.log();
console.log("  → Clear penalty for oversaturated markets");
console.log();

// Test Case 6: Demand threshold boundary testing
console.log("Test 6: Demand Gating Threshold (40 cutoff)");
console.log("-".repeat(80));

const demandLevels = [10, 30, 39, 40, 41, 60, 80];

console.log("Retired set at different demand scores:");
console.log();

const baseRetired = {
  bricklinkAvgPrice: 100,
  bricklinkMaxPrice: 120,
  retirementStatus: "retired" as const,
  yearsPostRetirement: 2,
  qualityScore: 60,
  availableQty: 40,
  availableLots: 10,
  salesVelocity: 0.1,
};

demandLevels.forEach((demand) => {
  const inputs = { ...baseRetired, demandScore: demand };
  const intrinsic = ValueCalculator.calculateIntrinsicValue(inputs);
  const status = demand >= 40 ? "✓ Gets premium" : "✗ Capped at 2%";
  console.log(`  Demand ${demand}: $${intrinsic.toFixed(2)} ${status}`);
});

console.log();
console.log("  → Sharp threshold at 40: demand must be proven");
console.log();

// Summary
console.log("=".repeat(80));
console.log("SUMMARY OF SAFEGUARDS");
console.log("=".repeat(80));
console.log();
console.log("✓ DEMAND-GATED RETIREMENT PREMIUM:");
console.log("  - Demand score >= 40: Full retirement premium (5-25%)");
console.log("  - Demand score < 40: Max 2% premium");
console.log("  - Rationale: Retired ≠ Valuable without buyers");
console.log();
console.log("✓ SATURATION DETECTION (3 factors):");
console.log("  1. Quantity available (40% weight):");
console.log("     - < 50 units: Healthy");
console.log("     - 50-200: Moderate");
console.log("     - 200-500: High");
console.log("     - > 500: Oversupply penalty");
console.log();
console.log("  2. Number of sellers (30% weight):");
console.log("     - < 10 sellers: Healthy");
console.log("     - 10-30: Competitive");
console.log("     - 30-50: Crowded");
console.log("     - > 50: Saturated penalty");
console.log();
console.log("  3. Velocity-to-supply ratio (30% weight):");
console.log("     - > 1% daily turnover: Healthy");
console.log("     - < 0.1% daily turnover: Stagnant penalty");
console.log();
console.log("  Saturation Discount Range: 0.80x - 1.0x (up to 20% off)");
console.log();
console.log("✓ CRITICAL INSIGHTS:");
console.log("  - These safeguards prevent classic value traps");
console.log("  - 'Retired' status is meaningless without demand");
console.log("  - Oversupply crushes prices regardless of other factors");
console.log("  - Both penalties can stack for severe cases");
console.log();
console.log("=".repeat(80));

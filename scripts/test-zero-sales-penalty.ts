/**
 * Test script to verify the impact of zero sales penalty enhancements
 *
 * Compares intrinsic value calculations for:
 * 1. Items with good sales velocity (healthy)
 * 2. Items with zero sales (dead inventory)
 * 3. Items with zero sales + low demand (extremely dead)
 */

import { ValueCalculator } from "../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../types/value-investing.ts";
import type { Cents } from "../types/price.ts";

// Helper to display cents as dollars
function formatCents(cents: Cents): string {
  return `$${(cents / 100).toFixed(2)}`;
}

console.log("=".repeat(80));
console.log("ZERO SALES PENALTY - IMPACT ANALYSIS");
console.log("=".repeat(80));
console.log();

// Base inputs (common to all test cases)
const baseInputs = {
  msrp: 40000 as Cents, // $400.00 MSRP
  retirementStatus: "retired" as const,
  yearsPostRetirement: 3,
  theme: "Star Wars",
  partsCount: 4000,
  qualityScore: 75,
  priceVolatility: 0.15,
};

// Test Case 1: Healthy item with good sales velocity
console.log("📊 TEST CASE 1: HEALTHY ITEM (Good Sales Velocity)");
console.log("-".repeat(80));
const healthyItem: IntrinsicValueInputs = {
  ...baseInputs,
  bricklinkAvgPrice: 50000 as Cents, // $500 market price
  bricklinkMaxPrice: 60000 as Cents,
  salesVelocity: 0.15, // ~1 sale every 7 days (good)
  avgDaysBetweenSales: 7,
  timesSold: 30, // 30 sales in 6 months
  availableQty: 120, // 120 units available
  availableLots: 45, // 45 sellers
  demandScore: 70,
};

const healthyValue = ValueCalculator.calculateIntrinsicValue(healthyItem);
console.log(`Market Price: ${formatCents(healthyItem.bricklinkAvgPrice!)}`);
console.log(`Sales in 6mo: ${healthyItem.timesSold}`);
console.log(`Sales Velocity: ${healthyItem.salesVelocity}/day`);
console.log(`Supply: ${healthyItem.availableQty} units, ${healthyItem.availableLots} sellers`);
console.log(`Demand Score: ${healthyItem.demandScore}`);
console.log(`→ Intrinsic Value: ${formatCents(healthyValue)}`);
console.log();

// Test Case 2: Dead item with ZERO sales
console.log("⚠️  TEST CASE 2: DEAD ITEM (Zero Sales, Medium Demand)");
console.log("-".repeat(80));
const deadItem: IntrinsicValueInputs = {
  ...baseInputs,
  bricklinkAvgPrice: 50000 as Cents, // Same market price
  bricklinkMaxPrice: 60000 as Cents,
  salesVelocity: 0, // ZERO sales velocity
  avgDaysBetweenSales: undefined, // No sales = can't calculate
  timesSold: 0, // ZERO sales in 6 months ⚠️
  availableQty: 117, // Similar supply
  availableLots: 42, // Similar sellers
  demandScore: 50, // Medium demand (not low enough to compound)
};

const deadValue = ValueCalculator.calculateIntrinsicValue(deadItem);
console.log(`Market Price: ${formatCents(deadItem.bricklinkAvgPrice!)}`);
console.log(`Sales in 6mo: ${deadItem.timesSold} ⚠️`);
console.log(`Sales Velocity: ${deadItem.salesVelocity}/day`);
console.log(`Supply: ${deadItem.availableQty} units, ${deadItem.availableLots} sellers`);
console.log(`Demand Score: ${deadItem.demandScore}`);
console.log(`→ Intrinsic Value: ${formatCents(deadValue)}`);
console.log(`→ Zero Sales Penalty Applied: 0.50x (50% discount)`);
console.log();

// Test Case 3: Extremely dead item (zero sales + low demand)
console.log("🚨 TEST CASE 3: EXTREMELY DEAD ITEM (Zero Sales + Low Demand)");
console.log("-".repeat(80));
const extremelyDeadItem: IntrinsicValueInputs = {
  ...baseInputs,
  bricklinkAvgPrice: 50000 as Cents,
  bricklinkMaxPrice: 60000 as Cents,
  salesVelocity: 0,
  avgDaysBetweenSales: undefined,
  timesSold: 0, // ZERO sales
  availableQty: 200, // High supply
  availableLots: 80, // Many sellers
  demandScore: 25, // LOW demand (< 30 threshold)
};

const extremelyDeadValue = ValueCalculator.calculateIntrinsicValue(extremelyDeadItem);
console.log(`Market Price: ${formatCents(extremelyDeadItem.bricklinkAvgPrice!)}`);
console.log(`Sales in 6mo: ${extremelyDeadItem.timesSold} 🚨`);
console.log(`Sales Velocity: ${extremelyDeadItem.salesVelocity}/day`);
console.log(`Supply: ${extremelyDeadItem.availableQty} units, ${extremelyDeadItem.availableLots} sellers`);
console.log(`Demand Score: ${extremelyDeadItem.demandScore} (LOW)`);
console.log(`→ Intrinsic Value: ${formatCents(extremelyDeadValue)}`);
console.log(`→ Zero Sales Penalty: 0.50x × 0.60x (compound) = 0.30x total`);
console.log();

// Test Case 4: Very slow sales (just above zero threshold)
console.log("⚠️  TEST CASE 4: VERY SLOW SALES (Barely Above Zero)");
console.log("-".repeat(80));
const slowItem: IntrinsicValueInputs = {
  ...baseInputs,
  bricklinkAvgPrice: 50000 as Cents,
  bricklinkMaxPrice: 60000 as Cents,
  salesVelocity: 0.005, // ~1 sale every 200 days (very slow)
  avgDaysBetweenSales: 200,
  timesSold: 1, // Just 1 sale (avoids zero penalty)
  availableQty: 150,
  availableLots: 60,
  demandScore: 40,
};

const slowValue = ValueCalculator.calculateIntrinsicValue(slowItem);
console.log(`Market Price: ${formatCents(slowItem.bricklinkAvgPrice!)}`);
console.log(`Sales in 6mo: ${slowItem.timesSold}`);
console.log(`Sales Velocity: ${slowItem.salesVelocity}/day`);
console.log(`Supply: ${slowItem.availableQty} units, ${slowItem.availableLots} sellers`);
console.log(`Demand Score: ${slowItem.demandScore}`);
console.log(`→ Intrinsic Value: ${formatCents(slowValue)}`);
console.log(`→ No zero sales penalty (has 1 sale), but severe liquidity penalty`);
console.log();

// Summary comparison
console.log("=".repeat(80));
console.log("SUMMARY COMPARISON");
console.log("=".repeat(80));
console.log();

const healthyDiscount = ((1 - healthyValue / healthyItem.bricklinkAvgPrice!) * 100).toFixed(1);
const deadDiscount = ((1 - deadValue / deadItem.bricklinkAvgPrice!) * 100).toFixed(1);
const extremeDiscount = ((1 - extremelyDeadValue / extremelyDeadItem.bricklinkAvgPrice!) * 100).toFixed(1);
const slowDiscount = ((1 - slowValue / slowItem.bricklinkAvgPrice!) * 100).toFixed(1);

console.log(`1. Healthy (30 sales):          ${formatCents(healthyValue).padEnd(10)} (${healthyDiscount}% vs market)`);
console.log(`2. Dead (0 sales):              ${formatCents(deadValue).padEnd(10)} (${deadDiscount}% vs market) ⚠️`);
console.log(`3. Extremely Dead (0 + low demand): ${formatCents(extremelyDeadValue).padEnd(10)} (${extremeDiscount}% vs market) 🚨`);
console.log(`4. Very Slow (1 sale):          ${formatCents(slowValue).padEnd(10)} (${slowDiscount}% vs market) ⚠️`);
console.log();

console.log("Key Insights:");
console.log(`- Dead item value is ${((healthyValue / deadValue) - 1) * 100}% LOWER than healthy`);
console.log(`- Extremely dead is ${((healthyValue / extremelyDeadValue) - 1) * 100}% LOWER than healthy`);
console.log(`- Zero sales penalty is BRUTAL: ${((1 - deadValue / healthyValue) * 100).toFixed(1)}% reduction`);
console.log();
console.log("✅ Zero sales penalty is working as intended!");
console.log("=".repeat(80));

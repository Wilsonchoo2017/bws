/**
 * Analyze actual BrickLink data to show impact of zero sales penalty
 * Uses real data from the database
 */

import { closeDb, db } from "../db/client.ts";
import { bricklinkVolumeHistory } from "../db/schema.ts";
import { desc } from "drizzle-orm";

console.log("=".repeat(80));
console.log("ANALYZING REAL BRICKLINK DATA - Zero Sales Impact");
console.log("=".repeat(80));
console.log();

// Query for items with zero sales vs items with good sales
// Get latest records for each item
const volumeData = await db
  .select()
  .from(bricklinkVolumeHistory)
  .orderBy(desc(bricklinkVolumeHistory.recorded_at))
  .limit(100)
  .then((rows) =>
    rows.filter((row) =>
      row.condition === "new" && row.time_period === "six_month"
    )
  );

// Separate into categories
const zeroSales = volumeData.filter((item) =>
  (item.times_sold ?? 0) === 0 && (item.total_qty ?? 0) > 0
);
const lowSales = volumeData.filter((item) =>
  (item.times_sold ?? 0) > 0 && (item.times_sold ?? 0) <= 5
);
const goodSales = volumeData.filter((item) => (item.times_sold ?? 0) > 10);

console.log("📊 DATASET SUMMARY");
console.log("-".repeat(80));
console.log(`Total items analyzed: ${volumeData.length}`);
console.log(
  `Items with ZERO sales: ${zeroSales.length} (${
    ((zeroSales.length / volumeData.length) * 100).toFixed(1)
  }%)`,
);
console.log(
  `Items with 1-5 sales: ${lowSales.length} (${
    ((lowSales.length / volumeData.length) * 100).toFixed(1)
  }%)`,
);
console.log(
  `Items with 10+ sales: ${goodSales.length} (${
    ((goodSales.length / volumeData.length) * 100).toFixed(1)
  }%)`,
);
console.log();

if (zeroSales.length > 0) {
  console.log("🚨 ZERO SALES ITEMS (Dead Inventory)");
  console.log("-".repeat(80));
  console.log(
    "Item ID       | Supply | Sellers | Avg Price | Times Sold | Penalty",
  );
  console.log("-".repeat(80));

  zeroSales.slice(0, 10).forEach((item) => {
    const supply = item.total_qty ?? 0;
    const sellers = item.total_lots ?? 0;
    const price = item.avg_price
      ? `$${(item.avg_price / 100).toFixed(2)}`
      : "N/A";
    const timesSold = item.times_sold ?? 0;

    console.log(
      `${item.item_id.padEnd(13)} | ${String(supply).padEnd(6)} | ${
        String(sellers).padEnd(7)
      } | ${price.padEnd(9)} | ${String(timesSold).padEnd(10)} | 0.50x (50%)`,
    );
  });
  console.log();

  const avgZeroSupply = zeroSales.reduce((sum, item) =>
    sum + (item.total_qty ?? 0), 0) / zeroSales.length;
  const avgZeroSellers = zeroSales.reduce((sum, item) =>
    sum + (item.total_lots ?? 0), 0) / zeroSales.length;

  console.log(
    `Average supply for zero-sales items: ${avgZeroSupply.toFixed(0)} units`,
  );
  console.log(
    `Average sellers for zero-sales items: ${
      avgZeroSellers.toFixed(0)
    } sellers`,
  );
  console.log();
}

if (goodSales.length > 0) {
  console.log("✅ GOOD SALES ITEMS (Healthy Inventory)");
  console.log("-".repeat(80));
  console.log(
    "Item ID       | Supply | Sellers | Avg Price | Times Sold | Velocity",
  );
  console.log("-".repeat(80));

  goodSales.slice(0, 10).forEach((item) => {
    const supply = item.total_qty ?? 0;
    const sellers = item.total_lots ?? 0;
    const price = item.avg_price
      ? `$${(item.avg_price / 100).toFixed(2)}`
      : "N/A";
    const timesSold = item.times_sold ?? 0;
    const velocity = (timesSold / 180).toFixed(3); // 6 months ≈ 180 days

    console.log(
      `${item.item_id.padEnd(13)} | ${String(supply).padEnd(6)} | ${
        String(sellers).padEnd(7)
      } | ${price.padEnd(9)} | ${
        String(timesSold).padEnd(10)
      } | ${velocity}/day`,
    );
  });
  console.log();

  const avgGoodSupply = goodSales.reduce((sum, item) =>
    sum + (item.total_qty ?? 0), 0) / goodSales.length;
  const avgGoodSellers = goodSales.reduce((sum, item) =>
    sum + (item.total_lots ?? 0), 0) / goodSales.length;
  const avgGoodSales = goodSales.reduce((sum, item) =>
    sum + (item.times_sold ?? 0), 0) / goodSales.length;

  console.log(
    `Average supply for good-sales items: ${avgGoodSupply.toFixed(0)} units`,
  );
  console.log(
    `Average sellers for good-sales items: ${
      avgGoodSellers.toFixed(0)
    } sellers`,
  );
  console.log(
    `Average sales in 6 months: ${avgGoodSales.toFixed(1)} transactions`,
  );
  console.log();
}

console.log("=".repeat(80));
console.log("KEY FINDINGS");
console.log("=".repeat(80));
console.log();

if (zeroSales.length > 0 && goodSales.length > 0) {
  const avgZeroSupply = zeroSales.reduce((sum, item) =>
    sum + (item.total_qty ?? 0), 0) / zeroSales.length;
  const avgGoodSupply = goodSales.reduce((sum, item) =>
    sum + (item.total_qty ?? 0), 0) / goodSales.length;

  console.log("1. Zero-sales items typically have:");
  console.log(
    `   - ${((avgZeroSupply / avgGoodSupply - 1) * 100).toFixed(0)}% ${
      avgZeroSupply > avgGoodSupply ? "MORE" : "LESS"
    } supply than healthy items`,
  );
  console.log("   - Effectively DEAD inventory sitting unsold");
  console.log();

  console.log("2. Impact of new penalty system:");
  console.log(`   - Zero sales items: 50% base penalty (0.50x multiplier)`);
  console.log(
    `   - If demand score < 30: Additional 40% penalty (0.60x × 0.50x = 0.30x total)`,
  );
  console.log(
    `   - Combined with saturation discount: Up to 85% total reduction possible`,
  );
  console.log();

  console.log("3. This prevents:");
  console.log("   - Overvaluing dead inventory nobody wants");
  console.log("   - Buying into oversaturated markets");
  console.log("   - False confidence in items with no proven demand");
}

console.log();
console.log("✅ Analysis complete!");
console.log("=".repeat(80));

// Close database connection
await closeDb();

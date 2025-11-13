/**
 * Test script to fetch and analyze WorldBricks.com HTML structure
 *
 * This script helps identify CSS selectors for extracting:
 * - Set number
 * - Set name
 * - Description
 * - Year released (HIGH PRIORITY)
 * - Year retired (HIGH PRIORITY)
 * - Designer/Creator
 * - Parts count
 * - Dimensions
 * - Image URL
 */

import { getHttpClient, closeHttpClient } from "../services/http/HttpClientService.ts";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.38/deno-dom-wasm.ts";

const TEST_URL = "https://www.worldbricks.com/en/instructions-number/30000/31000-31099/lego-set/31009-Small-Cottage.html";
const OUTPUT_FILE = "./scripts/worldbricks-sample.html";

async function testWorldBricksFetch() {
  const httpClient = getHttpClient();

  try {
    console.log("🚀 Starting WorldBricks fetch test...\n");

    // Initialize the HTTP client
    await httpClient.initialize();

    // Fetch the test page
    console.log(`📥 Fetching: ${TEST_URL}\n`);
    const response = await httpClient.fetch({
      url: TEST_URL,
      timeout: 30000,
    });

    console.log(`✅ Status: ${response.status}`);
    console.log(`📄 HTML Length: ${response.html.length} characters\n`);

    // Save HTML to file for manual inspection
    await Deno.writeTextFile(OUTPUT_FILE, response.html);
    console.log(`💾 Saved HTML to: ${OUTPUT_FILE}\n`);

    // Parse HTML and try to extract data
    console.log("🔍 Analyzing HTML structure...\n");
    analyzeHTML(response.html);

  } catch (error) {
    console.error("❌ Error:", error);
  } finally {
    // Clean up
    await closeHttpClient();
    console.log("\n✅ Test completed!");
  }
}

function analyzeHTML(html: string) {
  const doc = new DOMParser().parseFromString(html, "text/html");

  if (!doc) {
    console.error("Failed to parse HTML");
    return;
  }

  console.log("=".repeat(60));
  console.log("HTML STRUCTURE ANALYSIS");
  console.log("=".repeat(60));

  // Try to extract meta tags
  console.log("\n📋 META TAGS:");
  const metaTags = {
    title: doc.querySelector('meta[property="og:title"]')?.getAttribute("content"),
    description: doc.querySelector('meta[name="description"]')?.getAttribute("content"),
    image: doc.querySelector('meta[property="og:image:secure_url"]')?.getAttribute("content"),
  };
  console.log(JSON.stringify(metaTags, null, 2));

  // Try to find the page title
  console.log("\n📄 PAGE TITLE:");
  const title = doc.querySelector("title")?.textContent;
  console.log(`  ${title}`);

  // Look for common LEGO data containers
  console.log("\n🔍 SEARCHING FOR DATA FIELDS:");

  // Search for year patterns in the HTML
  const yearMatches = html.match(/\b(19\d{2}|20\d{2})\b/g);
  if (yearMatches) {
    console.log(`  Years found in HTML: ${[...new Set(yearMatches)].join(", ")}`);
  }

  // Search for "parts" or "pieces"
  const partsMatches = html.match(/(\d+)\s*(parts|pieces|pcs)/gi);
  if (partsMatches) {
    console.log(`  Parts mentions: ${partsMatches.slice(0, 5).join(", ")}`);
  }

  // Search for designer/creator
  const designerMatches = html.match(/(designer|creator|designed by|created by)[:;\s]+([^\n<]+)/gi);
  if (designerMatches) {
    console.log(`  Designer mentions: ${designerMatches.slice(0, 3).join(", ")}`);
  }

  // Look for common table structures
  console.log("\n📊 TABLES FOUND:");
  const tables = doc.querySelectorAll("table");
  console.log(`  Total tables: ${tables.length}`);

  tables.forEach((table, index) => {
    const rows = table.querySelectorAll("tr");
    if (rows.length > 0 && rows.length < 20) { // Focus on smaller, data tables
      console.log(`\n  Table ${index + 1} (${rows.length} rows):`);
      rows.forEach((row, rowIndex) => {
        const cells = row.querySelectorAll("td, th");
        if (cells.length > 0 && rowIndex < 10) {
          const cellText = Array.from(cells).map(cell =>
            cell.textContent?.trim().substring(0, 50)
          ).join(" | ");
          console.log(`    Row ${rowIndex + 1}: ${cellText}`);
        }
      });
    }
  });

  // Look for divs with product information
  console.log("\n📦 PRODUCT INFO DIVS:");
  const productDivs = doc.querySelectorAll(".djc_item, .product, [class*='detail'], [class*='info']");
  console.log(`  Found ${productDivs.length} potential product containers`);

  // Look for specific class patterns
  console.log("\n🎨 INTERESTING CLASSES:");
  const allElements = doc.querySelectorAll("[class*='djc'], [class*='item'], [class*='product']");
  const classes = new Set<string>();
  allElements.forEach(el => {
    const classList = el.getAttribute("class")?.split(" ") || [];
    classList.forEach(cls => {
      if (cls && (cls.includes("djc") || cls.includes("item") || cls.includes("product"))) {
        classes.add(cls);
      }
    });
  });
  console.log(`  ${Array.from(classes).slice(0, 20).join(", ")}`);

  // Look for JSON-LD structured data
  console.log("\n🏷️  JSON-LD STRUCTURED DATA:");
  const jsonLdScripts = doc.querySelectorAll('script[type="application/ld+json"]');
  console.log(`  Found ${jsonLdScripts.length} JSON-LD blocks`);
  jsonLdScripts.forEach((script, index) => {
    try {
      const data = JSON.parse(script.textContent || "{}");
      console.log(`  Block ${index + 1}:`, JSON.stringify(data, null, 2).substring(0, 200));
    } catch {
      console.log(`  Block ${index + 1}: Failed to parse`);
    }
  });

  console.log("\n" + "=".repeat(60));
  console.log("💡 NEXT STEPS:");
  console.log("  1. Inspect the saved HTML file for visual context");
  console.log("  2. Identify exact CSS selectors for each field");
  console.log("  3. Implement parsing logic in WorldBricksParser.ts");
  console.log("=".repeat(60));
}

// Run the test
if (import.meta.main) {
  testWorldBricksFetch();
}

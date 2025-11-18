/**
 * Script to manually add Shopee LEGO set from the sample HTML file
 *
 * Usage: deno run --allow-read --allow-net --allow-env scripts/add-shopee-sample.ts
 */

import { parseArgs } from "jsr:@std/cli/parse-args";

const SAMPLE_FILE_PATH = "./sample/shopee-element example.txt";
const API_BASE_URL = "http://localhost:8000";

async function main() {
  const args = parseArgs(Deno.args, {
    string: ["lego-set", "shop-url"],
    alias: {
      l: "lego-set",
      u: "shop-url",
    },
  });

  // Read the sample HTML file
  console.log(`Reading sample file: ${SAMPLE_FILE_PATH}`);
  const htmlContent = await Deno.readTextFile(SAMPLE_FILE_PATH);

  if (!htmlContent) {
    console.error("❌ Sample file is empty");
    Deno.exit(1);
  }

  console.log(`✓ Loaded ${htmlContent.length} characters from sample file`);

  // Determine the shop URL
  // Default to a generic Shopee Malaysia shop URL if not provided
  const shopUrl = args["shop-url"] ||
    "https://shopee.com.my/legoshopmy?shopCollection=";

  console.log(`Using shop URL: ${shopUrl}`);

  // Parse the Shopee HTML
  console.log("\nSending to parse-shopee API...");
  const parseResponse = await fetch(`${API_BASE_URL}/api/parse-shopee`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      html: htmlContent,
      source_url: shopUrl,
    }),
  });

  const parseResult = await parseResponse.json();

  if (!parseResponse.ok) {
    console.error("❌ Parse failed:", parseResult);
    Deno.exit(1);
  }

  console.log("\n✓ Parse result:");
  console.log(JSON.stringify(parseResult, null, 2));

  // Check if validation is required
  if (parseResult.requiresValidation) {
    console.log("\n⚠️  Products need LEGO set number validation:");

    for (const product of parseResult.productsNeedingValidation) {
      console.log(`\nProduct: ${product.productName}`);
      console.log(`Price: ${product.priceString}`);
      console.log(`Units Sold: ${product.unitsSoldString}`);
      console.log(`URL: ${product.productUrl}`);

      if (args["lego-set"]) {
        console.log(`\nUsing LEGO set number from argument: ${args["lego-set"]}`);

        // TODO: Add API endpoint to save product with manual LEGO set number
        console.log("\n⚠️  Note: Manual LEGO set number assignment not yet implemented");
        console.log("You can add the product manually by:");
        console.log("1. Inserting into the 'products' table with the LEGO set number");
        console.log("2. Or updating the existing product if it was saved");
      } else {
        console.log("\n💡 To assign a LEGO set number, run:");
        console.log(`   deno run --allow-read --allow-net --allow-env scripts/add-shopee-sample.ts --lego-set 77243`);
      }
    }
  } else {
    console.log("\n✅ All products saved successfully!");
    console.log(`Session ID: ${parseResult.session_id}`);
    console.log(`Products stored: ${parseResult.products_stored}/${parseResult.products_found}`);
  }
}

// Run the script
if (import.meta.main) {
  main().catch((error) => {
    console.error("❌ Error:", error);
    Deno.exit(1);
  });
}

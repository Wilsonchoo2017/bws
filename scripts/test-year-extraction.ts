#!/usr/bin/env -S deno run --allow-all
/**
 * Test year extraction from existing BrickLink raw HTML in database
 */

import { gunzip } from "https://deno.land/x/compress@v0.4.5/gzip/gzip.ts";
import { extractYearReleased } from "../services/bricklink/BricklinkParser.ts";
import { closeDb, db } from "../db/client.ts";
import { scrapeRawData } from "../db/schema.ts";
import { eq } from "drizzle-orm";

async function main() {
  console.log("🧪 Testing Year Extraction from BrickLink Raw HTML\n");

  try {
    // Get a sample raw HTML from database
    const samples = await db
      .select()
      .from(scrapeRawData)
      .where(eq(scrapeRawData.source, "bricklink"))
      .limit(5);

    console.log(`Found ${samples.length} BrickLink raw HTML samples\n`);

    for (const sample of samples) {
      console.log(`\n${"=".repeat(80)}`);
      console.log(`Testing: ${sample.sourceUrl}`);
      console.log(`${"=".repeat(80)}`);

      try {
        // Decompress HTML
        const compressedData = sample.rawHtmlCompressed;
        const decoded = Uint8Array.from(
          atob(compressedData),
          (c) => c.charCodeAt(0),
        );
        const decompressed = gunzip(decoded);
        const html = new TextDecoder().decode(decompressed);

        console.log(`HTML size: ${html.length} bytes`);

        // Extract year
        const yearReleased = extractYearReleased(html);

        if (yearReleased) {
          console.log(`✅ Year Released: ${yearReleased}`);
        } else {
          console.log("❌ Could not extract year");
        }

        // Show the actual pattern found
        const yearMatch = html.match(/Year Released:.*?(\d{4})/i);
        if (yearMatch) {
          console.log(`Pattern found: ${yearMatch[0]}`);
        } else {
          console.log("Pattern not found in HTML");
        }
      } catch (error) {
        console.error(`❌ Error processing sample: ${error.message}`);
      }
    }

    console.log(`\n${"=".repeat(80)}`);
    console.log("✅ Test complete!");
  } catch (error) {
    console.error("❌ Test failed:", error);
    Deno.exit(1);
  } finally {
    await closeDb();
  }
}

main();

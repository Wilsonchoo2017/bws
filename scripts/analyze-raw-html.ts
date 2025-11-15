#!/usr/bin/env -S deno run --allow-read --allow-write --allow-env --allow-net

import { Client } from "https://deno.land/x/postgres@v0.17.0/mod.ts";
import { load } from "https://deno.land/std@0.208.0/dotenv/mod.ts";
import { decode as base64Decode } from "https://deno.land/std@0.208.0/encoding/base64.ts";
import { gunzip } from "https://deno.land/x/denoflate@1.2.1/mod.ts";

// Load environment variables
await load({ export: true, allowEmptyValues: true });

const DATABASE_URL = Deno.env.get("DATABASE_URL");

if (!DATABASE_URL) {
  console.error("Missing DATABASE_URL environment variable");
  Deno.exit(1);
}

// Create PostgreSQL client
const client = new Client(DATABASE_URL);
await client.connect();

async function decompressHtml(compressedBase64: string): Promise<string> {
  try {
    // Decode base64
    const compressed = base64Decode(compressedBase64);

    // Decompress gzip
    const decompressed = gunzip(compressed);

    // Convert to string
    const decoder = new TextDecoder();
    return decoder.decode(decompressed);
  } catch (error) {
    console.error("Error decompressing HTML:", error);
    throw error;
  }
}

function findTables(html: string): Array<{ index: number; preview: string; hasPrice: boolean; hasSales: boolean }> {
  const tables: Array<{ index: number; preview: string; hasPrice: boolean; hasSales: boolean }> = [];
  const tableRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
  let match;
  let index = 0;

  while ((match = tableRegex.exec(html)) !== null) {
    const tableContent = match[1];
    const preview = match[0].substring(0, 500);

    // Check for indicators of sales data
    const hasPrice = /price|cost|\$|USD/i.test(tableContent);
    const hasSales = /sold|sale|transaction|date|qty|quantity/i.test(tableContent);

    tables.push({
      index: index++,
      preview,
      hasPrice,
      hasSales,
    });
  }

  return tables;
}

function extractSalesTableStructure(html: string, tableIndex: number): string | null {
  const tableRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
  let match;
  let index = 0;

  while ((match = tableRegex.exec(html)) !== null) {
    if (index === tableIndex) {
      // Extract up to 2000 characters of the table
      return match[0].substring(0, 2000);
    }
    index++;
  }

  return null;
}

async function main() {
  console.log("Querying database for session 27 raw HTML...\n");

  const result = await client.queryObject<{
    id: number;
    source_url: string;
    raw_html_compressed: string;
  }>(
    `SELECT id, source_url, raw_html_compressed
     FROM scrape_raw_data
     WHERE scrape_session_id = 27
     AND source = 'bricklink'
     ORDER BY scraped_at`
  );

  if (result.rows.length === 0) {
    console.log("No data found for session 27");
    await client.end();
    Deno.exit(0);
  }

  console.log(`Found ${result.rows.length} records\n`);

  const data = result.rows;

  for (const record of data) {
    console.log(`\n${"=".repeat(80)}`);
    console.log(`Record ID: ${record.id}`);
    console.log(`Source URL: ${record.source_url}`);
    console.log("=".repeat(80));

    // Decompress HTML
    const html = await decompressHtml(record.raw_html_compressed);
    console.log(`Decompressed HTML size: ${html.length} characters`);

    // Save to temporary file
    const filename = `/tmp/bricklink_${record.id}.html`;
    await Deno.writeTextFile(filename, html);
    console.log(`Saved to: ${filename}`);

    // Find all tables
    const tables = findTables(html);
    console.log(`\nFound ${tables.length} tables in HTML`);

    // Analyze each table
    for (const table of tables) {
      console.log(`\nTable ${table.index}:`);
      console.log(`  - Has price indicators: ${table.hasPrice}`);
      console.log(`  - Has sales indicators: ${table.hasSales}`);

      if (table.hasPrice && table.hasSales) {
        console.log(`  *** Likely candidate for sales data ***`);

        // Extract and display structure
        const structure = extractSalesTableStructure(html, table.index);
        if (structure) {
          const structureFile = `/tmp/bricklink_${record.id}_table_${table.index}.html`;
          await Deno.writeTextFile(structureFile, structure);
          console.log(`  Saved table structure to: ${structureFile}`);

          // Show first 500 chars
          console.log(`\n  Preview:`);
          console.log(`  ${"-".repeat(76)}`);
          console.log(structure.substring(0, 500));
          console.log(`  ${"-".repeat(76)}`);
        }
      }
    }

    // Search for specific patterns that might indicate sales data
    console.log("\n\nSearching for sales data patterns:");

    const patterns = [
      { name: "Past Sales link/section", regex: /past\s+sales|sold\s+listings|sales\s+history/i },
      { name: "Price column headers", regex: /<th[^>]*>.*?(price|cost|total).*?<\/th>/i },
      { name: "Date column headers", regex: /<th[^>]*>.*?(date|when|time).*?<\/th>/i },
      { name: "Quantity column headers", regex: /<th[^>]*>.*?(qty|quantity|amount).*?<\/th>/i },
      { name: "Table with 'soldDetail' class", regex: /<table[^>]*soldDetail[^>]*>/i },
      { name: "Table with 'pcipgSoldItems' id", regex: /<table[^>]*id=['"]*pcipgSoldItems[^>]*>/i },
    ];

    for (const pattern of patterns) {
      const match = pattern.regex.exec(html);
      if (match) {
        console.log(`  ✓ Found: ${pattern.name}`);
        console.log(`    Match: ${match[0]}`);

        // Get context around the match
        const start = Math.max(0, match.index - 200);
        const end = Math.min(html.length, match.index + 500);
        const context = html.substring(start, end);

        const contextFile = `/tmp/bricklink_${record.id}_${pattern.name.replace(/\s+/g, "_")}.html`;
        await Deno.writeTextFile(contextFile, context);
        console.log(`    Context saved to: ${contextFile}`);
      } else {
        console.log(`  ✗ Not found: ${pattern.name}`);
      }
    }
  }

  console.log("\n\nAnalysis complete!");

  // Cleanup
  await client.end();
}

main().catch((error) => {
  console.error("Fatal error:", error);
  client.end();
  Deno.exit(1);
});

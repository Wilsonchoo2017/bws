/**
 * Analysis Demo Page
 * Demonstrates the product analysis system
 */

import { Handlers, PageProps } from "$fresh/server.ts";
import { db } from "../db/client.ts";
import { products } from "../db/schema.ts";
import IntrinsicValueCard from "../islands/IntrinsicValueCard.tsx";

interface AnalysisDemoData {
  sampleProducts: Array<{
    productId: string;
    name: string | null;
    source: string;
  }>;
}

export const handler: Handlers<AnalysisDemoData> = {
  async GET(_req, ctx) {
    const { isNotNull } = await import("drizzle-orm");

    // Fetch some sample products with LEGO set numbers
    const sampleProducts = await db
      .select({
        productId: products.productId,
        name: products.name,
        source: products.source,
      })
      .from(products)
      .where(isNotNull(products.legoSetNumber))
      .limit(10);

    return ctx.render({ sampleProducts });
  },
};

export default function AnalysisDemoPage(
  { data }: PageProps<AnalysisDemoData>,
) {
  return (
    <div class="min-h-screen bg-gray-100">
      <div class="container mx-auto px-4 py-8">
        {/* Header */}
        <div class="mb-8">
          <h1 class="text-3xl font-bold text-gray-900 mb-2">
            Value Investing Analysis
          </h1>
          <p class="text-gray-600">
            Intrinsic value-based investment analysis for LEGO products
          </p>
        </div>

        {/* Sample Products List */}
        {data.sampleProducts.length > 0
          ? (
            <div class="space-y-8">
              <div class="bg-white rounded-lg shadow-md p-6">
                <h2 class="text-xl font-semibold mb-4">Sample Products</h2>
                <div class="space-y-2">
                  {data.sampleProducts.map((product) => (
                    <div
                      key={product.productId}
                      class="p-3 border border-gray-200 rounded hover:bg-gray-50"
                    >
                      <a
                        href={`#${product.productId}`}
                        class="text-blue-600 hover:underline font-medium"
                      >
                        {product.name}
                      </a>
                      <span class="text-sm text-gray-500 ml-2">
                        ({product.source})
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Analysis Cards for each product */}
              {data.sampleProducts.slice(0, 3).map((product) => (
                <div key={product.productId} id={product.productId}>
                  <h2 class="text-2xl font-bold text-gray-900 mb-4">
                    {product.name}
                  </h2>
                  <IntrinsicValueCard productId={product.productId} />
                </div>
              ))}
            </div>
          )
          : (
            <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
              <p class="text-yellow-800">
                No products with LEGO set numbers found. Please add some
                products with valid LEGO set numbers to see the analysis.
              </p>
            </div>
          )}

        {/* System Overview */}
        <div class="mt-12 bg-white rounded-lg shadow-md p-6">
          <h2 class="text-xl font-semibold mb-4">Value Investing Principles</h2>
          <div class="space-y-4 text-gray-700">
            <div>
              <h3 class="font-semibold text-lg mb-2">Key Metrics</h3>
              <ul class="list-disc list-inside space-y-1">
                <li>
                  <strong>Intrinsic Value:</strong>{" "}
                  The true worth based on MSRP, retirement status, demand, quality, and market conditions
                </li>
                <li>
                  <strong>Target Price:</strong>{" "}
                  Maximum price to pay with margin of safety built in
                </li>
                <li>
                  <strong>Margin of Safety:</strong>{" "}
                  Discount percentage from intrinsic value
                </li>
                <li>
                  <strong>Expected ROI:</strong>{" "}
                  Theoretical return based on current price vs intrinsic value
                </li>
              </ul>
            </div>

            <div>
              <h3 class="font-semibold text-lg mb-2">Data Sources</h3>
              <ul class="list-disc list-inside space-y-1">
                <li>Shopee/ToysRUs retail pricing and sales metrics</li>
                <li>Bricklink resale pricing and historical trends</li>
                <li>WorldBricks retirement tracking and MSRP data</li>
                <li>Demand and quality analysis</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

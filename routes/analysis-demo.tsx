/**
 * Analysis Demo Page
 * Demonstrates the product analysis system
 */

import { Handlers, PageProps } from "$fresh/server.ts";
import { db } from "../db/client.ts";
import { products } from "../db/schema.ts";
import ProductAnalysisCard from "../islands/ProductAnalysisCard.tsx";

interface AnalysisDemoData {
  sampleProducts: Array<{
    productId: string;
    name: string;
    source: string;
  }>;
}

export const handler: Handlers<AnalysisDemoData> = {
  async GET(_req, ctx) {
    // Fetch some sample products with LEGO set numbers
    const sampleProducts = await db
      .select({
        productId: products.productId,
        name: products.name,
        source: products.source,
      })
      .from(products)
      .where(products.legoSetNumber !== null)
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
            Product Analysis System
          </h1>
          <p class="text-gray-600">
            Investment-focused analysis for LEGO products using
            multi-dimensional scoring
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
                  <ProductAnalysisCard
                    productId={product.productId}
                    defaultStrategy="Investment Focus"
                  />
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
          <h2 class="text-xl font-semibold mb-4">System Overview</h2>
          <div class="space-y-4 text-gray-700">
            <div>
              <h3 class="font-semibold text-lg mb-2">Analysis Dimensions</h3>
              <ul class="list-disc list-inside space-y-1">
                <li>
                  <strong>Pricing:</strong>{" "}
                  Retail vs resale margins, discounts, price trends,
                  appreciation potential
                </li>
                <li>
                  <strong>Demand:</strong>{" "}
                  Sales velocity, Reddit community sentiment, Bricklink resale
                  activity
                </li>
                <li>
                  <strong>Availability:</strong>{" "}
                  Stock levels, retirement timing, scarcity signals
                </li>
                <li>
                  <strong>Quality:</strong>{" "}
                  Product ratings, seller trust signals, brand authenticity
                </li>
              </ul>
            </div>

            <div>
              <h3 class="font-semibold text-lg mb-2">Investment Strategies</h3>
              <ul class="list-disc list-inside space-y-1">
                <li>
                  <strong>Investment Focus:</strong>{" "}
                  Long-term ROI, retirement timing, price appreciation
                </li>
                <li>
                  <strong>Quick Flip:</strong>{" "}
                  Immediate resale potential, high current demand, low stock
                </li>
                <li>
                  <strong>Bargain Hunter:</strong>{" "}
                  Deep discounts, quality products, good value
                </li>
              </ul>
            </div>

            <div>
              <h3 class="font-semibold text-lg mb-2">Data Sources</h3>
              <ul class="list-disc list-inside space-y-1">
                <li>Shopee/ToysRUs retail pricing and sales metrics</li>
                <li>Bricklink resale pricing and historical trends</li>
                <li>BrickRanker retirement tracking</li>
                <li>Reddit community sentiment analysis</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

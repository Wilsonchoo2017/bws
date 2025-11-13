/**
 * Product Detail Page
 * Shows product metadata and comprehensive analysis
 */

import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { desc, eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  type BricklinkItem,
  bricklinkItems,
  priceHistory,
  type Product,
  products,
  shopeeScrapes,
  type WorldbricksSet,
} from "../../db/schema.ts";
import { getBricklinkRepository } from "../../services/bricklink/BricklinkRepository.ts";
import { getWorldBricksRepository } from "../../services/worldbricks/WorldBricksRepository.ts";
import ProductAnalysisCard from "../../islands/ProductAnalysisCard.tsx";
import ProductEditModal from "../../islands/ProductEditModal.tsx";
import ProductImageGallery from "../../islands/ProductImageGallery.tsx";
import PricingOverview from "../../islands/PricingOverview.tsx";

interface ShopeeScrape {
  id: number;
  price: number | null;
  currency: string | null;
  unitsSold: number | null;
  shopId: number | null;
  shopName: string | null;
  productUrl: string | null;
  scrapedAt: Date;
}

interface PriceHistoryRecord {
  id: number;
  price: number | null;
  priceBeforeDiscount: number | null;
  unitsSoldSnapshot: number | null;
  recordedAt: Date;
}

interface PriceData {
  amount: number;
  currency: string;
}

interface PricingBox {
  avg_price?: PriceData;
  min_price?: PriceData;
  max_price?: PriceData;
  qty_avg_price?: PriceData;
  total_qty?: number;
  total_lots?: number;
  times_sold?: number;
}

interface ProductDetailData {
  product: Product;
  shopeeScrapes: ShopeeScrape[];
  priceHistory: PriceHistoryRecord[];
  bricklinkItem: BricklinkItem | undefined;
  worldbricksSet: WorldbricksSet | undefined;
}

export const handler: Handlers<ProductDetailData | null> = {
  async GET(_req, ctx) {
    const { id } = ctx.params;

    // Fetch product by productId
    const result = await db
      .select()
      .from(products)
      .where(eq(products.productId, id))
      .limit(1);

    if (result.length === 0) {
      return ctx.renderNotFound();
    }

    const product = result[0];

    // Fetch historical data for Shopee products
    let shopeeScrapesData: ShopeeScrape[] = [];
    if (product.source === "shopee") {
      shopeeScrapesData = await db
        .select()
        .from(shopeeScrapes)
        .where(eq(shopeeScrapes.productId, product.productId))
        .orderBy(desc(shopeeScrapes.scrapedAt))
        .limit(50);
    }

    // Fetch price history (legacy table for all sources)
    const priceHistoryData = await db
      .select()
      .from(priceHistory)
      .where(eq(priceHistory.productId, product.productId))
      .orderBy(desc(priceHistory.recordedAt))
      .limit(50);

    // Fetch Bricklink data if product has LEGO set number
    let bricklinkData: BricklinkItem | undefined = undefined;
    if (product.legoSetNumber) {
      const repo = getBricklinkRepository();
      // Try exact match first
      bricklinkData = await repo.findByItemId(product.legoSetNumber);

      // If not found and doesn't end with -1, try appending -1
      if (!bricklinkData && !product.legoSetNumber.endsWith("-1")) {
        bricklinkData = await repo.findByItemId(`${product.legoSetNumber}-1`);
      }
    }

    // Fetch WorldBricks data if product has LEGO set number
    let worldbricksData: WorldbricksSet | undefined = undefined;
    if (product.legoSetNumber) {
      const worldbricksRepo = getWorldBricksRepository();
      worldbricksData = await worldbricksRepo.findBySetNumber(
        product.legoSetNumber,
      );
    }

    return ctx.render({
      product,
      shopeeScrapes: shopeeScrapesData,
      priceHistory: priceHistoryData,
      bricklinkItem: bricklinkData,
      worldbricksSet: worldbricksData,
    });
  },
};

export default function ProductDetailPage(
  { data }: PageProps<ProductDetailData | null>,
) {
  if (!data) {
    return (
      <div class="min-h-screen bg-base-200 flex items-center justify-center">
        <div class="text-center">
          <h1 class="text-4xl font-bold text-error mb-4">Product Not Found</h1>
          <a href="/products" class="btn btn-primary">
            Back to Products
          </a>
        </div>
      </div>
    );
  }

  const {
    product,
    shopeeScrapes,
    priceHistory,
    bricklinkItem,
    worldbricksSet,
  } = data;

  // Helper functions
  const formatPrice = (price: number | null, currency: string | null) => {
    if (!price && price !== 0) return "N/A";
    const formatted = (price / 100).toFixed(2);
    return `${currency || "SGD"} ${formatted}`;
  };

  const formatNumber = (num: number | null) => {
    if (!num && num !== 0) return "N/A";
    return num.toLocaleString();
  };

  const formatDate = (date: Date | string) => {
    return new Date(date).toLocaleString();
  };

  const calculateDiscount = () => {
    if (!product.price || !product.priceBeforeDiscount) return null;
    if (product.priceBeforeDiscount <= product.price) return null;
    return (
      ((product.priceBeforeDiscount - product.price) /
        product.priceBeforeDiscount) * 100
    ).toFixed(0);
  };

  const discount = calculateDiscount();

  // Prepare images array for gallery
  const productImages =
    product.images && Array.isArray(product.images) && product.images.length > 0
      ? product.images as string[]
      : product.image
      ? [product.image]
      : [];

  return (
    <>
      <Head>
        <title>{product.name || "Product"} - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto space-y-6">
          {/* Breadcrumb */}
          <div class="text-sm breadcrumbs">
            <ul>
              <li>
                <a href="/products" class="link link-hover">Products</a>
              </li>
              <li>{product.name || "Product Details"}</li>
            </ul>
          </div>

          {/* Header with Title and Actions */}
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 class="text-3xl lg:text-4xl font-bold mb-2">
                {product.name || "Unknown Product"}
              </h1>
              <div class="flex items-center gap-2 flex-wrap">
                <div class="badge badge-primary badge-lg">
                  {product.source.toUpperCase()}
                </div>
                {product.brand && (
                  <div class="badge badge-outline badge-lg">
                    {product.brand}
                  </div>
                )}
                {product.legoSetNumber && (
                  <div class="badge badge-secondary badge-lg">
                    Set #{product.legoSetNumber}
                  </div>
                )}
              </div>
            </div>
            <ProductEditModal product={product} />
          </div>

          {/* Quick Actions */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title text-2xl mb-4">Quick Links</h2>
              <div class="flex flex-wrap gap-3">
                <a
                  href={`/products?search=${product.productId}`}
                  class="btn btn-primary"
                >
                  View in Product List
                </a>
                {product.legoSetNumber && (
                  <>
                    <a
                      href={`https://www.bricklink.com/v2/catalog/catalogitem.page?S=${product.legoSetNumber}-1`}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="btn btn-outline"
                    >
                      View on Bricklink ↗
                    </a>
                    <a
                      href={`https://www.brickeconomy.com/set/${product.legoSetNumber}-1/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="btn btn-outline"
                    >
                      View on Brickeconomy ↗
                    </a>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Pricing Overview */}
          <PricingOverview
            productId={product.productId}
            currentPrice={product.price ?? undefined}
            priceBeforeDiscount={product.priceBeforeDiscount ?? undefined}
            currency={product.currency ?? "MYR"}
          />

          {/* Images Section */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title text-2xl mb-4">Product Images</h2>
              <div class="max-w-2xl mx-auto">
                <ProductImageGallery
                  images={productImages}
                  productName={product.name || "Product"}
                />
              </div>
            </div>
          </div>

          {/* Bricklink Market Data Section */}
          {bricklinkItem && (() => {
            // Type cast JSONB fields to PricingBox
            const currentNew = bricklinkItem.currentNew as PricingBox | null;
            const currentUsed = bricklinkItem.currentUsed as PricingBox | null;
            const sixMonthNew = bricklinkItem.sixMonthNew as PricingBox | null;
            const sixMonthUsed = bricklinkItem.sixMonthUsed as
              | PricingBox
              | null;

            return (
              <div class="card bg-base-100 shadow-xl">
                <div class="card-body">
                  <h2 class="card-title text-2xl mb-4">
                    Bricklink Market Data
                  </h2>

                  {/* Last Scraped Info */}
                  <div class="alert alert-info mb-6">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      class="stroke-current shrink-0 w-6 h-6"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      >
                      </path>
                    </svg>
                    <span>
                      Last updated: {bricklinkItem.lastScrapedAt
                        ? formatDate(bricklinkItem.lastScrapedAt)
                        : "Never"}
                    </span>
                  </div>

                  {/* Current Market Prices */}
                  <h3 class="text-lg font-semibold mb-3">
                    Current Market Prices
                  </h3>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                    {/* New Condition */}
                    {currentNew && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-success mb-4">
                            New Condition
                          </h4>
                          <div class="grid grid-cols-2 gap-3">
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Average Price
                              </div>
                              <div class="stat-value text-lg">
                                {currentNew.avg_price?.currency}{" "}
                                {currentNew.avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Qty Avg Price
                              </div>
                              <div class="stat-value text-lg">
                                {currentNew.qty_avg_price?.currency}{" "}
                                {currentNew.qty_avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Min Price</div>
                              <div class="stat-value text-base text-info">
                                {currentNew.min_price?.currency}{" "}
                                {currentNew.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base text-warning">
                                {currentNew.max_price?.currency}{" "}
                                {currentNew.max_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Total Units Sold
                              </div>
                              <div class="stat-value text-base">
                                {formatNumber(currentNew.total_qty ?? null)}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Total Lots</div>
                              <div class="stat-value text-base">
                                {formatNumber(currentNew.total_lots ?? null)}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Used Condition */}
                    {currentUsed && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-warning mb-4">
                            Used Condition
                          </h4>
                          <div class="grid grid-cols-2 gap-3">
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Average Price
                              </div>
                              <div class="stat-value text-lg">
                                {currentUsed.avg_price?.currency}{" "}
                                {currentUsed.avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Qty Avg Price
                              </div>
                              <div class="stat-value text-lg">
                                {currentUsed.qty_avg_price?.currency}{" "}
                                {currentUsed.qty_avg_price?.amount?.toFixed(
                                  2,
                                ) || "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Min Price</div>
                              <div class="stat-value text-base text-info">
                                {currentUsed.min_price?.currency}{" "}
                                {currentUsed.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base text-warning">
                                {currentUsed.max_price?.currency}{" "}
                                {currentUsed.max_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Total Units Sold
                              </div>
                              <div class="stat-value text-base">
                                {formatNumber(currentUsed.total_qty ?? null)}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Total Lots</div>
                              <div class="stat-value text-base">
                                {formatNumber(currentUsed.total_lots ?? null)}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 6-Month Historical Comparison */}
                  <h3 class="text-lg font-semibold mb-3">
                    6-Month Historical Data
                  </h3>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* New Condition - Historical */}
                    {sixMonthNew && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-success mb-4">
                            New Condition (Past 6 Months)
                          </h4>
                          <div class="grid grid-cols-2 gap-3">
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Average Price
                              </div>
                              <div class="stat-value text-lg">
                                {sixMonthNew.avg_price?.currency}{" "}
                                {sixMonthNew.avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                              {currentNew?.avg_price && sixMonthNew.avg_price &&
                                (
                                  <div class="stat-desc">
                                    {((currentNew.avg_price.amount -
                                        sixMonthNew.avg_price.amount) /
                                        sixMonthNew.avg_price.amount * 100) > 0
                                      ? (
                                        <span class="text-error">
                                          ↑ {((currentNew.avg_price.amount -
                                            sixMonthNew.avg_price.amount) /
                                            sixMonthNew.avg_price.amount * 100)
                                            .toFixed(1)}%
                                        </span>
                                      )
                                      : (
                                        <span class="text-success">
                                          ↓ {Math.abs(
                                            (currentNew.avg_price.amount -
                                              sixMonthNew.avg_price.amount) /
                                              sixMonthNew.avg_price.amount *
                                              100,
                                          ).toFixed(1)}%
                                        </span>
                                      )}
                                  </div>
                                )}
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Qty Avg Price
                              </div>
                              <div class="stat-value text-lg">
                                {sixMonthNew.qty_avg_price?.currency}{" "}
                                {sixMonthNew.qty_avg_price?.amount?.toFixed(
                                  2,
                                ) || "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Min Price</div>
                              <div class="stat-value text-base text-info">
                                {sixMonthNew.min_price?.currency}{" "}
                                {sixMonthNew.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base text-warning">
                                {sixMonthNew.max_price?.currency}{" "}
                                {sixMonthNew.max_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Times Sold</div>
                              <div class="stat-value text-base">
                                {formatNumber(sixMonthNew.times_sold ?? null)}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Total Units</div>
                              <div class="stat-value text-base">
                                {formatNumber(sixMonthNew.total_qty ?? null)}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Used Condition - Historical */}
                    {sixMonthUsed && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-warning mb-4">
                            Used Condition (Past 6 Months)
                          </h4>
                          <div class="grid grid-cols-2 gap-3">
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Average Price
                              </div>
                              <div class="stat-value text-lg">
                                {sixMonthUsed.avg_price?.currency}{" "}
                                {sixMonthUsed.avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                              {currentUsed?.avg_price &&
                                sixMonthUsed.avg_price && (
                                <div class="stat-desc">
                                  {((currentUsed.avg_price.amount -
                                      sixMonthUsed.avg_price.amount) /
                                      sixMonthUsed.avg_price.amount * 100) > 0
                                    ? (
                                      <span class="text-error">
                                        ↑ {((currentUsed.avg_price.amount -
                                          sixMonthUsed.avg_price.amount) /
                                          sixMonthUsed.avg_price.amount * 100)
                                          .toFixed(1)}%
                                      </span>
                                    )
                                    : (
                                      <span class="text-success">
                                        ↓ {Math.abs(
                                          (currentUsed.avg_price.amount -
                                            sixMonthUsed.avg_price.amount) /
                                            sixMonthUsed.avg_price.amount * 100,
                                        ).toFixed(1)}%
                                      </span>
                                    )}
                                </div>
                              )}
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">
                                Qty Avg Price
                              </div>
                              <div class="stat-value text-lg">
                                {sixMonthUsed.qty_avg_price?.currency}{" "}
                                {sixMonthUsed.qty_avg_price?.amount?.toFixed(
                                  2,
                                ) || "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Min Price</div>
                              <div class="stat-value text-base text-info">
                                {sixMonthUsed.min_price?.currency}{" "}
                                {sixMonthUsed.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base text-warning">
                                {sixMonthUsed.max_price?.currency}{" "}
                                {sixMonthUsed.max_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Times Sold</div>
                              <div class="stat-value text-base">
                                {formatNumber(sixMonthUsed.times_sold ?? null)}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Total Units</div>
                              <div class="stat-value text-base">
                                {formatNumber(sixMonthUsed.total_qty ?? null)}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Core Product Info Section */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title text-2xl mb-4">Core Information</h2>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Product ID</div>
                  <div class="stat-value text-lg break-all">
                    {product.productId}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Database ID</div>
                  <div class="stat-value text-lg">{product.id}</div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Source</div>
                  <div class="stat-value text-lg">{product.source}</div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Brand</div>
                  <div class="stat-value text-lg">{product.brand || "N/A"}</div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">LEGO Set Number</div>
                  <div class="stat-value text-lg">
                    {product.legoSetNumber || "N/A"}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Watch Status</div>
                  <div class="stat-value text-lg">
                    <div
                      class={`badge badge-lg ${
                        product.watchStatus === "active"
                          ? "badge-success"
                          : product.watchStatus === "paused"
                          ? "badge-warning"
                          : product.watchStatus === "stopped"
                          ? "badge-error"
                          : "badge-ghost"
                      }`}
                    >
                      {product.watchStatus || "N/A"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* LEGO Set Information Section */}
          {worldbricksSet && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">LEGO Set Information</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Set Name</div>
                    <div class="stat-value text-lg">
                      {worldbricksSet.setName || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Year Released</div>
                    <div class="stat-value text-xl">
                      {worldbricksSet.yearReleased || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Retirement</div>
                    <div class="stat-value text-xl">
                      {worldbricksSet.yearRetired
                        ? (
                          <div class="flex items-center gap-2">
                            <span>{worldbricksSet.yearRetired}</span>
                            <div class="badge badge-warning">Retired</div>
                          </div>
                        )
                        : "Not retired"}
                    </div>
                  </div>
                  {worldbricksSet.designer && (
                    <div class="stat bg-base-200 rounded-lg">
                      <div class="stat-title">Designer</div>
                      <div class="stat-value text-lg">
                        {worldbricksSet.designer}
                      </div>
                    </div>
                  )}
                  {worldbricksSet.partsCount && (
                    <div class="stat bg-base-200 rounded-lg">
                      <div class="stat-title">Parts Count</div>
                      <div class="stat-value text-xl">
                        {formatNumber(worldbricksSet.partsCount)}
                      </div>
                    </div>
                  )}
                  {worldbricksSet.dimensions && (
                    <div class="stat bg-base-200 rounded-lg">
                      <div class="stat-title">Dimensions</div>
                      <div class="stat-value text-sm">
                        {worldbricksSet.dimensions}
                      </div>
                    </div>
                  )}
                </div>
                {worldbricksSet.description && (
                  <div class="mt-4">
                    <h3 class="text-lg font-semibold mb-2">Description</h3>
                    <p class="text-sm">{worldbricksSet.description}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Bricklink/Investment Analysis Section */}
          {product.legoSetNumber && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">
                  Bricklink Investment Analysis
                </h2>
                <ProductAnalysisCard
                  productId={product.productId}
                  defaultStrategy="Investment Focus"
                />
              </div>
            </div>
          )}

          {/* Shopee Section */}
          {product.source === "shopee" && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">Shopee Data</h2>

                {/* Sales & Engagement Metrics */}
                <h3 class="text-lg font-semibold mb-3">Sales & Engagement</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Units Sold</div>
                    <div class="stat-value text-xl">
                      {formatNumber(product.unitsSold)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Lifetime Sold</div>
                    <div class="stat-value text-xl">
                      {formatNumber(product.lifetimeSold)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Views</div>
                    <div class="stat-value text-xl">
                      {formatNumber(product.view_count)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Likes</div>
                    <div class="stat-value text-xl">
                      {formatNumber(product.liked_count)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Comments</div>
                    <div class="stat-value text-xl">
                      {formatNumber(product.commentCount)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Avg Star Rating</div>
                    <div class="stat-value text-xl">
                      {product.avgStarRating
                        ? (product.avgStarRating / 10).toFixed(1)
                        : "N/A"}
                    </div>
                  </div>
                </div>

                {/* Shop Information */}
                <h3 class="text-lg font-semibold mb-3">Shop Information</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Shop ID</div>
                    <div class="stat-value text-lg">
                      {product.shopId?.toString() || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Shop Name</div>
                    <div class="stat-value text-lg">
                      {product.shopName || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Shop Location</div>
                    <div class="stat-value text-lg">
                      {product.shopLocation || "N/A"}
                    </div>
                  </div>
                </div>

                {/* Stock Information */}
                <h3 class="text-lg font-semibold mb-3">Stock Information</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Current Stock</div>
                    <div
                      class={`stat-value text-xl ${
                        product.currentStock === 0
                          ? "text-error"
                          : (product.currentStock || 0) < 10
                          ? "text-warning"
                          : "text-success"
                      }`}
                    >
                      {formatNumber(product.currentStock)}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Stock Type</div>
                    <div class="stat-value text-lg">
                      {product.stockType?.toString() || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Stock Info Summary</div>
                    <div class="stat-value text-sm">
                      {product.stockInfoSummary || "N/A"}
                    </div>
                  </div>
                </div>

                {/* Shop Flags & Badges */}
                <h3 class="text-lg font-semibold mb-3">Shop Badges & Flags</h3>
                <div class="flex flex-wrap gap-2">
                  <div
                    class={`badge badge-lg ${
                      product.isPreferred ? "badge-success" : "badge-ghost"
                    }`}
                  >
                    {product.isPreferred ? "✓" : "✗"} Preferred Seller
                  </div>
                  <div
                    class={`badge badge-lg ${
                      product.isMart ? "badge-info" : "badge-ghost"
                    }`}
                  >
                    {product.isMart ? "✓" : "✗"} Shopee Mall
                  </div>
                  <div
                    class={`badge badge-lg ${
                      product.isServiceByShopee
                        ? "badge-primary"
                        : "badge-ghost"
                    }`}
                  >
                    {product.isServiceByShopee ? "✓" : "✗"} Service by Shopee
                  </div>
                  <div
                    class={`badge badge-lg ${
                      product.isAdult ? "badge-warning" : "badge-ghost"
                    }`}
                  >
                    {product.isAdult ? "✓" : "✗"} Adult Content
                  </div>
                </div>

                {/* Rating Distribution */}
                {product.ratingCount &&
                  typeof product.ratingCount === "object" && (
                  <>
                    <h3 class="text-lg font-semibold mb-3 mt-6">
                      Rating Distribution
                    </h3>
                    <div class="bg-base-200 rounded-lg p-4">
                      <pre class="text-sm overflow-auto">{JSON.stringify(product.ratingCount, null, 2)}</pre>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* ToysRUs Section */}
          {product.source === "toysrus" && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">ToysRUs Data</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">SKU</div>
                    <div class="stat-value text-lg">{product.sku || "N/A"}</div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Category Number</div>
                    <div class="stat-value text-lg">
                      {product.categoryNumber || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Category Name</div>
                    <div class="stat-value text-lg">
                      {product.categoryName || "N/A"}
                    </div>
                  </div>
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Age Range</div>
                    <div class="stat-value text-lg">
                      {product.ageRange || "N/A"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Historical Data Section */}
          {(shopeeScrapes.length > 0 || priceHistory.length > 0) && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">Historical Data</h2>

                {/* Shopee Scrapes History */}
                {shopeeScrapes.length > 0 && (
                  <>
                    <h3 class="text-lg font-semibold mb-3">
                      Shopee Scrape History ({shopeeScrapes.length} records)
                    </h3>
                    <div class="overflow-x-auto mb-6">
                      <table class="table table-zebra table-sm">
                        <thead>
                          <tr>
                            <th>Scraped At</th>
                            <th>Price</th>
                            <th>Units Sold</th>
                            <th>Shop Name</th>
                            <th>Shop ID</th>
                          </tr>
                        </thead>
                        <tbody>
                          {shopeeScrapes.map((scrape) => (
                            <tr key={scrape.id}>
                              <td class="whitespace-nowrap">
                                {formatDate(scrape.scrapedAt)}
                              </td>
                              <td>
                                {formatPrice(scrape.price, scrape.currency)}
                              </td>
                              <td>{formatNumber(scrape.unitsSold)}</td>
                              <td>{scrape.shopName || "N/A"}</td>
                              <td>{scrape.shopId?.toString() || "N/A"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                {/* Price History */}
                {priceHistory.length > 0 && (
                  <>
                    <h3 class="text-lg font-semibold mb-3">
                      Price History ({priceHistory.length} records)
                    </h3>
                    <div class="overflow-x-auto">
                      <table class="table table-zebra table-sm">
                        <thead>
                          <tr>
                            <th>Recorded At</th>
                            <th>Price</th>
                            <th>Before Discount</th>
                            <th>Units Sold</th>
                            <th>Discount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {priceHistory.map((record) => {
                            const recordDiscount =
                              record.price && record.priceBeforeDiscount &&
                                record.priceBeforeDiscount > record.price
                                ? (((record.priceBeforeDiscount -
                                  record.price) / record.priceBeforeDiscount) *
                                  100).toFixed(0)
                                : null;
                            return (
                              <tr key={record.id}>
                                <td class="whitespace-nowrap">
                                  {formatDate(record.recordedAt)}
                                </td>
                                <td>
                                  {formatPrice(record.price, product.currency)}
                                </td>
                                <td>
                                  {formatPrice(
                                    record.priceBeforeDiscount,
                                    product.currency,
                                  )}
                                </td>
                                <td>
                                  {formatNumber(record.unitsSoldSnapshot)}
                                </td>
                                <td>
                                  {recordDiscount && (
                                    <div class="badge badge-success badge-sm">
                                      {recordDiscount}%
                                    </div>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Metadata Section */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title text-2xl mb-4">
                Metadata & Technical Info
              </h2>

              {/* Timestamps */}
              <h3 class="text-lg font-semibold mb-3">Timestamps</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Created At</div>
                  <div class="stat-value text-sm">
                    {formatDate(product.createdAt)}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Updated At</div>
                  <div class="stat-value text-sm">
                    {formatDate(product.updatedAt)}
                  </div>
                </div>
              </div>

              {/* Image Data */}
              <h3 class="text-lg font-semibold mb-3">Image Information</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Main Image URL</div>
                  <div class="stat-value text-xs break-all">
                    {product.image || "N/A"}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Local Image Path</div>
                  <div class="stat-value text-xs break-all">
                    {product.localImagePath || "N/A"}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Image Download Status</div>
                  <div class="stat-value text-sm">
                    <div
                      class={`badge ${
                        product.imageDownloadStatus === "completed"
                          ? "badge-success"
                          : product.imageDownloadStatus === "failed"
                          ? "badge-error"
                          : product.imageDownloadStatus === "pending"
                          ? "badge-warning"
                          : "badge-ghost"
                      }`}
                    >
                      {product.imageDownloadStatus || "N/A"}
                    </div>
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Image Downloaded At</div>
                  <div class="stat-value text-xs">
                    {product.imageDownloadedAt
                      ? formatDate(product.imageDownloadedAt)
                      : "N/A"}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Total Images</div>
                  <div class="stat-value text-xl">
                    {product.images && Array.isArray(product.images)
                      ? product.images.length
                      : 0}
                  </div>
                </div>
                {product.localImages &&
                  typeof product.localImages === "object" && (
                  <div class="stat bg-base-200 rounded-lg">
                    <div class="stat-title">Local Images</div>
                    <div class="stat-value text-xs">
                      {Array.isArray(product.localImages)
                        ? product.localImages.length
                        : "N/A"}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

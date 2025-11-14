/**
 * Product Detail Page
 * Shows product metadata and comprehensive analysis
 */

import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { desc, eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  type BricklinkItem,
  type BrickrankerRetirementItem,
  priceHistory,
  type Product,
  productTags,
  products,
  shopeeScrapes,
  type WorldbricksSet,
} from "../../db/schema.ts";
import { getBricklinkRepository } from "../../services/bricklink/BricklinkRepository.ts";
import { getBrickRankerRepository } from "../../services/brickranker/BrickRankerRepository.ts";
import { getWorldBricksRepository } from "../../services/worldbricks/WorldBricksRepository.ts";
import TagBadge from "../../components/tags/TagBadge.tsx";
import IntrinsicValueCard from "../../islands/IntrinsicValueCard.tsx";
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

interface ProductTag {
  id: string;
  name: string;
  description: string | null;
  endDate: string | null;
  isExpired?: boolean;
}

interface ProductDetailData {
  product: Product;
  shopeeScrapes: ShopeeScrape[];
  priceHistory: PriceHistoryRecord[];
  bricklinkItem: BricklinkItem | undefined;
  worldbricksSet: WorldbricksSet | undefined;
  brickrankerItem: BrickrankerRetirementItem | undefined;
  productTags: ProductTag[];
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

    // Fetch BrickRanker retirement data if product has LEGO set number
    let brickrankerData: BrickrankerRetirementItem | undefined = undefined;
    if (product.legoSetNumber) {
      const brickrankerRepo = getBrickRankerRepository();
      brickrankerData = await brickrankerRepo.findBySetNumber(
        product.legoSetNumber,
      );
    }

    // Fetch product tags
    const productTagsData: ProductTag[] = [];
    if (product.tags && Array.isArray(product.tags)) {
      const tagIds = (product.tags as Array<{ tagId: string; addedAt: string }>)
        .map((t) => t.tagId);

      if (tagIds.length > 0) {
        const tags = await db
          .select()
          .from(productTags)
          .where(
            sql`${productTags.id} = ANY(${tagIds})`,
          );

        // Map tags and check if expired
        const now = new Date();
        productTagsData.push(
          ...tags.map((tag) => ({
            ...tag,
            isExpired: tag.endDate ? new Date(tag.endDate) < now : false,
          })),
        );
      }
    }

    return ctx.render({
      product,
      shopeeScrapes: shopeeScrapesData,
      priceHistory: priceHistoryData,
      bricklinkItem: bricklinkData,
      worldbricksSet: worldbricksData,
      brickrankerItem: brickrankerData,
      productTags: productTagsData,
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
    brickrankerItem,
    productTags,
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

  // Prepare images array for gallery - prioritize local images over remote URLs
  const productImages = (() => {
    // First priority: local images array
    if (
      product.localImages && Array.isArray(product.localImages) &&
      product.localImages.length > 0
    ) {
      return product.localImages as string[];
    }
    // Second priority: single local image path
    if (product.localImagePath) {
      return [product.localImagePath];
    }
    // Third priority: remote images array
    if (
      product.images && Array.isArray(product.images) &&
      product.images.length > 0
    ) {
      return product.images as string[];
    }
    // Fourth priority: single remote image
    if (product.image) {
      return [product.image];
    }
    // No images available
    return [];
  })();

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
              {productTags.length > 0 && (
                <div class="flex items-center gap-2 flex-wrap mt-2">
                  <span class="text-sm text-base-content/60">Tags:</span>
                  {productTags.map((tag) => (
                    <TagBadge
                      key={tag.id}
                      name={tag.name}
                      isExpired={tag.isExpired}
                      showStatus={tag.isExpired}
                    />
                  ))}
                </div>
              )}
            </div>
            <ProductEditModal
              product={product}
              worldbricksSet={worldbricksSet}
              brickrankerItem={brickrankerItem}
            />
          </div>

          {/* Quick Links & Core Information - Side by Side Layout */}
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Quick Links & Core Information */}
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-xl mb-3">Core Information</h2>

                <div class="flex flex-wrap gap-3 mb-4">
                  <a
                    href={`/products?search=${product.productId}`}
                    class="btn btn-primary btn-sm"
                  >
                    View in Product List
                  </a>
                  {product.legoSetNumber && (
                    <>
                      <a
                        href={`https://www.bricklink.com/v2/catalog/catalogitem.page?S=${product.legoSetNumber}-1`}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn btn-outline btn-sm"
                      >
                        View on Bricklink ↗
                      </a>
                      <a
                        href={`https://www.brickeconomy.com/set/${product.legoSetNumber}-1/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn btn-outline btn-sm"
                      >
                        View on Brickeconomy ↗
                      </a>
                    </>
                  )}
                </div>

                <div class="space-y-3">
                  {/* LEGO Set Number & Watch Status */}
                  <div class="flex items-center gap-2 flex-wrap text-sm">
                    <span class="text-base-content/60">LEGO Set:</span>
                    <span class="font-semibold">{product.legoSetNumber || "N/A"}</span>
                    <span class="text-base-content/60">•</span>
                    <span class="text-base-content/60">Watch Status:</span>
                    <div
                      class={`badge badge-sm ${
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

                  {/* Retirement Timeline */}
                  {(worldbricksSet || brickrankerItem) && (
                    <div class="divider my-2"></div>
                  )}

                  {/* Release Year */}
                  {(worldbricksSet?.yearReleased || brickrankerItem?.yearReleased) && (
                    <div class="flex items-center gap-2 text-sm">
                      <span class="text-base-content/60">Release Year:</span>
                      <span class="font-semibold text-success">
                        {worldbricksSet?.yearReleased || brickrankerItem?.yearReleased}
                      </span>
                    </div>
                  )}

                  {/* Retirement Status */}
                  {(() => {
                    const isRetired = worldbricksSet?.yearRetired;
                    const isRetiringSoon = brickrankerItem?.retiringSoon;
                    const expectedRetirement = brickrankerItem?.expectedRetirementDate;

                    if (isRetired) {
                      return (
                        <div class="flex items-center gap-2 text-sm">
                          <span class="text-base-content/60">Retirement Year:</span>
                          <span class="font-semibold text-error">{worldbricksSet.yearRetired}</span>
                          <div class="badge badge-error badge-sm">Retired</div>
                        </div>
                      );
                    } else if (isRetiringSoon && expectedRetirement) {
                      return (
                        <div class="flex items-center gap-2 text-sm">
                          <span class="text-base-content/60">Expected Retirement:</span>
                          <span class="font-semibold text-warning">{expectedRetirement}</span>
                          <div class="badge badge-warning badge-sm">Retiring Soon</div>
                        </div>
                      );
                    } else if (worldbricksSet?.yearReleased || brickrankerItem?.yearReleased) {
                      return (
                        <div class="flex items-center gap-2 text-sm">
                          <span class="text-base-content/60">Status:</span>
                          <div class="badge badge-success badge-sm">Active</div>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>
              </div>
            </div>

            {/* Product Images */}
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">Product Images</h2>
                <ProductImageGallery
                  images={productImages}
                  productName={product.name || "Product"}
                />
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


          {/* Bricklink Market Data Section */}
          {bricklinkItem && (() => {
            // Type cast JSONB fields to PricingBox
            const currentNew = bricklinkItem.currentNew as PricingBox | null;
            const currentUsed = bricklinkItem.currentUsed as PricingBox | null;
            const sixMonthNew = bricklinkItem.sixMonthNew as PricingBox | null;
            const sixMonthUsed = bricklinkItem.sixMonthUsed as
              | PricingBox
              | null;

            // Check if at least one pricing box has data
            const hasPricingData = currentNew || currentUsed || sixMonthNew ||
              sixMonthUsed;

            // If no pricing data available, show a message instead of empty section
            if (!hasPricingData) {
              return (
                <div class="card bg-base-100 shadow-xl">
                  <div class="card-body">
                    <h2 class="card-title text-2xl mb-4">
                      📊 Bricklink Market Data
                    </h2>
                    <div class="alert alert-warning">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        class="stroke-current shrink-0 h-6 w-6"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        />
                      </svg>
                      <div>
                        <h3 class="font-bold">Pricing data not available</h3>
                        <div class="text-xs">
                          This LEGO set exists on BrickLink (item:{" "}
                          {bricklinkItem.itemId}), but pricing information
                          hasn't been scraped yet or isn't available in the
                          market.
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <div class="card bg-base-100 shadow-xl">
                <div class="card-body">
                  <h2 class="card-title text-2xl mb-4">
                    📊 Bricklink Market Data
                  </h2>

                  {/* Last Scraped Info */}
                  <div class="text-xs text-base-content/60 mb-6">
                    Last updated: {bricklinkItem.lastScrapedAt
                      ? formatDate(bricklinkItem.lastScrapedAt)
                      : "Never"}
                  </div>

                  <div class="divider divider-start">
                    <span class="text-lg font-semibold">
                      Current Market Prices
                    </span>
                  </div>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                    {/* New Condition */}
                    {currentNew && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-success mb-4">
                            🟢 New Condition
                          </h4>

                          {/* Price Range Visualization */}
                          {currentNew.min_price && currentNew.max_price &&
                            currentNew.avg_price && (
                            <div class="mb-4 p-4 bg-base-100 rounded-lg">
                              <div class="text-xs font-semibold text-base-content/60 mb-2">
                                PRICE RANGE
                              </div>
                              <div class="flex items-center gap-2">
                                <span class="text-xs text-info">
                                  {currentNew.min_price.currency}{" "}
                                  {currentNew.min_price.amount.toFixed(2)}
                                </span>
                                <progress
                                  class="progress progress-success flex-1"
                                  value={((currentNew.avg_price.amount -
                                    currentNew.min_price.amount) /
                                    (currentNew.max_price.amount -
                                      currentNew.min_price.amount)) * 100}
                                  max="100"
                                >
                                </progress>
                                <span class="text-xs text-warning">
                                  {currentNew.max_price.currency}{" "}
                                  {currentNew.max_price.amount.toFixed(2)}
                                </span>
                              </div>
                              <div class="text-center mt-1">
                                <span class="text-xs text-success font-semibold">
                                  Avg: {currentNew.avg_price.currency}{" "}
                                  {currentNew.avg_price.amount.toFixed(2)}
                                </span>
                              </div>
                            </div>
                          )}

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
                                <div
                                  class="tooltip"
                                  data-tip="Weighted average price based on quantity sold"
                                >
                                  Qty Avg Price
                                  <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    class="inline-block w-3 h-3 stroke-current ml-1"
                                  >
                                    <path
                                      stroke-linecap="round"
                                      stroke-linejoin="round"
                                      stroke-width="2"
                                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                    >
                                    </path>
                                  </svg>
                                </div>
                              </div>
                              <div class="stat-value text-lg">
                                {currentNew.qty_avg_price?.currency}{" "}
                                {currentNew.qty_avg_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Min Price</div>
                              <div class="stat-value text-base">
                                {currentNew.min_price?.currency}{" "}
                                {currentNew.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base">
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
                            🟡 Used Condition
                          </h4>

                          {/* Price Range Visualization */}
                          {currentUsed.min_price && currentUsed.max_price &&
                            currentUsed.avg_price && (
                            <div class="mb-4 p-4 bg-base-100 rounded-lg">
                              <div class="text-xs font-semibold text-base-content/60 mb-2">
                                PRICE RANGE
                              </div>
                              <div class="flex items-center gap-2">
                                <span class="text-xs text-info">
                                  {currentUsed.min_price.currency}{" "}
                                  {currentUsed.min_price.amount.toFixed(2)}
                                </span>
                                <progress
                                  class="progress progress-warning flex-1"
                                  value={((currentUsed.avg_price.amount -
                                    currentUsed.min_price.amount) /
                                    (currentUsed.max_price.amount -
                                      currentUsed.min_price.amount)) * 100}
                                  max="100"
                                >
                                </progress>
                                <span class="text-xs text-warning">
                                  {currentUsed.max_price.currency}{" "}
                                  {currentUsed.max_price.amount.toFixed(2)}
                                </span>
                              </div>
                              <div class="text-center mt-1">
                                <span class="text-xs text-warning font-semibold">
                                  Avg: {currentUsed.avg_price.currency}{" "}
                                  {currentUsed.avg_price.amount.toFixed(2)}
                                </span>
                              </div>
                            </div>
                          )}

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
                                <div
                                  class="tooltip"
                                  data-tip="Weighted average price based on quantity sold"
                                >
                                  Qty Avg Price
                                  <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    class="inline-block w-3 h-3 stroke-current ml-1"
                                  >
                                    <path
                                      stroke-linecap="round"
                                      stroke-linejoin="round"
                                      stroke-width="2"
                                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                    >
                                    </path>
                                  </svg>
                                </div>
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
                              <div class="stat-value text-base">
                                {currentUsed.min_price?.currency}{" "}
                                {currentUsed.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base">
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

                  <div class="divider divider-start">
                    <span class="text-lg font-semibold">
                      6-Month Historical Data
                    </span>
                  </div>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* New Condition - Historical */}
                    {sixMonthNew && (
                      <div class="card bg-base-200">
                        <div class="card-body">
                          <h4 class="card-title text-success mb-4">
                            🟢 New Condition (Past 6 Months)
                          </h4>

                          {/* Price Trend Radial Progress */}
                          {currentNew?.avg_price && sixMonthNew.avg_price &&
                            (() => {
                              const changePercent =
                                (currentNew.avg_price.amount -
                                  sixMonthNew.avg_price.amount) /
                                sixMonthNew.avg_price.amount * 100;
                              const isIncrease = changePercent > 0;
                              return (
                                <div class="flex justify-center mb-4">
                                  <div class="flex items-center gap-6">
                                    <div class="text-center">
                                      <div
                                        class={`radial-progress ${
                                          isIncrease
                                            ? "text-error"
                                            : "text-success"
                                        }`}
                                        style={`--value:${
                                          Math.min(Math.abs(changePercent), 100)
                                        };--size:6rem;`}
                                        role="progressbar"
                                      >
                                        {isIncrease ? "↑" : "↓"}{" "}
                                        {Math.abs(changePercent).toFixed(1)}%
                                      </div>
                                      <div class="text-xs mt-2 text-base-content/70">
                                        6-Month Trend
                                      </div>
                                    </div>
                                    <div class="text-sm">
                                      <div class="text-base-content/60">
                                        6 months ago:{" "}
                                        <span class="font-semibold">
                                          {sixMonthNew.avg_price.currency}{" "}
                                          {sixMonthNew.avg_price.amount.toFixed(
                                            2,
                                          )}
                                        </span>
                                      </div>
                                      <div class="text-base-content/60">
                                        Current:{" "}
                                        <span class="font-semibold">
                                          {currentNew.avg_price.currency}{" "}
                                          {currentNew.avg_price.amount.toFixed(
                                            2,
                                          )}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}

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
                              <div class="stat-value text-base">
                                {sixMonthNew.min_price?.currency}{" "}
                                {sixMonthNew.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base">
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
                            🟡 Used Condition (Past 6 Months)
                          </h4>

                          {/* Price Trend Radial Progress */}
                          {currentUsed?.avg_price && sixMonthUsed.avg_price &&
                            (() => {
                              const changePercent =
                                (currentUsed.avg_price.amount -
                                  sixMonthUsed.avg_price.amount) /
                                sixMonthUsed.avg_price.amount * 100;
                              const isIncrease = changePercent > 0;
                              return (
                                <div class="flex justify-center mb-4">
                                  <div class="flex items-center gap-6">
                                    <div class="text-center">
                                      <div
                                        class={`radial-progress ${
                                          isIncrease
                                            ? "text-error"
                                            : "text-success"
                                        }`}
                                        style={`--value:${
                                          Math.min(Math.abs(changePercent), 100)
                                        };--size:6rem;`}
                                        role="progressbar"
                                      >
                                        {isIncrease ? "↑" : "↓"}{" "}
                                        {Math.abs(changePercent).toFixed(1)}%
                                      </div>
                                      <div class="text-xs mt-2 text-base-content/70">
                                        6-Month Trend
                                      </div>
                                    </div>
                                    <div class="text-sm">
                                      <div class="text-base-content/60">
                                        6 months ago:{" "}
                                        <span class="font-semibold">
                                          {sixMonthUsed.avg_price.currency}{" "}
                                          {sixMonthUsed.avg_price.amount
                                            .toFixed(2)}
                                        </span>
                                      </div>
                                      <div class="text-base-content/60">
                                        Current:{" "}
                                        <span class="font-semibold">
                                          {currentUsed.avg_price.currency}{" "}
                                          {currentUsed.avg_price.amount.toFixed(
                                            2,
                                          )}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}

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
                              <div class="stat-value text-base">
                                {sixMonthUsed.min_price?.currency}{" "}
                                {sixMonthUsed.min_price?.amount?.toFixed(2) ||
                                  "N/A"}
                              </div>
                            </div>
                            <div class="stat bg-base-100 rounded-lg p-3">
                              <div class="stat-title text-xs">Max Price</div>
                              <div class="stat-value text-base">
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


          {/* LEGO Set Information Section */}
          {worldbricksSet && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">
                  🧱 LEGO Set Information
                </h2>
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

          {/* Investment Analysis Section */}
          {product.legoSetNumber && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">
                  💎 Investment Analysis
                </h2>
                <IntrinsicValueCard productId={product.productId} />
              </div>
            </div>
          )}

          {/* Shopee Section */}
          {product.source === "shopee" && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">🛒 Shopee Data</h2>

                {/* Rating Distribution */}
                {product.ratingCount &&
                  typeof product.ratingCount === "object" && (() => {
                    const ratings = product.ratingCount as Record<
                      string,
                      number
                    >;
                    const totalRatings = Object.values(ratings).reduce(
                      (sum, count) => sum + count,
                      0,
                    );

                    // Sort rating keys in descending order (5 stars to 1 star)
                    const ratingKeys = Object.keys(ratings)
                      .filter((key) => key.match(/^\d+$/))
                      .sort((a, b) => parseInt(b) - parseInt(a));

                    return (
                      <>
                        <div class="divider divider-start mt-6">
                          <span class="text-lg font-semibold">
                            ⭐ Rating Distribution
                          </span>
                        </div>

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                          {/* Visual Rating Breakdown */}
                          <div class="bg-base-200 rounded-lg p-6">
                            <div class="space-y-3">
                              {ratingKeys.map((star) => {
                                const count = ratings[star] || 0;
                                const percentage = totalRatings > 0
                                  ? (count / totalRatings * 100)
                                  : 0;
                                return (
                                  <div
                                    key={star}
                                    class="flex items-center gap-3"
                                  >
                                    <div class="flex items-center gap-1 w-16">
                                      <span class="text-sm font-semibold">
                                        {star}
                                      </span>
                                      <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        viewBox="0 0 24 24"
                                        fill="currentColor"
                                        class="w-4 h-4 text-warning"
                                      >
                                        <path
                                          fill-rule="evenodd"
                                          d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z"
                                          clip-rule="evenodd"
                                        />
                                      </svg>
                                    </div>
                                    <progress
                                      class="progress progress-warning flex-1"
                                      value={percentage}
                                      max="100"
                                    >
                                    </progress>
                                    <div class="w-20 text-right">
                                      <span class="text-sm font-semibold">
                                        {count}
                                      </span>
                                      <span class="text-xs text-base-content/60 ml-1">
                                        ({percentage.toFixed(1)}%)
                                      </span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          {/* Summary Stats */}
                          <div class="grid grid-cols-2 gap-4">
                            <div class="stat bg-base-200 rounded-lg">
                              <div class="stat-figure text-warning">
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  viewBox="0 0 24 24"
                                  fill="currentColor"
                                  class="w-12 h-12"
                                >
                                  <path
                                    fill-rule="evenodd"
                                    d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z"
                                    clip-rule="evenodd"
                                  />
                                </svg>
                              </div>
                              <div class="stat-title">Average Rating</div>
                              <div class="stat-value text-warning">
                                {product.avgStarRating
                                  ? (product.avgStarRating / 10).toFixed(1)
                                  : "N/A"}
                              </div>
                              <div class="stat-desc">out of 5.0</div>
                            </div>

                            <div class="stat bg-base-200 rounded-lg">
                              <div class="stat-figure text-primary">
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke-width="1.5"
                                  stroke="currentColor"
                                  class="w-12 h-12"
                                >
                                  <path
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z"
                                  />
                                </svg>
                              </div>
                              <div class="stat-title">Total Ratings</div>
                              <div class="stat-value text-primary">
                                {formatNumber(totalRatings)}
                              </div>
                              <div class="stat-desc">customer reviews</div>
                            </div>

                            {/* Most Common Rating */}
                            {(() => {
                              const mostCommon = ratingKeys.reduce(
                                (
                                  max,
                                  star,
                                ) => (ratings[star] > ratings[max]
                                  ? star
                                  : max),
                                ratingKeys[0],
                              );
                              return (
                                <div class="stat bg-base-200 rounded-lg col-span-2">
                                  <div class="stat-title">
                                    Most Common Rating
                                  </div>
                                  <div class="stat-value text-2xl">
                                    <div class="rating rating-lg">
                                      {[1, 2, 3, 4, 5].map((i) => (
                                        <input
                                          key={i}
                                          type="radio"
                                          class={`mask mask-star-2 ${
                                            parseInt(mostCommon) >= i
                                              ? "bg-warning"
                                              : "bg-base-300"
                                          }`}
                                          disabled
                                          checked={parseInt(mostCommon) === i}
                                        />
                                      ))}
                                    </div>
                                  </div>
                                  <div class="stat-desc">
                                    {ratings[mostCommon]}{" "}
                                    customers
                                    ({((ratings[mostCommon] / totalRatings) *
                                      100).toFixed(1)}%) gave {mostCommon} stars
                                  </div>
                                </div>
                              );
                            })()}
                          </div>
                        </div>
                      </>
                    );
                  })()}
              </div>
            </div>
          )}

          {/* ToysRUs Section */}
          {product.source === "toysrus" && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h2 class="card-title text-2xl mb-4">🧸 ToysRUs Data</h2>
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
                <h2 class="card-title text-2xl mb-4">📈 Historical Data</h2>

                {/* Price Trend Summary for Shopee */}
                {shopeeScrapes.length > 0 && (() => {
                  const sortedScrapes = [...shopeeScrapes].sort((a, b) =>
                    new Date(a.scrapedAt).getTime() -
                    new Date(b.scrapedAt).getTime()
                  );
                  const oldestPrice = sortedScrapes[0]?.price;
                  const newestPrice = sortedScrapes[sortedScrapes.length - 1]
                    ?.price;
                  const lowestPrice = Math.min(
                    ...sortedScrapes.map((s) => s.price || Infinity).filter(
                      (p) => p !== Infinity,
                    ),
                  );
                  const highestPrice = Math.max(
                    ...sortedScrapes.map((s) => s.price || -Infinity).filter(
                      (p) => p !== -Infinity,
                    ),
                  );

                  const priceChange = oldestPrice && newestPrice
                    ? ((newestPrice - oldestPrice) / oldestPrice * 100)
                    : null;

                  return (
                    <div class="stats stats-vertical lg:stats-horizontal shadow mb-6">
                      <div class="stat">
                        <div class="stat-figure text-primary">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            class="inline-block w-8 h-8 stroke-current"
                          >
                            <path
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              stroke-width="2"
                              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                            >
                            </path>
                          </svg>
                        </div>
                        <div class="stat-title">Total Records</div>
                        <div class="stat-value text-primary">
                          {shopeeScrapes.length}
                        </div>
                        <div class="stat-desc">Historical data points</div>
                      </div>

                      {priceChange !== null && (
                        <div class="stat">
                          <div
                            class={`stat-figure ${
                              priceChange >= 0 ? "text-error" : "text-success"
                            }`}
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              class="inline-block w-8 h-8 stroke-current"
                            >
                              <path
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                stroke-width="2"
                                d={priceChange >= 0
                                  ? "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                                  : "M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"}
                              >
                              </path>
                            </svg>
                          </div>
                          <div class="stat-title">Price Trend</div>
                          <div
                            class={`stat-value ${
                              priceChange >= 0 ? "text-error" : "text-success"
                            }`}
                          >
                            {priceChange >= 0 ? "↑" : "↓"}{" "}
                            {Math.abs(priceChange).toFixed(1)}%
                          </div>
                          <div class="stat-desc">Since first record</div>
                        </div>
                      )}

                      <div class="stat">
                        <div class="stat-figure text-info">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            class="inline-block w-8 h-8 stroke-current"
                          >
                            <path
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              stroke-width="2"
                              d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"
                            >
                            </path>
                          </svg>
                        </div>
                        <div class="stat-title">Lowest Price</div>
                        <div class="stat-value text-info text-xl">
                          {formatPrice(lowestPrice, product.currency)}
                        </div>
                        <div class="stat-desc">Historical low</div>
                      </div>

                      <div class="stat">
                        <div class="stat-figure text-warning">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            class="inline-block w-8 h-8 stroke-current"
                          >
                            <path
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              stroke-width="2"
                              d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                            >
                            </path>
                          </svg>
                        </div>
                        <div class="stat-title">Highest Price</div>
                        <div class="stat-value text-warning text-xl">
                          {formatPrice(highestPrice, product.currency)}
                        </div>
                        <div class="stat-desc">Historical high</div>
                      </div>
                    </div>
                  );
                })()}

                {/* Shopee Scrapes History */}
                {shopeeScrapes.length > 0 && (
                  <>
                    <div class="divider divider-start">
                      <span class="text-lg font-semibold">
                        Shopee Scrape History ({shopeeScrapes.length} records)
                      </span>
                    </div>
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
                    <div class="divider divider-start">
                      <span class="text-lg font-semibold">
                        Price History ({priceHistory.length} records)
                      </span>
                    </div>
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
                            const discountValue = recordDiscount
                              ? parseInt(recordDiscount)
                              : 0;
                            return (
                              <tr key={record.id}>
                                <td class="whitespace-nowrap">
                                  {formatDate(record.recordedAt)}
                                </td>
                                <td>
                                  <div class="flex items-center gap-2">
                                    {formatPrice(
                                      record.price,
                                      product.currency,
                                    )}
                                    {discountValue >= 30 && (
                                      <div class="indicator">
                                        <span class="indicator-item indicator-start badge badge-error badge-xs">
                                          🔥
                                        </span>
                                      </div>
                                    )}
                                  </div>
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
                                    <div
                                      class={`badge badge-sm ${
                                        discountValue >= 30
                                          ? "badge-error"
                                          : discountValue >= 20
                                          ? "badge-warning"
                                          : "badge-success"
                                      }`}
                                    >
                                      {recordDiscount}% OFF
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
                🔧 Metadata & Technical Info
              </h2>

              <div class="divider divider-start">
                <span class="text-lg font-semibold">Timestamps</span>
              </div>
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

              <div class="divider divider-start">
                <span class="text-lg font-semibold">Image Information</span>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Main Image URL</div>
                  <div class="stat-value text-xs">
                    {product.image
                      ? (
                        <div
                          class="tooltip tooltip-top"
                          data-tip={product.image}
                        >
                          <span class="truncate block max-w-full">
                            {product.image}
                          </span>
                        </div>
                      )
                      : "N/A"}
                  </div>
                </div>
                <div class="stat bg-base-200 rounded-lg">
                  <div class="stat-title">Local Image Path</div>
                  <div class="stat-value text-xs">
                    {product.localImagePath
                      ? (
                        <div
                          class="tooltip tooltip-top"
                          data-tip={product.localImagePath}
                        >
                          <span class="truncate block max-w-full">
                            {product.localImagePath}
                          </span>
                        </div>
                      )
                      : "N/A"}
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

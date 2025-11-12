/**
 * Product Detail Page
 * Shows product metadata and comprehensive analysis
 */

import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { products, type Product } from "../../db/schema.ts";
import ProductAnalysisCard from "../../islands/ProductAnalysisCard.tsx";

interface ProductDetailData {
  product: Product;
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

    return ctx.render({ product: result[0] });
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

  const { product } = data;

  // Helper functions
  const formatPrice = (price: number | null, currency: string | null) => {
    if (!price) return "N/A";
    const formatted = (price / 100).toFixed(2);
    return `${currency || "SGD"} ${formatted}`;
  };

  const formatNumber = (num: number | null) => {
    if (!num) return "N/A";
    return num.toLocaleString();
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

          {/* Product Metadata Card */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <div class="flex flex-col lg:flex-row gap-6">
                {/* Product Image */}
                <div class="flex-shrink-0">
                  {product.image
                    ? (
                      <figure class="w-full lg:w-80 h-80 bg-base-200 rounded-lg overflow-hidden">
                        <img
                          src={product.image}
                          alt={product.name || "Product"}
                          class="w-full h-full object-contain"
                        />
                      </figure>
                    )
                    : (
                      <div class="w-full lg:w-80 h-80 bg-base-200 rounded-lg flex items-center justify-center">
                        <span class="text-base-content/40">No Image</span>
                      </div>
                    )}
                </div>

                {/* Product Info */}
                <div class="flex-1 space-y-4">
                  {/* Title and Source Badge */}
                  <div>
                    <div class="flex items-start gap-3 mb-2">
                      <h1 class="text-2xl lg:text-3xl font-bold flex-1">
                        {product.name || "Unknown Product"}
                      </h1>
                      <div class="badge badge-primary badge-lg">
                        {product.source.toUpperCase()}
                      </div>
                    </div>
                    {product.brand && (
                      <p class="text-base-content/70">
                        Brand: <span class="font-semibold">{product.brand}</span>
                      </p>
                    )}
                  </div>

                  {/* LEGO Set Number */}
                  {product.legoSetNumber && (
                    <div class="badge badge-outline badge-lg">
                      Set #{product.legoSetNumber}
                    </div>
                  )}

                  {/* Pricing */}
                  <div class="space-y-2">
                    <div class="flex items-baseline gap-3">
                      <span class="text-3xl font-bold text-primary">
                        {formatPrice(product.price, product.currency)}
                      </span>
                      {product.priceBeforeDiscount &&
                        product.priceBeforeDiscount > (product.price || 0) && (
                        <span class="text-lg line-through text-base-content/50">
                          {formatPrice(
                            product.priceBeforeDiscount,
                            product.currency,
                          )}
                        </span>
                      )}
                      {discount && (
                        <div class="badge badge-success badge-lg">
                          {discount}% OFF
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Stats Grid - Shopee specific */}
                  {product.source === "shopee" && (
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {product.unitsSold !== null && (
                        <div class="stat bg-base-200 rounded-lg p-3">
                          <div class="stat-title text-xs">Units Sold</div>
                          <div class="stat-value text-xl">
                            {formatNumber(product.unitsSold)}
                          </div>
                        </div>
                      )}
                      {product.view_count !== null && (
                        <div class="stat bg-base-200 rounded-lg p-3">
                          <div class="stat-title text-xs">Views</div>
                          <div class="stat-value text-xl">
                            {formatNumber(product.view_count)}
                          </div>
                        </div>
                      )}
                      {product.liked_count !== null && (
                        <div class="stat bg-base-200 rounded-lg p-3">
                          <div class="stat-title text-xs">Likes</div>
                          <div class="stat-value text-xl">
                            {formatNumber(product.liked_count)}
                          </div>
                        </div>
                      )}
                      {product.avgStarRating !== null && (
                        <div class="stat bg-base-200 rounded-lg p-3">
                          <div class="stat-title text-xs">Rating</div>
                          <div class="stat-value text-xl flex items-center gap-1">
                            {(product.avgStarRating / 10).toFixed(1)}
                            <span class="text-sm">⭐</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Shop Info - Shopee */}
                  {product.source === "shopee" && product.shopName && (
                    <div class="space-y-2">
                      <div class="flex items-center gap-2">
                        <span class="text-base-content/70">Seller:</span>
                        <span class="font-semibold">{product.shopName}</span>
                        {product.isPreferred && (
                          <div class="badge badge-success badge-sm">
                            Preferred
                          </div>
                        )}
                        {product.isMart && (
                          <div class="badge badge-info badge-sm">Mall</div>
                        )}
                      </div>
                      {product.shopLocation && (
                        <div class="text-sm text-base-content/70">
                          Location: {product.shopLocation}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Stock Info */}
                  {product.currentStock !== null && (
                    <div class="flex items-center gap-2">
                      <span class="text-base-content/70">Stock:</span>
                      <span
                        class={`font-semibold ${
                          product.currentStock === 0
                            ? "text-error"
                            : product.currentStock < 10
                            ? "text-warning"
                            : "text-success"
                        }`}
                      >
                        {product.currentStock === 0
                          ? "Out of Stock"
                          : `${formatNumber(product.currentStock)} available`}
                      </span>
                    </div>
                  )}

                  {/* ToysRUs specific - Age Range & Category */}
                  {product.source === "toysrus" && (
                    <div class="flex flex-wrap gap-4">
                      {product.ageRange && (
                        <div>
                          <span class="text-base-content/70">Age: </span>
                          <span class="font-semibold">{product.ageRange}</span>
                        </div>
                      )}
                      {product.categoryName && (
                        <div>
                          <span class="text-base-content/70">Category: </span>
                          <span class="font-semibold">
                            {product.categoryName}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div class="flex flex-wrap gap-3 pt-4">
                    <a
                      href={`/products?search=${product.productId}`}
                      class="btn btn-primary"
                    >
                      View in List
                    </a>
                    {product.legoSetNumber && (
                      <a
                        href={`https://www.bricklink.com/v2/catalog/catalogitem.page?S=${product.legoSetNumber}-1`}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn btn-outline"
                      >
                        View on Bricklink ↗
                      </a>
                    )}
                  </div>

                  {/* Last Updated */}
                  <div class="text-xs text-base-content/50">
                    Last updated:{" "}
                    {new Date(product.updatedAt).toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Investment Analysis Section */}
          {product.legoSetNumber && (
            <div>
              <h2 class="text-2xl font-bold mb-4">Investment Analysis</h2>
              <ProductAnalysisCard
                productId={product.productId}
                defaultStrategy="Investment Focus"
              />
            </div>
          )}

          {!product.legoSetNumber && (
            <div class="alert alert-info">
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
                Investment analysis is only available for products with a valid LEGO set number.
              </span>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

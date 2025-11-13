import { useSignal } from "@preact/signals";
import { formatDelta, formatPrice, formatSold } from "../utils/formatters.ts";
import { getSoldStyle } from "../constants/app-config.ts";

type Platform = "shopee" | "toysrus" | "brickeconomy";

interface Product {
  id: number;
  productId: string;
  name: string;
  price: number | null;
  sold: number | null;
  legoSetNumber: string | null;
  shopName?: string;
  image?: string;
  brand?: string;
  sku?: string;
  wasUpdated?: boolean;
  isNew?: boolean;
  previousSold?: number | null;
  previousPrice?: number | null;
  soldDelta?: number | null;
  priceDelta?: number | null;
  priceChangePercent?: number | null;
  createdAt?: string;
  updatedAt?: string;
}

interface ParseResult {
  success: boolean;
  session_id: number;
  status: "success" | "partial" | "failed";
  products_found: number;
  products_stored: number;
  products: Product[];
  error?: string;
}

interface ProductNeedingValidation {
  productName: string;
  price: number | null;
  priceString?: string;
  unitsSold?: number | null;
  unitsSoldString?: string;
  priceBeforeDiscount?: number | null;
  image?: string | null;
  productUrl?: string | null;
  shopName?: string | null;
  brand?: string | null;
  sku?: string | null;
  _originalData: Record<string, unknown>;
}

interface ValidationResponse {
  success: boolean;
  requiresValidation: boolean;
  session_id: number;
  alreadySaved: Product[];
  productsNeedingValidation: ProductNeedingValidation[];
  message: string;
}

const PLATFORM_CONFIG = {
  shopee: {
    name: "Shopee",
    apiEndpoint: "/api/parse-shopee",
    urlLabel: "Shopee Shop URL",
    urlPlaceholder: "https://shopee.com.my/legoshopmy?shopCollection=...",
    urlRequired: true,
    urlHelp: "Required to extract shop name",
    description:
      "Paste the HTML content from a Shopee product listing page to extract and store product data",
  },
  toysrus: {
    name: 'Toys"R"Us',
    apiEndpoint: "/api/parse-toysrus",
    urlLabel: 'Toys"R"Us Page URL',
    urlPlaceholder: "https://www.toysrus.com.my/search?q=lego",
    urlRequired: false,
    urlHelp: "Optional - for reference",
    description:
      'Paste the HTML content from a Toys"R"Us product listing page to extract and store product data',
  },
  brickeconomy: {
    name: "BrickEconomy",
    apiEndpoint: "/api/parse-brickeconomy",
    urlLabel: "BrickEconomy Page URL",
    urlPlaceholder: "https://www.brickeconomy.com/set/76917-1/...",
    urlRequired: false,
    urlHelp: "Optional - for reference",
    description:
      "Paste the HTML content from a BrickEconomy product detail page to extract comprehensive LEGO set data including pricing, investment metrics, and predictions",
  },
};

export default function UnifiedParser() {
  const platform = useSignal<Platform>("shopee");
  const htmlContent = useSignal("");
  const sourceUrl = useSignal("");
  const isLoading = useSignal(false);
  const result = useSignal<ParseResult | null>(null);
  const error = useSignal<string | null>(null);

  // Validation state
  const showValidationModal = useSignal(false);
  const productsNeedingValidation = useSignal<ProductNeedingValidation[]>([]);
  const currentValidationIndex = useSignal(0);
  const manualLegoId = useSignal("");
  const isSaving = useSignal(false);
  const sessionId = useSignal<number | null>(null);
  const alreadySavedProducts = useSignal<Product[]>([]);
  const validatedProducts = useSignal<Product[]>([]);

  const config = PLATFORM_CONFIG[platform.value];

  const handleSubmit = async (e: Event) => {
    e.preventDefault();

    // Validation
    if (!htmlContent.value.trim()) {
      error.value = "Please paste HTML content before submitting";
      return;
    }

    if (config.urlRequired && !sourceUrl.value.trim()) {
      error.value = "Source URL is required for " + config.name;
      return;
    }

    // Reset previous results
    result.value = null;
    error.value = null;
    isLoading.value = true;

    try {
      const response = await fetch(config.apiEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          html: htmlContent.value,
          source_url: sourceUrl.value.trim() || undefined,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `Server error: ${response.status}`);
      }

      // Check if validation is required
      if (data.requiresValidation && data.productsNeedingValidation) {
        sessionId.value = data.session_id;
        alreadySavedProducts.value = data.alreadySaved || [];
        validatedProducts.value = []; // Reset validated products array
        productsNeedingValidation.value = data.productsNeedingValidation;
        currentValidationIndex.value = 0;
        showValidationModal.value = true;
        error.value = data.message || "Some products need LEGO ID validation";
      } else {
        result.value = data;
      }
    } catch (err) {
      error.value = err instanceof Error
        ? err.message
        : "Failed to parse HTML. Please check your connection and try again.";
    } finally {
      isLoading.value = false;
    }
  };

  const handleReset = () => {
    htmlContent.value = "";
    sourceUrl.value = "";
    result.value = null;
    error.value = null;
  };

  const handlePlatformChange = (newPlatform: Platform) => {
    platform.value = newPlatform;
    // Clear results when switching platforms
    result.value = null;
    error.value = null;
  };

  const handleCancelValidation = () => {
    showValidationModal.value = false;
    productsNeedingValidation.value = [];
    currentValidationIndex.value = 0;
    manualLegoId.value = "";
    error.value = null; // Clear error instead of showing cancellation message
  };

  const _handleSkipProduct = () => {
    // Move to next product or close modal if done
    if (
      currentValidationIndex.value < productsNeedingValidation.value.length - 1
    ) {
      currentValidationIndex.value++;
      manualLegoId.value = "";
    } else {
      handleCancelValidation();
    }
  };

  const handleSaveWithLegoId = async () => {
    const legoId = manualLegoId.value.trim();

    // Validate LEGO ID format
    if (!/^\d{5}$/.test(legoId)) {
      error.value = "LEGO ID must be exactly 5 digits";
      return;
    }

    const currentProduct =
      productsNeedingValidation.value[currentValidationIndex.value];
    if (!currentProduct) return;

    isSaving.value = true;
    error.value = null;

    try {
      // Prepare product data based on platform
      const productData = platform.value === "shopee"
        ? {
          source: "shopee",
          productId: currentProduct._originalData.product_id,
          name: currentProduct._originalData.product_name,
          currency: "MYR",
          price: currentProduct._originalData.price,
          unitsSold: currentProduct._originalData.units_sold,
          legoSetNumber: legoId,
          shopId: currentProduct._originalData.shop_id,
          shopName: currentProduct._originalData.shop_name,
          image: currentProduct._originalData.image,
          rawData: {
            product_url: currentProduct._originalData.product_url,
            price_string: currentProduct._originalData.price_string,
            units_sold_string: currentProduct._originalData.units_sold_string,
          },
        }
        : {
          source: "toysrus",
          productId: currentProduct._originalData.productId,
          name: currentProduct._originalData.name,
          brand: currentProduct._originalData.brand,
          currency: "MYR",
          price: currentProduct._originalData.price,
          priceBeforeDiscount: currentProduct._originalData.priceBeforeDiscount,
          image: currentProduct._originalData.image,
          legoSetNumber: legoId,
          sku: currentProduct._originalData.sku,
          categoryNumber: currentProduct._originalData.categoryNumber,
          categoryName: currentProduct._originalData.categoryName,
          ageRange: currentProduct._originalData.ageRange,
          rawData: {
            product_url: currentProduct._originalData.productUrl,
            ...(currentProduct._originalData.rawData as Record<string, unknown> || {}),
          },
        };

      const response = await fetch("/api/products/validate-and-save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(productData),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Failed to save product");
      }

      // Add validated product to accumulator
      validatedProducts.value = [...validatedProducts.value, data.product];

      // Move to next product or close modal if done
      if (
        currentValidationIndex.value <
          productsNeedingValidation.value.length - 1
      ) {
        currentValidationIndex.value++;
        manualLegoId.value = "";
      } else {
        // All products validated, close modal and show complete summary
        showValidationModal.value = false;
        productsNeedingValidation.value = [];
        currentValidationIndex.value = 0;
        manualLegoId.value = "";
        error.value = null;

        // Combine already saved products with validated products
        const allProducts = [
          ...alreadySavedProducts.value,
          ...validatedProducts.value,
        ];

        result.value = {
          success: true,
          session_id: sessionId.value || -1,
          status: "success",
          products_found: allProducts.length,
          products_stored: allProducts.length,
          products: allProducts,
        };

        // Clear validation state
        sessionId.value = null;
        alreadySavedProducts.value = [];
        validatedProducts.value = [];
      }
    } catch (err) {
      error.value = err instanceof Error
        ? err.message
        : "Failed to save product";
    } finally {
      isSaving.value = false;
    }
  };

  const currentProduct =
    productsNeedingValidation.value[currentValidationIndex.value];

  return (
    <div class="w-full max-w-6xl mx-auto space-y-6">
      {/* Form Card */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title text-2xl">Multi-Platform Product Parser</h2>

          {/* Platform Selector */}
          <div class="form-control mb-4">
            <label class="label">
              <span class="label-text font-medium">Select Platform</span>
            </label>
            <div class="flex gap-4">
              <label class="label cursor-pointer gap-2">
                <input
                  type="radio"
                  name="platform"
                  class="radio radio-primary"
                  checked={platform.value === "shopee"}
                  onChange={() => handlePlatformChange("shopee")}
                  disabled={isLoading.value}
                />
                <span class="label-text">Shopee</span>
              </label>
              <label class="label cursor-pointer gap-2">
                <input
                  type="radio"
                  name="platform"
                  class="radio radio-primary"
                  checked={platform.value === "toysrus"}
                  onChange={() => handlePlatformChange("toysrus")}
                  disabled={isLoading.value}
                />
                <span class="label-text">Toys"R"Us</span>
              </label>
            </div>
          </div>

          <p class="text-sm opacity-70">
            {config.description}
          </p>

          <form onSubmit={handleSubmit} class="space-y-4 mt-4">
            {/* HTML Content Input */}
            <div class="form-control">
              <label class="label">
                <span class="label-text font-medium">HTML Content *</span>
              </label>
              <textarea
                class="textarea textarea-bordered h-40 font-mono text-sm"
                placeholder="Paste HTML element here..."
                value={htmlContent.value}
                onInput={(e) => htmlContent.value = e.currentTarget.value}
                disabled={isLoading.value}
              />
            </div>

            {/* Source URL Input */}
            <div class="form-control">
              <label class="label">
                <span class="label-text font-medium">
                  {config.urlLabel} {config.urlRequired ? "*" : ""}
                </span>
                <span class="label-text-alt opacity-70">
                  {config.urlHelp}
                </span>
              </label>
              <input
                type="url"
                class="input input-bordered"
                placeholder={config.urlPlaceholder}
                value={sourceUrl.value}
                onInput={(e) => sourceUrl.value = e.currentTarget.value}
                disabled={isLoading.value}
                required={config.urlRequired}
              />
            </div>

            {/* Action Buttons */}
            <div class="card-actions justify-end gap-2">
              <button
                type="button"
                class="btn btn-ghost"
                onClick={handleReset}
                disabled={isLoading.value}
              >
                Clear
              </button>
              <button
                type="submit"
                class="btn btn-primary"
                disabled={isLoading.value}
              >
                {isLoading.value
                  ? (
                    <>
                      <span class="loading loading-spinner loading-sm"></span>
                      Parsing...
                    </>
                  )
                  : (
                    "Parse & Store"
                  )}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Error Alert */}
      {error.value && (
        <div class="alert alert-error">
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
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>{error.value}</span>
        </div>
      )}

      {/* Success/Partial Result Alert */}
      {result.value && (
        <>
          {result.value.status === "success"
            ? (
              <div class="alert alert-success">
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
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <div class="font-bold">Successfully parsed and stored!</div>
                  <div class="text-sm">
                    Session ID: {result.value.session_id} | Products:{" "}
                    {result.value.products_stored}/{result.value.products_found}
                    {" "}
                    stored
                  </div>
                </div>
              </div>
            )
            : result.value.status === "partial"
            ? (
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
                  <div class="font-bold">Partially successful</div>
                  <div class="text-sm">
                    Session ID: {result.value.session_id} | Products:{" "}
                    {result.value.products_stored}/{result.value.products_found}
                    {" "}
                    stored (some products failed to save)
                  </div>
                </div>
              </div>
            )
            : (
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
                  />
                </svg>
                <div>
                  <div class="font-bold">No products found</div>
                  <div class="text-sm">
                    Session ID: {result.value.session_id}{" "}
                    | The HTML content didn't contain any recognizable product
                    listings
                  </div>
                </div>
              </div>
            )}

          {/* Products Table */}
          {result.value.products && result.value.products.length > 0 && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body p-0">
                <div class="overflow-x-auto">
                  <table class="table">
                    <thead>
                      <tr class="border-b border-base-300">
                        <th class="bg-base-200">Status</th>
                        <th class="bg-base-200">Image</th>
                        <th class="bg-base-200">Product</th>
                        <th class="bg-base-200">Set #</th>
                        <th class="bg-base-200">Price</th>
                        {platform.value === "shopee" && (
                          <th class="bg-base-200">Sold</th>
                        )}
                        <th class="bg-base-200">
                          {platform.value === "shopee" ? "Shop" : "SKU"}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.value.products.map((product) => {
                        const soldDelta = formatDelta(
                          product.soldDelta || null,
                          "sold",
                        );
                        const priceDelta = formatDelta(
                          product.priceDelta || null,
                          "price",
                        );

                        // Determine row background color based on price change
                        const isPriceDrop = product.priceDelta && product.priceDelta < 0;
                        const isPriceIncrease = product.priceDelta && product.priceDelta > 0;
                        const rowBgClass = product.isNew
                          ? "bg-warning/10 hover:bg-warning/20"
                          : isPriceDrop
                          ? "bg-success/10 hover:bg-success/20"
                          : isPriceIncrease
                          ? "bg-error/10 hover:bg-error/20"
                          : "hover:bg-base-200/50";

                        return (
                          <tr
                            key={product.id}
                            class={`${rowBgClass} transition-colors`}
                          >
                            <td class="py-3">
                              {product.isNew
                                ? (
                                  <span class="badge badge-warning badge-sm gap-1 font-semibold">
                                    ⚡ New
                                  </span>
                                )
                                : isPriceDrop
                                ? (
                                  <span class="badge badge-success badge-sm gap-1 font-semibold">
                                    🔻 Drop
                                  </span>
                                )
                                : isPriceIncrease
                                ? (
                                  <span class="badge badge-error badge-sm gap-1 font-semibold">
                                    🔺 Up
                                  </span>
                                )
                                : (
                                  <span class="badge badge-ghost badge-sm gap-1">
                                    —
                                  </span>
                                )}
                            </td>
                            <td class="py-3">
                              {product.image
                                ? (
                                  <div class="avatar">
                                    <div class="w-16 h-16 rounded-lg">
                                      <img
                                        src={product.image}
                                        alt={product.name || "Product"}
                                        class="object-cover"
                                      />
                                    </div>
                                  </div>
                                )
                                : (
                                  <div class="w-16 h-16 bg-base-300 rounded-lg flex items-center justify-center">
                                    <svg
                                      xmlns="http://www.w3.org/2000/svg"
                                      class="h-8 w-8 opacity-30"
                                      fill="none"
                                      viewBox="0 0 24 24"
                                      stroke="currentColor"
                                    >
                                      <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                                      />
                                    </svg>
                                  </div>
                                )}
                            </td>
                            <td class="py-3">
                              <div class="max-w-xs">
                                <div
                                  class="font-medium text-sm leading-tight line-clamp-2"
                                  title={product.name || undefined}
                                >
                                  {product.name || "N/A"}
                                </div>
                                {product.brand && (
                                  <div class="text-xs text-base-content/60 mt-1">
                                    {product.brand}
                                  </div>
                                )}
                              </div>
                            </td>
                            <td class="py-3">
                              {product.legoSetNumber
                                ? (
                                  <span class="badge badge-primary badge-sm">
                                    {product.legoSetNumber}
                                  </span>
                                )
                                : <span class="text-xs opacity-40">—</span>}
                            </td>
                            <td class="py-3">
                              <div class="flex items-center gap-2">
                                <div class="font-semibold text-base">
                                  {formatPrice(product.price)}
                                </div>
                                {product.priceChangePercent !== null && product.priceChangePercent !== undefined && (
                                  <span
                                    class={`badge badge-sm font-bold ${
                                      product.priceChangePercent < 0
                                        ? product.priceChangePercent <= -20
                                          ? "badge-success"
                                          : product.priceChangePercent <= -10
                                          ? "bg-success/70 text-success-content"
                                          : "bg-success/40 text-success-content"
                                        : "badge-error"
                                    }`}
                                  >
                                    {product.priceChangePercent > 0 ? "+" : ""}
                                    {product.priceChangePercent}%
                                  </span>
                                )}
                              </div>
                              {priceDelta && (
                                <div
                                  class={`text-xs font-medium mt-0.5 ${
                                    priceDelta.isPositive
                                      ? "text-error"
                                      : "text-success"
                                  }`}
                                >
                                  {priceDelta.text}
                                </div>
                              )}
                            </td>
                            {platform.value === "shopee" && (
                              <td class="py-3">
                                <div
                                  class="text-base"
                                  style={getSoldStyle(product.sold)}
                                >
                                  {formatSold(product.sold)}
                                </div>
                                {soldDelta && (
                                  <div
                                    class={`text-xs font-medium mt-0.5 ${
                                      soldDelta.isPositive
                                        ? "text-success"
                                        : "text-error"
                                    }`}
                                  >
                                    {soldDelta.text}
                                  </div>
                                )}
                              </td>
                            )}
                            <td class="py-3">
                              <span class="text-sm font-medium opacity-70">
                                {platform.value === "shopee"
                                  ? (product.shopName || "—")
                                  : (product.sku || "—")}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* LEGO ID Validation Modal */}
      {showValidationModal.value && currentProduct && (
        <div class="modal modal-open">
          <div class="modal-box max-w-2xl">
            <h3 class="font-bold text-lg mb-4">
              LEGO ID Required ({currentValidationIndex.value + 1} of{" "}
              {productsNeedingValidation.value.length})
            </h3>

            <div class="space-y-4">
              {/* Product Info */}
              <div class="flex gap-4 p-4 bg-base-200 rounded-lg">
                {currentProduct.image && (
                  <div class="avatar">
                    <div class="w-24 h-24 rounded-lg">
                      <img
                        src={currentProduct.image}
                        alt={currentProduct.productName}
                        class="object-cover"
                      />
                    </div>
                  </div>
                )}
                <div class="flex-1">
                  <div class="font-medium text-sm mb-2">
                    {currentProduct.productName}
                  </div>
                  <div class="text-sm text-base-content/60">
                    Price: {formatPrice(currentProduct.price)}
                  </div>
                  {currentProduct.shopName && (
                    <div class="text-sm text-base-content/60">
                      Shop: {currentProduct.shopName}
                    </div>
                  )}
                  {currentProduct.brand && (
                    <div class="text-sm text-base-content/60">
                      Brand: {currentProduct.brand}
                    </div>
                  )}
                </div>
              </div>

              {/* LEGO ID Input */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text font-medium">
                    Enter 5-digit LEGO Set Number *
                  </span>
                </label>
                <input
                  type="text"
                  class="input input-bordered"
                  placeholder="e.g., 10295"
                  value={manualLegoId.value}
                  onInput={(e) => manualLegoId.value = e.currentTarget.value}
                  maxLength={5}
                  disabled={isSaving.value}
                  autoFocus
                />
                <label class="label">
                  <span class="label-text-alt text-warning">
                    LEGO ID not found in product name. Please enter manually or
                    cancel to skip.
                  </span>
                </label>
              </div>

              {/* Action Buttons */}
              <div class="modal-action">
                <button
                  type="button"
                  class="btn btn-ghost"
                  onClick={handleCancelValidation}
                  disabled={isSaving.value}
                >
                  Cancel All
                </button>
                <button
                  type="button"
                  class="btn btn-primary"
                  onClick={handleSaveWithLegoId}
                  disabled={isSaving.value || !manualLegoId.value.trim()}
                >
                  {isSaving.value
                    ? (
                      <>
                        <span class="loading loading-spinner loading-sm"></span>
                        Saving...
                      </>
                    )
                    : (
                      "Save Product"
                    )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

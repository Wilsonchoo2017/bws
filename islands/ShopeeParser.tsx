import { useSignal } from "@preact/signals";
import { formatDelta, formatPrice, formatSold } from "../utils/formatters.ts";
import { getSoldStyle } from "../constants/app-config.ts";

interface ShopeeProduct {
  id: number;
  productId: string;
  name: string;
  price: number | null;
  sold: number | null;
  legoSetNumber: string | null;
  shopName?: string;
  image?: string;
  wasUpdated?: boolean;
  previousSold?: number | null;
  previousPrice?: number | null;
  soldDelta?: number | null;
  priceDelta?: number | null;
  createdAt?: string;
  updatedAt?: string;
}

interface ParseResult {
  success: boolean;
  session_id: number;
  status: "success" | "partial" | "failed";
  products_found: number;
  products_stored: number;
  products: ShopeeProduct[];
  error?: string;
}

export default function ShopeeParser() {
  const htmlContent = useSignal("");
  const sourceUrl = useSignal("");
  const isLoading = useSignal(false);
  const result = useSignal<ParseResult | null>(null);
  const error = useSignal<string | null>(null);

  const handleSubmit = async (e: Event) => {
    e.preventDefault();

    // Validation
    if (!htmlContent.value.trim()) {
      error.value = "Please paste HTML content before submitting";
      return;
    }

    // Reset previous results
    result.value = null;
    error.value = null;
    isLoading.value = true;

    try {
      const response = await fetch("/api/parse-shopee", {
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

      result.value = data;
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

  return (
    <div class="w-full max-w-6xl mx-auto space-y-6">
      {/* Form Card */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title text-2xl">Shopee HTML Parser</h2>
          <p class="text-sm opacity-70">
            Paste the HTML content from a Shopee product listing page to extract
            and store product data
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
                <span class="label-text font-medium">Source URL *</span>
                <span class="label-text-alt opacity-70">
                  Required to extract shop name
                </span>
              </label>
              <input
                type="url"
                class="input input-bordered"
                placeholder="https://shopee.com.my/legoshopmy?shopCollection=..."
                value={sourceUrl.value}
                onInput={(e) => sourceUrl.value = e.currentTarget.value}
                disabled={isLoading.value}
                required
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
                        <th class="bg-base-200">Sold</th>
                        <th class="bg-base-200">Shop</th>
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

                        return (
                          <tr
                            key={product.id}
                            class="hover:bg-base-200/50 transition-colors"
                          >
                            <td class="py-3">
                              {product.wasUpdated
                                ? (
                                  <span class="badge badge-info badge-sm gap-1">
                                    <svg
                                      xmlns="http://www.w3.org/2000/svg"
                                      class="h-3 w-3"
                                      viewBox="0 0 20 20"
                                      fill="currentColor"
                                    >
                                      <path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" />
                                      <path
                                        fill-rule="evenodd"
                                        d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z"
                                        clip-rule="evenodd"
                                      />
                                    </svg>
                                    Updated
                                  </span>
                                )
                                : (
                                  <span class="badge badge-success badge-sm gap-1">
                                    <svg
                                      xmlns="http://www.w3.org/2000/svg"
                                      class="h-3 w-3"
                                      viewBox="0 0 20 20"
                                      fill="currentColor"
                                    >
                                      <path
                                        fill-rule="evenodd"
                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z"
                                        clip-rule="evenodd"
                                      />
                                    </svg>
                                    New
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
                              <div class="font-semibold text-base">
                                {formatPrice(product.price)}
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
                            <td class="py-3">
                              <span class="text-sm font-medium opacity-70">
                                {product.shopName || "—"}
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
    </div>
  );
}

import { useSignal } from "@preact/signals";

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

  const formatPrice = (priceInCents: number | null) => {
    if (priceInCents === null) return "N/A";
    return `RM ${(priceInCents / 100).toFixed(2)}`;
  };

  const formatSold = (sold: number | null) => {
    if (sold === null) return "N/A";
    if (sold >= 1000) return `${(sold / 1000).toFixed(1)}k`;
    return sold.toString();
  };

  const formatDelta = (delta: number | null, type: "sold" | "price") => {
    if (delta === null || delta === 0) return null;

    const isPositive = delta > 0;
    const prefix = isPositive ? "+" : "";

    if (type === "sold") {
      const formatted = delta >= 1000 ? `${(delta / 1000).toFixed(1)}k` : delta.toString();
      return { text: `${prefix}${formatted}`, isPositive };
    } else {
      const formatted = (delta / 100).toFixed(2);
      return { text: `${prefix}RM ${formatted}`, isPositive };
    }
  };

  const getSoldColorClass = (sold: number | null) => {
    if (sold === null || sold === 0) return "";

    // Color thresholds based on sold units
    // Using !important via Tailwind's ! prefix to override DaisyUI styles
    if (sold >= 10000) return "!text-purple-600 font-bold"; // 10k+ - Purple (Viral)
    if (sold >= 5000) return "!text-red-600 font-bold";    // 5k-10k - Red (Hot)
    if (sold >= 1000) return "!text-orange-600 font-semibold"; // 1k-5k - Orange (Popular)
    if (sold >= 500) return "!text-yellow-600 font-medium";    // 500-1k - Yellow (Selling)
    if (sold >= 100) return "!text-green-600";             // 100-500 - Green (Moderate)
    return "";                                             // <100 - Default
  };

  return (
    <div class="w-full max-w-6xl mx-auto space-y-6">
      {/* Form Card */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title text-2xl">Shopee HTML Parser</h2>
          <p class="text-sm opacity-70">
            Paste the HTML content from a Shopee product listing page to extract and store product data
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
                <span class="label-text-alt opacity-70">Required to extract shop name</span>
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
                {isLoading.value ? (
                  <>
                    <span class="loading loading-spinner loading-sm"></span>
                    Parsing...
                  </>
                ) : (
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
          {result.value.status === "success" ? (
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
                  Session ID: {result.value.session_id} |
                  Products: {result.value.products_stored}/{result.value.products_found} stored
                </div>
              </div>
            </div>
          ) : result.value.status === "partial" ? (
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
                  Session ID: {result.value.session_id} |
                  Products: {result.value.products_stored}/{result.value.products_found} stored
                  (some products failed to save)
                </div>
              </div>
            </div>
          ) : (
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
                  Session ID: {result.value.session_id} |
                  The HTML content didn't contain any recognizable product listings
                </div>
              </div>
            </div>
          )}

          {/* Products Table */}
          {result.value.products && result.value.products.length > 0 && (
            <div class="card bg-base-100 shadow-xl">
              <div class="card-body">
                <h3 class="card-title">Stored Products ({result.value.products.length})</h3>

                <div class="overflow-x-auto">
                  <table class="table table-zebra">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>Image</th>
                        <th>Product Name</th>
                        <th>LEGO Set</th>
                        <th>Price</th>
                        <th>Sold</th>
                        <th>Shop</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.value.products.map((product) => {
                        const soldDelta = formatDelta(product.soldDelta || null, "sold");
                        const priceDelta = formatDelta(product.priceDelta || null, "price");

                        return (
                          <tr key={product.id}>
                            <td>
                              {product.wasUpdated ? (
                                <span class="badge badge-info badge-sm">Updated</span>
                              ) : (
                                <span class="badge badge-success badge-sm">New</span>
                              )}
                            </td>
                            <td>
                              {product.image ? (
                                <div class="avatar">
                                  <div class="w-12 h-12 rounded">
                                    <img src={product.image} alt={product.name || "Product"} />
                                  </div>
                                </div>
                              ) : (
                                <div class="w-12 h-12 bg-base-300 rounded flex items-center justify-center">
                                  <span class="text-xs opacity-50">No img</span>
                                </div>
                              )}
                            </td>
                            <td>
                              <div class="font-medium max-w-xs truncate" title={product.name || undefined}>
                                {product.name || "N/A"}
                              </div>
                              <div class="text-xs opacity-50">ID: {product.productId}</div>
                            </td>
                            <td>
                              {product.legoSetNumber ? (
                                <span class="badge badge-primary">{product.legoSetNumber}</span>
                              ) : (
                                <span class="text-xs opacity-50">—</span>
                              )}
                            </td>
                            <td>
                              <div class="font-semibold">{formatPrice(product.price)}</div>
                              {priceDelta && (
                                <div
                                  class={`text-xs ${
                                    priceDelta.isPositive ? "text-error" : "text-success"
                                  }`}
                                >
                                  {priceDelta.text}
                                </div>
                              )}
                            </td>
                            <td>
                              <div class={getSoldColorClass(product.sold)}>
                                {formatSold(product.sold)}
                              </div>
                              {soldDelta && (
                                <div
                                  class={`text-xs ${
                                    soldDelta.isPositive ? "text-success" : "text-error"
                                  }`}
                                >
                                  {soldDelta.text}
                                </div>
                              )}
                            </td>
                            <td class="text-sm opacity-70">{product.shopName || "—"}</td>
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

/**
 * Utility functions for data normalization and conversion
 */

/**
 * Converts a price string (e.g., "RM 150.50", "RM150.50", "150.50") to cents (bigint)
 * @param priceStr - Price string with or without currency symbol
 * @returns Price in cents as a number, or null if invalid
 */
export function parsePriceToCents(priceStr: string): number | null {
  if (!priceStr || priceStr === "N/A") return null;

  // Remove currency symbols and whitespace
  const cleanPrice = priceStr
    .replace(/RM/gi, "")
    .replace(/\$/g, "")
    .replace(/,/g, "")
    .trim();

  const price = parseFloat(cleanPrice);
  if (isNaN(price)) return null;

  // Convert to cents (multiply by 100)
  return Math.round(price * 100);
}

/**
 * Normalizes sold units string (e.g., "1.5k", "500", "2K", "1.2k+") to a number
 * @param soldStr - Sold units string
 * @returns Normalized number of units sold, or null if invalid
 */
export function normalizeSoldUnits(soldStr: string): number | null {
  if (!soldStr || soldStr === "N/A") return null;

  // Remove "+" sign and whitespace
  const cleaned = soldStr.replace(/\+/g, "").trim().toLowerCase();

  // Check for 'k' suffix (thousands)
  if (cleaned.includes("k")) {
    const num = parseFloat(cleaned.replace("k", ""));
    if (isNaN(num)) return null;
    return Math.round(num * 1000);
  }

  // Parse as regular number
  const num = parseFloat(cleaned.replace(/,/g, ""));
  return isNaN(num) ? null : Math.round(num);
}

/**
 * Extracts product ID from a Shopee URL or product link
 * @param url - Full Shopee product URL or path
 * @returns Product ID string, or null if not found
 * @example
 * extractShopeeProductId("https://shopee.com.my/product/123456/7890123456")
 * // Returns "123456-7890123456"
 */
export function extractShopeeProductId(url: string): string | null {
  if (!url) return null;

  // Pattern: /shop_id/item_id or ?itemid=...&shopid=...
  const pathMatch = url.match(/\/(\d+)\/(\d+)/);
  if (pathMatch) {
    return `${pathMatch[1]}-${pathMatch[2]}`; // shop_id-item_id
  }

  // Alternative pattern from query params
  const itemIdMatch = url.match(/[?&]itemid=(\d+)/i);
  const shopIdMatch = url.match(/[?&]shopid=(\d+)/i);
  if (itemIdMatch && shopIdMatch) {
    return `${shopIdMatch[1]}-${itemIdMatch[1]}`;
  }

  return null;
}

/**
 * Extracts LEGO set number from product name
 * @param productName - Product name string
 * @returns LEGO set number (5 digits) or null if not found
 */
export function extractLegoSetNumber(productName: string): string | null {
  if (!productName) return null;

  const match = productName.match(/\b(\d{5})\b/);
  return match ? match[1] : null;
}

/**
 * Generates a unique product ID from product name if URL-based ID is not available
 * Uses product name hash as fallback
 * @param productName - Product name
 * @returns Generated product ID
 */
export function generateProductIdFromName(productName: string): string {
  // Simple hash function for fallback ID generation
  let hash = 0;
  for (let i = 0; i < productName.length; i++) {
    const char = productName.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return `gen-${Math.abs(hash)}`;
}

/**
 * Extracts shop username from a Shopee shop URL
 * @param url - Shopee shop URL
 * @returns Shop username string, or null if not found
 * @example
 * extractShopUsername("https://shopee.com.my/legoshopmy?shopCollection=262908470")
 * // Returns "legoshopmy"
 */
export function extractShopUsername(url: string): string | null {
  if (!url) return null;

  try {
    const urlObj = new URL(url);
    const pathname = urlObj.pathname;

    // Extract username from path: /username or /username/...
    // Skip common non-shop paths
    const skipPaths = ["/product", "/search", "/cart", "/checkout", "/account"];

    const pathMatch = pathname.match(/^\/([^/?#]+)/);
    if (pathMatch && pathMatch[1]) {
      const username = pathMatch[1];
      // Check if it's not a common non-shop path
      if (!skipPaths.includes(`/${username}`)) {
        return username;
      }
    }
  } catch (_error) {
    // Invalid URL, return null
    return null;
  }

  return null;
}

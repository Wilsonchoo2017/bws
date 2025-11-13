import { formatDate, formatNumber, formatPrice } from "../../utils/formatters.ts";
import {
  getProductPlatformBadgeClass,
  getProductPlatformLabel,
  getSoldBadgeColor,
} from "../../utils/product-helpers.ts";
import type { Product } from "../../hooks/useProductList.ts";
import type { ProductSource } from "../../db/schema.ts";

interface ProductTableRowProps {
  product: Product;
  sourceFilter: ProductSource | "all";
}

/**
 * Individual product table row component.
 * Displays product information including platform, image, name, pricing, and metadata.
 * Follows Single Responsibility Principle - only handles rendering a single product row.
 */
export function ProductTableRow({ product, sourceFilter }: ProductTableRowProps) {
  return (
    <tr key={product.id}>
      {/* Platform Badge */}
      <td>
        <span
          class={`badge badge-sm ${getProductPlatformBadgeClass(product.source)}`}
        >
          {getProductPlatformLabel(product.source)}
        </span>
      </td>

      {/* Product Image */}
      <td>
        {product.image
          ? (
            <div class="avatar">
              <div class="w-16 rounded">
                <img
                  src={product.image}
                  alt={product.name || "Product"}
                  loading="lazy"
                />
              </div>
            </div>
          )
          : (
            <div class="w-16 h-16 bg-base-300 rounded flex items-center justify-center">
              <span class="text-xs text-base-content/50">
                No image
              </span>
            </div>
          )}
      </td>

      {/* Product Name and Brand */}
      <td class="max-w-xs">
        <a
          href={`/products/${product.productId}`}
          class="font-medium line-clamp-2 link link-hover text-primary"
        >
          {product.name || "Unnamed product"}
        </a>
        {product.brand && (
          <div class="text-xs text-base-content/60 mt-1">
            {product.brand}
          </div>
        )}
      </td>

      {/* LEGO Set Number */}
      <td>
        {product.legoSetNumber
          ? (
            <span class="badge badge-primary">
              {product.legoSetNumber}
            </span>
          )
          : <span class="text-base-content/50">—</span>}
      </td>

      {/* Bricklink Data Availability */}
      <td>
        <span
          class={`badge badge-sm ${
            product.hasBricklinkData ? "badge-success" : "badge-ghost"
          }`}
        >
          {product.hasBricklinkData ? "Available" : "Missing"}
        </span>
      </td>

      {/* Price */}
      <td>
        <div class="font-semibold">{formatPrice(product.price)}</div>
        {product.priceBeforeDiscount &&
          product.priceBeforeDiscount > (product.price || 0) && (
          <div class="text-xs text-base-content/50 line-through">
            {formatPrice(product.priceBeforeDiscount)}
          </div>
        )}
      </td>

      {/* Units Sold (conditional - not shown for ToysRUs) */}
      {sourceFilter !== "toysrus" && (
        <td>
          <span
            class={`badge ${getSoldBadgeColor(product.unitsSold)}`}
          >
            {formatNumber(product.unitsSold)}
          </span>
        </td>
      )}

      {/* Shop Info / SKU */}
      <td>
        {product.source === "shopee"
          ? (
            <>
              <div class="text-sm">
                {product.shopName || "Unknown"}
              </div>
              {product.shopLocation && (
                <div class="text-xs text-base-content/50">
                  {product.shopLocation}
                </div>
              )}
            </>
          )
          : (
            <div class="text-sm font-mono">
              {product.sku || "—"}
            </div>
          )}
      </td>

      {/* Updated Date */}
      <td class="text-sm text-base-content/70">
        {formatDate(product.updatedAt)}
      </td>
    </tr>
  );
}

/**
 * Behavior-focused tests for Shopee HTML parser
 * Tests WHAT the parser does (outputs), not HOW it does it (implementation)
 */

import { assertEquals, assertExists } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { type Element } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import {
  parseHtmlDocument,
  parseProductItem,
  parseShopeeHtml,
} from "./shopee-extractors.ts";
import {
  EMPTY_HTML,
  EXPECTED_PRODUCT_1,
  EXPECTED_PRODUCT_2,
  PRODUCT_MINIMAL,
  PRODUCT_WITH_DISCOUNT_AND_BADGES,
  PRODUCT_WITH_NUMERIC_SOLD,
  PRODUCT_WITHOUT_SET_NUMBER,
  SAMPLE_SHOPEE_HTML,
} from "./shopee-extractors.fixtures.ts";

// ============================================================================
// Integration Tests - Full parsing behavior
// ============================================================================

Deno.test("parseShopeeHtml - should extract all products from valid HTML with multiple items", () => {
  // Arrange: HTML with 2 complete products
  const shopUsername = "legoshopmy";

  // Act: Parse the full HTML
  const products = parseShopeeHtml(SAMPLE_SHOPEE_HTML, shopUsername);

  // Assert: Verify we got 2 products
  assertEquals(products.length, 2, "Should parse 2 products from the HTML");

  // Verify first product (excluding randomly generated product_id)
  const product1 = products[0];
  assertExists(product1.product_id, "Product ID should be generated");
  assertEquals(product1.product_name, EXPECTED_PRODUCT_1.product_name);
  assertEquals(product1.brand, EXPECTED_PRODUCT_1.brand);
  assertEquals(product1.lego_set_number, EXPECTED_PRODUCT_1.lego_set_number);
  assertEquals(product1.price, EXPECTED_PRODUCT_1.price);
  assertEquals(product1.price_string, EXPECTED_PRODUCT_1.price_string);
  assertEquals(product1.discount_percentage, EXPECTED_PRODUCT_1.discount_percentage);
  assertEquals(product1.price_before_discount, EXPECTED_PRODUCT_1.price_before_discount);
  assertEquals(product1.promotional_badges, EXPECTED_PRODUCT_1.promotional_badges);
  assertEquals(product1.units_sold, EXPECTED_PRODUCT_1.units_sold);
  assertEquals(product1.units_sold_string, EXPECTED_PRODUCT_1.units_sold_string);
  assertEquals(product1.image, EXPECTED_PRODUCT_1.image);
  assertEquals(product1.product_url, EXPECTED_PRODUCT_1.product_url);
  assertEquals(product1.shop_name, EXPECTED_PRODUCT_1.shop_name);

  // Verify second product
  const product2 = products[1];
  assertExists(product2.product_id, "Product ID should be generated");
  assertEquals(product2.product_name, EXPECTED_PRODUCT_2.product_name);
  assertEquals(product2.price, EXPECTED_PRODUCT_2.price);
  assertEquals(product2.units_sold, EXPECTED_PRODUCT_2.units_sold);
  assertEquals(product2.promotional_badges, EXPECTED_PRODUCT_2.promotional_badges);
});

Deno.test("parseShopeeHtml - should return empty array when HTML contains no products", () => {
  // Arrange: Empty product listing
  const shopUsername = "testshop";

  // Act: Parse empty HTML
  const products = parseShopeeHtml(EMPTY_HTML, shopUsername);

  // Assert: Should return empty array, not throw error
  assertEquals(products, [], "Should return empty array for HTML with no products");
});

// ============================================================================
// Product-level Parsing Tests - Individual product behavior
// ============================================================================

Deno.test("parseProductItem - should parse product with discount and multiple badges", () => {
  // Arrange: Parse HTML to get DOM element
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item, "Test fixture should contain product item");

  // Act: Parse single product
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert: Verify all expected fields
  assertExists(product, "Should successfully parse the product");
  assertEquals(product!.product_name, EXPECTED_PRODUCT_1.product_name);
  assertEquals(product!.lego_set_number, "77243", "Should extract LEGO set number from name");
  assertEquals(product!.brand, "LEGO", "Should identify LEGO brand");
  assertEquals(product!.price, 12600, "Should convert RM126.00 to 12600 cents");
  assertEquals(product!.discount_percentage, 3, "Should extract 3% discount");
  assertEquals(product!.price_before_discount, 12990, "Should calculate original price");
  assertEquals(product!.units_sold, 1000, "Should normalize '1k+' to 1000 units");
  assertEquals(product!.promotional_badges.length, 3, "Should extract 3 badges including verified");
  assertEquals(product!.promotional_badges, ["shopeelagimurah", "cod", "verified"], "Should normalize badge text and detect verified flag");
});

Deno.test("parseProductItem - should parse product with numeric sold units", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_NUMERIC_SOLD);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert: Focus on the different behavior (numeric sold units)
  assertExists(product);
  assertEquals(product!.units_sold, 666, "Should parse numeric sold count correctly");
  assertEquals(product!.units_sold_string, "666 sold");
  assertEquals(product!.discount_percentage, 6, "Should extract 6% discount");
  assertEquals(product!.price, 12211, "Should convert RM122.11 to cents");
});

// ============================================================================
// Price Extraction Tests - Critical business logic
// ============================================================================

Deno.test("parseProductItem - should correctly convert prices to cents", () => {
  // Arrange: Product with RM126.00 price
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert: Verify price is in cents (critical for financial calculations)
  assertExists(product);
  assertEquals(product!.price, 12600, "RM126.00 should be 12600 cents");
  assertEquals(product!.price_string, "126.00", "Should return numeric price portion");
});

Deno.test("parseProductItem - should calculate price before discount correctly", () => {
  // Arrange: Product with RM126.00 and -3% discount
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert: Verify discount calculation
  // Original = Current / (1 - discount%) = 12600 / 0.97 ≈ 12990
  assertExists(product);
  assertEquals(product!.price_before_discount, 12990, "Should calculate original price from discount");
  assertEquals(product!.discount_percentage, 3);
});

// ============================================================================
// Sold Units Normalization Tests
// ============================================================================

Deno.test("parseProductItem - should normalize '1k+' sold units to 1000", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(product!.units_sold, 1000, "Should convert '1k+' to numeric 1000");
  assertEquals(product!.units_sold_string, "1k+ sold", "Should preserve original text");
});

Deno.test("parseProductItem - should handle regular numeric sold counts", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_NUMERIC_SOLD);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(product!.units_sold, 666, "Should parse regular numbers correctly");
  assertEquals(product!.units_sold_string, "666 sold");
});

// ============================================================================
// LEGO Set Number Extraction Tests
// ============================================================================

Deno.test("parseProductItem - should extract LEGO set number from product name", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(product!.lego_set_number, "77243", "Should extract 5-digit LEGO set number");
});

Deno.test("parseProductItem - should return null when no LEGO set number exists", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITHOUT_SET_NUMBER);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "genericshop");

  // Assert
  assertExists(product);
  assertEquals(product!.lego_set_number, null, "Should return null for products without set numbers");
});

// ============================================================================
// Badge Normalization Tests
// ============================================================================

Deno.test("parseProductItem - should normalize badge text to lowercase without special characters", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(
    product!.promotional_badges,
    ["shopeelagimurah", "cod", "verified"],
    "Should normalize 'Shopee Lagi Murah' to 'shopeelagimurah', 'COD' to 'cod', and detect verified flag",
  );
});

Deno.test("parseProductItem - should handle multiple badge types", () => {
  // Arrange: Product with COD and Sea Shipping badges
  const doc = parseHtmlDocument(PRODUCT_WITH_NUMERIC_SOLD);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(product!.promotional_badges.length, 3, "Should extract all badges including verified");
  assertEquals(product!.promotional_badges, ["cod", "seashipping", "verified"]);
});

// ============================================================================
// Edge Cases and Error Handling
// ============================================================================

Deno.test("parseProductItem - should handle minimal product HTML gracefully", () => {
  // Arrange: Minimal HTML with just name and price
  const doc = parseHtmlDocument(PRODUCT_MINIMAL);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act: Parse minimal product
  const product = parseProductItem(item as Element, 0, "testshop");

  // Assert: Should parse successfully with null for missing fields
  assertExists(product, "Should parse minimal product without errors");
  assertEquals(product!.product_name, "Simple Product Name");
  assertEquals(product!.price, 9999, "Should parse RM99.99 to cents");
  assertEquals(product!.discount_percentage, null, "Should return null for missing discount");
  assertEquals(product!.promotional_badges, [], "Should return empty array for missing badges");
  assertEquals(product!.units_sold, null, "Should return null for missing sold units");
});

Deno.test("parseProductItem - should return null for invalid product elements", () => {
  // Arrange: Empty element
  const doc = parseHtmlDocument("<div></div>");
  const item = doc.querySelector("div");
  assertExists(item);

  // Act: Try to parse invalid element
  const product = parseProductItem(item as Element, 0, "testshop");

  // Assert: Should return null instead of throwing error
  assertEquals(product, null, "Should return null for elements without product data");
});

// ============================================================================
// URL and Shop Information Tests
// ============================================================================

Deno.test("parseProductItem - should construct complete product URL", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertExists(product!.product_url, "Should extract product URL");
  assertEquals(
    product!.product_url?.startsWith("https://shopee.com.my/"),
    true,
    "Should construct full Shopee URL",
  );
  assertEquals(
    product!.product_url?.includes("77243"),
    true,
    "URL should contain set number",
  );
});

Deno.test("parseProductItem - should set shop_name from provided username", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);
  const shopUsername = "mylegoshop123";

  // Act
  const product = parseProductItem(item as Element, 0, shopUsername);

  // Assert
  assertExists(product);
  assertEquals(product!.shop_name, shopUsername, "Should use provided shop username");
});

// ============================================================================
// Image Extraction Tests
// ============================================================================

Deno.test("parseProductItem - should extract product image URL", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertExists(product!.image, "Should extract image URL");
  assertEquals(
    product!.image?.startsWith("https://"),
    true,
    "Image should be a valid HTTPS URL",
  );
  assertEquals(
    product!.image?.includes("susercontent.com"),
    true,
    "Image should be from Shopee CDN",
  );
});

// ============================================================================
// Brand Detection Tests
// ============================================================================

Deno.test("parseProductItem - should detect LEGO brand from product name", () => {
  // Arrange
  const doc = parseHtmlDocument(PRODUCT_WITH_DISCOUNT_AND_BADGES);
  const item = doc.querySelector(".shop-search-result-view__item");
  assertExists(item);

  // Act
  const product = parseProductItem(item as Element, 0, "legoshopmy");

  // Assert
  assertExists(product);
  assertEquals(product!.brand, "LEGO", "Should detect LEGO brand");
});

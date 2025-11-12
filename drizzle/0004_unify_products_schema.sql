-- Create product_source enum
CREATE TYPE "product_source" AS ENUM('shopee', 'toysrus');

-- Rename shopee_items to products and add source column
ALTER TABLE "shopee_items" RENAME TO "products";
ALTER TABLE "products" ADD COLUMN "source" "product_source" NOT NULL DEFAULT 'shopee';

-- Add Toys"R"Us-specific columns
ALTER TABLE "products" ADD COLUMN "sku" varchar(50);
ALTER TABLE "products" ADD COLUMN "category_number" varchar(50);
ALTER TABLE "products" ADD COLUMN "category_name" varchar(255);
ALTER TABLE "products" ADD COLUMN "age_range" varchar(100);

-- Update indexes with new table name
DROP INDEX IF EXISTS "idx_shopee_product_id";
DROP INDEX IF EXISTS "idx_shopee_price";
DROP INDEX IF EXISTS "idx_shopee_sold";
DROP INDEX IF EXISTS "idx_shopee_shop_id";
DROP INDEX IF EXISTS "idx_shopee_created_at";
DROP INDEX IF EXISTS "idx_shopee_lego_set";
DROP INDEX IF EXISTS "idx_shopee_watch_status";
DROP INDEX IF EXISTS "idx_shopee_name_search";

CREATE INDEX "idx_products_source" ON "products" ("source");
CREATE INDEX "idx_products_product_id" ON "products" ("product_id");
CREATE INDEX "idx_products_price" ON "products" ("price");
CREATE INDEX "idx_products_sold" ON "products" ("units_sold");
CREATE INDEX "idx_products_shop_id" ON "products" ("shop_id");
CREATE INDEX "idx_products_created_at" ON "products" ("created_at");
CREATE INDEX "idx_products_lego_set" ON "products" ("lego_set_number");
CREATE INDEX "idx_products_watch_status" ON "products" ("watch_status");
CREATE INDEX "idx_products_name_search" ON "products" USING gin (to_tsvector('english', name));
CREATE INDEX "idx_products_source_lego" ON "products" ("source", "lego_set_number");

-- Rename shopee_price_history to price_history
ALTER TABLE "shopee_price_history" RENAME TO "price_history";

-- Update price history indexes
DROP INDEX IF EXISTS "idx_price_history_product_time";
CREATE INDEX "idx_price_history_product_time" ON "price_history" ("product_id", "recorded_at");

-- Rename shopee_scrape_sessions to scrape_sessions and add source column
ALTER TABLE "shopee_scrape_sessions" RENAME TO "scrape_sessions";
ALTER TABLE "scrape_sessions" ADD COLUMN "source" "product_source" NOT NULL DEFAULT 'shopee';

-- Update scrape sessions indexes
DROP INDEX IF EXISTS "idx_scrape_sessions_scraped_at";
CREATE INDEX "idx_scrape_sessions_scraped_at" ON "scrape_sessions" ("scraped_at");
CREATE INDEX "idx_scrape_sessions_source" ON "scrape_sessions" ("source");

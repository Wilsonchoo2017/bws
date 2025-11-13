-- Migration: Add local image storage columns
-- This migration adds columns to support storing downloaded images locally
-- while maintaining backward compatibility with existing external URLs

-- Add image download columns to products table
ALTER TABLE "products" ADD COLUMN "local_image_path" text;
ALTER TABLE "products" ADD COLUMN "local_images" jsonb;
ALTER TABLE "products" ADD COLUMN "image_downloaded_at" timestamp;
ALTER TABLE "products" ADD COLUMN "image_download_status" varchar(20);

-- Add image download columns to bricklink_items table
ALTER TABLE "bricklink_items" ADD COLUMN "image_url" text;
ALTER TABLE "bricklink_items" ADD COLUMN "local_image_path" text;
ALTER TABLE "bricklink_items" ADD COLUMN "image_downloaded_at" timestamp;
ALTER TABLE "bricklink_items" ADD COLUMN "image_download_status" varchar(20);

-- Add image download columns to brickranker_retirement_items table
ALTER TABLE "brickranker_retirement_items" ADD COLUMN "image_url" text;
ALTER TABLE "brickranker_retirement_items" ADD COLUMN "local_image_path" text;
ALTER TABLE "brickranker_retirement_items" ADD COLUMN "image_downloaded_at" timestamp;
ALTER TABLE "brickranker_retirement_items" ADD COLUMN "image_download_status" varchar(20);

-- Create indexes for efficient queries on image download status
CREATE INDEX "idx_products_image_status" ON "products" ("image_download_status");
CREATE INDEX "idx_bricklink_image_status" ON "bricklink_items" ("image_download_status");
CREATE INDEX "idx_brickranker_image_status" ON "brickranker_retirement_items" ("image_download_status");

-- Comments for documentation
COMMENT ON COLUMN "products"."local_image_path" IS 'Local filesystem path for single downloaded image';
COMMENT ON COLUMN "products"."local_images" IS 'JSONB array of local filesystem paths for multiple images';
COMMENT ON COLUMN "products"."image_downloaded_at" IS 'Timestamp when image was last downloaded';
COMMENT ON COLUMN "products"."image_download_status" IS 'Status: pending, downloading, completed, failed, skipped';

COMMENT ON COLUMN "bricklink_items"."image_url" IS 'External URL for product image';
COMMENT ON COLUMN "bricklink_items"."local_image_path" IS 'Local filesystem path for downloaded image';
COMMENT ON COLUMN "bricklink_items"."image_downloaded_at" IS 'Timestamp when image was downloaded';
COMMENT ON COLUMN "bricklink_items"."image_download_status" IS 'Status: pending, downloading, completed, failed, skipped';

COMMENT ON COLUMN "brickranker_retirement_items"."image_url" IS 'External URL for set image';
COMMENT ON COLUMN "brickranker_retirement_items"."local_image_path" IS 'Local filesystem path for downloaded image';
COMMENT ON COLUMN "brickranker_retirement_items"."image_downloaded_at" IS 'Timestamp when image was downloaded';
COMMENT ON COLUMN "brickranker_retirement_items"."image_download_status" IS 'Status: pending, downloading, completed, failed, skipped';

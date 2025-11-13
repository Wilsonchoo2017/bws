-- Migration: Add WorldBricks LEGO set information table
-- This migration creates a new table to store comprehensive LEGO set data from WorldBricks,
-- focusing on year released and year retired as primary fields

-- Create worldbricks_sets table
CREATE TABLE "worldbricks_sets" (
  "id" serial PRIMARY KEY,
  "set_number" varchar(20) NOT NULL UNIQUE,
  "set_name" text,
  "description" text,

  -- Primary fields (year released and retired year are high priority)
  "year_released" integer,
  "year_retired" integer,

  -- Secondary fields
  "designer" varchar(255),
  "parts_count" integer,
  "dimensions" varchar(255),

  -- Media fields
  "image_url" text,
  "local_image_path" text,
  "image_downloaded_at" timestamp,
  "image_download_status" varchar(20),

  -- Source tracking
  "source_url" text,

  -- Scraping metadata
  "last_scraped_at" timestamp,
  "scrape_status" varchar(20),

  -- Timestamps
  "created_at" timestamp DEFAULT now() NOT NULL,
  "updated_at" timestamp DEFAULT now() NOT NULL
);

-- Create indexes for efficient queries
CREATE INDEX "idx_worldbricks_set_number" ON "worldbricks_sets" ("set_number");
CREATE INDEX "idx_worldbricks_year_released" ON "worldbricks_sets" ("year_released");
CREATE INDEX "idx_worldbricks_year_retired" ON "worldbricks_sets" ("year_retired");
CREATE INDEX "idx_worldbricks_image_status" ON "worldbricks_sets" ("image_download_status");
CREATE INDEX "idx_worldbricks_scrape_status" ON "worldbricks_sets" ("scrape_status");

-- Add comments for documentation
COMMENT ON TABLE "worldbricks_sets" IS 'LEGO set information scraped from WorldBricks.com';
COMMENT ON COLUMN "worldbricks_sets"."set_number" IS 'LEGO set number (e.g., 31009)';
COMMENT ON COLUMN "worldbricks_sets"."set_name" IS 'Name of the LEGO set (e.g., Small Cottage)';
COMMENT ON COLUMN "worldbricks_sets"."description" IS 'Product description from WorldBricks';
COMMENT ON COLUMN "worldbricks_sets"."year_released" IS 'Year the set was first released (HIGH PRIORITY)';
COMMENT ON COLUMN "worldbricks_sets"."year_retired" IS 'Year the set was retired/discontinued (HIGH PRIORITY)';
COMMENT ON COLUMN "worldbricks_sets"."designer" IS 'Set designer/creator name';
COMMENT ON COLUMN "worldbricks_sets"."parts_count" IS 'Number of pieces in the set';
COMMENT ON COLUMN "worldbricks_sets"."dimensions" IS 'Physical dimensions of the built model';
COMMENT ON COLUMN "worldbricks_sets"."image_url" IS 'External URL for set image from WorldBricks';
COMMENT ON COLUMN "worldbricks_sets"."local_image_path" IS 'Local filesystem path for downloaded image';
COMMENT ON COLUMN "worldbricks_sets"."image_downloaded_at" IS 'Timestamp when image was downloaded';
COMMENT ON COLUMN "worldbricks_sets"."image_download_status" IS 'Status: pending, downloading, completed, failed, skipped';
COMMENT ON COLUMN "worldbricks_sets"."source_url" IS 'Original WorldBricks URL where data was scraped from';
COMMENT ON COLUMN "worldbricks_sets"."last_scraped_at" IS 'Timestamp of last successful scrape';
COMMENT ON COLUMN "worldbricks_sets"."scrape_status" IS 'Status: success, failed, partial';

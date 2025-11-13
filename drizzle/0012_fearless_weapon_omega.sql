ALTER TABLE "worldbricks_sets" ADD COLUMN "scrape_interval_days" integer DEFAULT 90;--> statement-breakpoint
ALTER TABLE "worldbricks_sets" ADD COLUMN "next_scrape_at" timestamp;--> statement-breakpoint
CREATE INDEX "idx_worldbricks_next_scrape_at" ON "worldbricks_sets" USING btree ("next_scrape_at");--> statement-breakpoint
-- Backfill: Set next_scrape_at to NOW() for all existing records to trigger immediate scraping
UPDATE "worldbricks_sets" SET "next_scrape_at" = NOW() WHERE "next_scrape_at" IS NULL;
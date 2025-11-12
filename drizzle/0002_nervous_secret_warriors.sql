ALTER TABLE "bricklink_items" ADD COLUMN "scrape_interval_days" integer DEFAULT 30 NOT NULL;--> statement-breakpoint
ALTER TABLE "bricklink_items" ADD COLUMN "last_scraped_at" timestamp;--> statement-breakpoint
ALTER TABLE "bricklink_items" ADD COLUMN "next_scrape_at" timestamp;--> statement-breakpoint
CREATE INDEX "idx_bricklink_next_scrape_at" ON "bricklink_items" USING btree ("next_scrape_at");
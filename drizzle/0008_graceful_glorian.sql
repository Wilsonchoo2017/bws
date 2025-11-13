ALTER TABLE "reddit_search_results" ADD COLUMN "watch_status" "watch_status" DEFAULT 'active' NOT NULL;--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD COLUMN "scrape_interval_days" integer DEFAULT 30 NOT NULL;--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD COLUMN "last_scraped_at" timestamp;--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD COLUMN "next_scrape_at" timestamp;--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD COLUMN "created_at" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD COLUMN "updated_at" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
CREATE INDEX "idx_reddit_watch_status" ON "reddit_search_results" USING btree ("watch_status");--> statement-breakpoint
CREATE INDEX "idx_reddit_next_scrape_at" ON "reddit_search_results" USING btree ("next_scrape_at");
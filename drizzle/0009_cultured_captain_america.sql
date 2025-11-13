CREATE TABLE "shopee_scrapes" (
	"id" serial PRIMARY KEY NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"scrape_session_id" integer,
	"price" bigint,
	"price_before_discount" bigint,
	"price_min" bigint,
	"price_max" bigint,
	"currency" varchar(10),
	"units_sold" bigint,
	"lifetime_sold" bigint,
	"shop_id" bigint,
	"shop_name" varchar(255),
	"shop_location" varchar(255),
	"current_stock" bigint,
	"stock_type" bigint,
	"stock_info_summary" text,
	"liked_count" bigint,
	"comment_count" bigint,
	"view_count" bigint,
	"avg_star_rating" bigint,
	"rating_count" jsonb,
	"is_adult" boolean,
	"is_mart" boolean,
	"is_preferred" boolean,
	"is_service_by_shopee" boolean,
	"product_url" text,
	"raw_data" jsonb,
	"scraped_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "products" ADD COLUMN "first_seen_at" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
ALTER TABLE "products" ADD COLUMN "last_seen_at" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
ALTER TABLE "scrape_sessions" ADD COLUMN "session_label" varchar(255);--> statement-breakpoint
ALTER TABLE "scrape_sessions" ADD COLUMN "filter_context" text;--> statement-breakpoint
ALTER TABLE "scrape_sessions" ADD COLUMN "shop_name" varchar(255);--> statement-breakpoint
CREATE INDEX "idx_shopee_scrapes_product_id" ON "shopee_scrapes" USING btree ("product_id");--> statement-breakpoint
CREATE INDEX "idx_shopee_scrapes_session_id" ON "shopee_scrapes" USING btree ("scrape_session_id");--> statement-breakpoint
CREATE INDEX "idx_shopee_scrapes_product_time" ON "shopee_scrapes" USING btree ("product_id","scraped_at");--> statement-breakpoint
CREATE INDEX "idx_shopee_scrapes_shop_id" ON "shopee_scrapes" USING btree ("shop_id");--> statement-breakpoint
CREATE INDEX "idx_shopee_scrapes_scraped_at" ON "shopee_scrapes" USING btree ("scraped_at");--> statement-breakpoint
CREATE INDEX "idx_scrape_sessions_shop_name" ON "scrape_sessions" USING btree ("shop_name");--> statement-breakpoint
ALTER TABLE "reddit_search_results" ADD CONSTRAINT "unique_lego_set_subreddit" UNIQUE("lego_set_number","subreddit");
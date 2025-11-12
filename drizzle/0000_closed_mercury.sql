CREATE TABLE "bricklink_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"item_type" varchar(10) NOT NULL,
	"title" text,
	"weight" varchar(50),
	"six_month_new" jsonb,
	"six_month_used" jsonb,
	"current_new" jsonb,
	"current_used" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "bricklink_items_item_id_unique" UNIQUE("item_id")
);
--> statement-breakpoint
CREATE TABLE "shopee_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"name" text,
	"brand" varchar(255),
	"currency" varchar(10),
	"price" bigint,
	"price_min" bigint,
	"price_max" bigint,
	"price_before_discount" bigint,
	"sold" bigint,
	"historical_sold" bigint,
	"liked_count" bigint,
	"cmt_count" bigint,
	"view_count" bigint,
	"item_rating_star_rating" bigint,
	"item_rating_rating_count" jsonb,
	"stock_info_summary" text,
	"stock_info_stock_type" bigint,
	"stock_info_current_stock" bigint,
	"is_adult" boolean,
	"is_mart" boolean,
	"is_preferred" boolean,
	"is_service_by_shopee" boolean,
	"image" text,
	"images" jsonb,
	"shop_id" bigint,
	"shop_name" varchar(255),
	"shop_location" varchar(255),
	"lego_set_number" varchar(10),
	"raw_data" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "shopee_items_product_id_unique" UNIQUE("product_id")
);
--> statement-breakpoint
CREATE TABLE "shopee_price_history" (
	"id" serial PRIMARY KEY NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"price" bigint,
	"price_before_discount" bigint,
	"sold_at_time" bigint,
	"recorded_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "shopee_scrape_sessions" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_url" text,
	"products_found" integer DEFAULT 0 NOT NULL,
	"products_stored" integer DEFAULT 0 NOT NULL,
	"status" varchar(20) DEFAULT 'success' NOT NULL,
	"error_message" text,
	"scraped_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE INDEX "idx_shopee_product_id" ON "shopee_items" USING btree ("product_id");--> statement-breakpoint
CREATE INDEX "idx_shopee_price" ON "shopee_items" USING btree ("price");--> statement-breakpoint
CREATE INDEX "idx_shopee_sold" ON "shopee_items" USING btree ("sold");--> statement-breakpoint
CREATE INDEX "idx_shopee_shop_id" ON "shopee_items" USING btree ("shop_id");--> statement-breakpoint
CREATE INDEX "idx_shopee_created_at" ON "shopee_items" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_shopee_lego_set" ON "shopee_items" USING btree ("lego_set_number");--> statement-breakpoint
CREATE INDEX "idx_shopee_name_search" ON "shopee_items" USING gin (to_tsvector('english', "name"));--> statement-breakpoint
CREATE INDEX "idx_price_history_product_time" ON "shopee_price_history" USING btree ("product_id","recorded_at");--> statement-breakpoint
CREATE INDEX "idx_scrape_sessions_scraped_at" ON "shopee_scrape_sessions" USING btree ("scraped_at");
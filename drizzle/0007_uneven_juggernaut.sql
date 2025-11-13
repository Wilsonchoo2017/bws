CREATE TYPE "public"."condition_type" AS ENUM('new', 'used');--> statement-breakpoint
CREATE TYPE "public"."product_source" AS ENUM('shopee', 'toysrus', 'brickeconomy', 'self');--> statement-breakpoint
CREATE TYPE "public"."time_period" AS ENUM('six_month', 'current');--> statement-breakpoint
CREATE TYPE "public"."watch_status" AS ENUM('active', 'paused', 'stopped', 'archived');--> statement-breakpoint
CREATE TABLE "bricklink_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"item_type" varchar(10) NOT NULL,
	"title" text,
	"weight" varchar(50),
	"image_url" text,
	"local_image_path" text,
	"image_downloaded_at" timestamp,
	"image_download_status" varchar(20),
	"six_month_new" jsonb,
	"six_month_used" jsonb,
	"current_new" jsonb,
	"current_used" jsonb,
	"watch_status" "watch_status" DEFAULT 'active' NOT NULL,
	"scrape_interval_days" integer DEFAULT 30 NOT NULL,
	"last_scraped_at" timestamp,
	"next_scrape_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "bricklink_items_item_id_unique" UNIQUE("item_id")
);
--> statement-breakpoint
CREATE TABLE "bricklink_price_history" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"six_month_new" jsonb,
	"six_month_used" jsonb,
	"current_new" jsonb,
	"current_used" jsonb,
	"recorded_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "bricklink_volume_history" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"condition" "condition_type" NOT NULL,
	"time_period" time_period NOT NULL,
	"total_qty" integer,
	"times_sold" integer,
	"total_lots" integer,
	"min_price" integer,
	"avg_price" integer,
	"qty_avg_price" integer,
	"max_price" integer,
	"currency" varchar(3) DEFAULT 'USD',
	"recorded_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "brickranker_retirement_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"set_number" varchar(20) NOT NULL,
	"set_name" text NOT NULL,
	"year_released" integer,
	"retiring_soon" boolean DEFAULT false NOT NULL,
	"expected_retirement_date" varchar(50),
	"theme" varchar(100),
	"image_url" text,
	"local_image_path" text,
	"image_downloaded_at" timestamp,
	"image_download_status" varchar(20),
	"product_id" integer,
	"is_active" boolean DEFAULT true NOT NULL,
	"scrape_interval_days" integer DEFAULT 30 NOT NULL,
	"last_scraped_at" timestamp,
	"next_scrape_at" timestamp,
	"scraped_at" timestamp DEFAULT now() NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "brickranker_retirement_items_set_number_unique" UNIQUE("set_number")
);
--> statement-breakpoint
CREATE TABLE "price_history" (
	"id" serial PRIMARY KEY NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"price" bigint,
	"price_before_discount" bigint,
	"units_sold_snapshot" bigint,
	"recorded_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "product_analysis" (
	"id" serial PRIMARY KEY NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"strategy" varchar(50) NOT NULL,
	"overall_score" integer NOT NULL,
	"confidence" integer NOT NULL,
	"action" varchar(20) NOT NULL,
	"urgency" varchar(20) NOT NULL,
	"dimensional_scores" jsonb NOT NULL,
	"estimated_roi" integer,
	"time_horizon" varchar(100),
	"risks" jsonb,
	"opportunities" jsonb,
	"full_recommendation" jsonb NOT NULL,
	"analyzed_at" timestamp DEFAULT now() NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "products" (
	"id" serial PRIMARY KEY NOT NULL,
	"source" "product_source" NOT NULL,
	"product_id" varchar(100) NOT NULL,
	"name" text,
	"brand" varchar(255),
	"currency" varchar(10),
	"price" bigint,
	"price_min" bigint,
	"price_max" bigint,
	"price_before_discount" bigint,
	"image" text,
	"images" jsonb,
	"local_image_path" text,
	"local_images" jsonb,
	"image_downloaded_at" timestamp,
	"image_download_status" varchar(20),
	"lego_set_number" varchar(10),
	"watch_status" "watch_status" DEFAULT 'active' NOT NULL,
	"units_sold" bigint,
	"lifetime_sold" bigint,
	"liked_count" bigint,
	"comment_count" bigint,
	"view_count" bigint,
	"avg_star_rating" bigint,
	"rating_count" jsonb,
	"stock_info_summary" text,
	"stock_type" bigint,
	"current_stock" bigint,
	"is_adult" boolean,
	"is_mart" boolean,
	"is_preferred" boolean,
	"is_service_by_shopee" boolean,
	"shop_id" bigint,
	"shop_name" varchar(255),
	"shop_location" varchar(255),
	"sku" varchar(50),
	"category_number" varchar(50),
	"category_name" varchar(255),
	"age_range" varchar(100),
	"raw_data" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "products_product_id_unique" UNIQUE("product_id")
);
--> statement-breakpoint
CREATE TABLE "reddit_search_results" (
	"id" serial PRIMARY KEY NOT NULL,
	"lego_set_number" varchar(20) NOT NULL,
	"subreddit" varchar(50) DEFAULT 'lego' NOT NULL,
	"total_posts" integer DEFAULT 0 NOT NULL,
	"posts" jsonb,
	"searched_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "scrape_sessions" (
	"id" serial PRIMARY KEY NOT NULL,
	"source" "product_source" NOT NULL,
	"source_url" text,
	"products_found" integer DEFAULT 0 NOT NULL,
	"products_stored" integer DEFAULT 0 NOT NULL,
	"status" varchar(20) DEFAULT 'success' NOT NULL,
	"error_message" text,
	"scraped_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "worldbricks_sets" (
	"id" serial PRIMARY KEY NOT NULL,
	"set_number" varchar(20) NOT NULL,
	"set_name" text,
	"description" text,
	"year_released" integer,
	"year_retired" integer,
	"designer" varchar(255),
	"parts_count" integer,
	"dimensions" varchar(255),
	"image_url" text,
	"local_image_path" text,
	"image_downloaded_at" timestamp,
	"image_download_status" varchar(20),
	"source_url" text,
	"last_scraped_at" timestamp,
	"scrape_status" varchar(20),
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "worldbricks_sets_set_number_unique" UNIQUE("set_number")
);
--> statement-breakpoint
CREATE INDEX "idx_bricklink_watch_status" ON "bricklink_items" USING btree ("watch_status");--> statement-breakpoint
CREATE INDEX "idx_bricklink_next_scrape_at" ON "bricklink_items" USING btree ("next_scrape_at");--> statement-breakpoint
CREATE INDEX "idx_bricklink_image_status" ON "bricklink_items" USING btree ("image_download_status");--> statement-breakpoint
CREATE INDEX "idx_bricklink_price_history_item_time" ON "bricklink_price_history" USING btree ("item_id","recorded_at");--> statement-breakpoint
CREATE INDEX "idx_bricklink_volume_item_condition_time" ON "bricklink_volume_history" USING btree ("item_id","condition","time_period","recorded_at");--> statement-breakpoint
CREATE INDEX "idx_bricklink_volume_condition" ON "bricklink_volume_history" USING btree ("condition");--> statement-breakpoint
CREATE INDEX "idx_bricklink_volume_recorded_at" ON "bricklink_volume_history" USING btree ("recorded_at");--> statement-breakpoint
CREATE INDEX "idx_brickranker_set_number" ON "brickranker_retirement_items" USING btree ("set_number");--> statement-breakpoint
CREATE INDEX "idx_brickranker_product_id" ON "brickranker_retirement_items" USING btree ("product_id");--> statement-breakpoint
CREATE INDEX "idx_brickranker_theme" ON "brickranker_retirement_items" USING btree ("theme");--> statement-breakpoint
CREATE INDEX "idx_brickranker_is_active" ON "brickranker_retirement_items" USING btree ("is_active");--> statement-breakpoint
CREATE INDEX "idx_brickranker_next_scrape_at" ON "brickranker_retirement_items" USING btree ("next_scrape_at");--> statement-breakpoint
CREATE INDEX "idx_brickranker_image_status" ON "brickranker_retirement_items" USING btree ("image_download_status");--> statement-breakpoint
CREATE INDEX "idx_price_history_product_time" ON "price_history" USING btree ("product_id","recorded_at");--> statement-breakpoint
CREATE INDEX "idx_analysis_product_strategy" ON "product_analysis" USING btree ("product_id","strategy");--> statement-breakpoint
CREATE INDEX "idx_analysis_action" ON "product_analysis" USING btree ("action");--> statement-breakpoint
CREATE INDEX "idx_analysis_urgency" ON "product_analysis" USING btree ("urgency");--> statement-breakpoint
CREATE INDEX "idx_analysis_score" ON "product_analysis" USING btree ("overall_score");--> statement-breakpoint
CREATE INDEX "idx_analysis_analyzed_at" ON "product_analysis" USING btree ("analyzed_at");--> statement-breakpoint
CREATE INDEX "idx_products_source" ON "products" USING btree ("source");--> statement-breakpoint
CREATE INDEX "idx_products_product_id" ON "products" USING btree ("product_id");--> statement-breakpoint
CREATE INDEX "idx_products_price" ON "products" USING btree ("price");--> statement-breakpoint
CREATE INDEX "idx_products_sold" ON "products" USING btree ("units_sold");--> statement-breakpoint
CREATE INDEX "idx_products_shop_id" ON "products" USING btree ("shop_id");--> statement-breakpoint
CREATE INDEX "idx_products_created_at" ON "products" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_products_lego_set" ON "products" USING btree ("lego_set_number");--> statement-breakpoint
CREATE INDEX "idx_products_watch_status" ON "products" USING btree ("watch_status");--> statement-breakpoint
CREATE INDEX "idx_products_image_status" ON "products" USING btree ("image_download_status");--> statement-breakpoint
CREATE INDEX "idx_products_name_search" ON "products" USING gin (to_tsvector('english', "name"));--> statement-breakpoint
CREATE INDEX "idx_products_source_lego" ON "products" USING btree ("source","lego_set_number");--> statement-breakpoint
CREATE INDEX "idx_reddit_lego_set_number" ON "reddit_search_results" USING btree ("lego_set_number");--> statement-breakpoint
CREATE INDEX "idx_reddit_searched_at" ON "reddit_search_results" USING btree ("searched_at");--> statement-breakpoint
CREATE INDEX "idx_scrape_sessions_scraped_at" ON "scrape_sessions" USING btree ("scraped_at");--> statement-breakpoint
CREATE INDEX "idx_scrape_sessions_source" ON "scrape_sessions" USING btree ("source");--> statement-breakpoint
CREATE INDEX "idx_worldbricks_set_number" ON "worldbricks_sets" USING btree ("set_number");--> statement-breakpoint
CREATE INDEX "idx_worldbricks_year_released" ON "worldbricks_sets" USING btree ("year_released");--> statement-breakpoint
CREATE INDEX "idx_worldbricks_year_retired" ON "worldbricks_sets" USING btree ("year_retired");--> statement-breakpoint
CREATE INDEX "idx_worldbricks_image_status" ON "worldbricks_sets" USING btree ("image_download_status");--> statement-breakpoint
CREATE INDEX "idx_worldbricks_scrape_status" ON "worldbricks_sets" USING btree ("scrape_status");
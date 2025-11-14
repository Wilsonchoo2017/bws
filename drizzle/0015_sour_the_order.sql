ALTER TYPE "public"."product_source" ADD VALUE 'bricklink' BEFORE 'self';--> statement-breakpoint
ALTER TYPE "public"."product_source" ADD VALUE 'worldbricks' BEFORE 'self';--> statement-breakpoint
ALTER TYPE "public"."product_source" ADD VALUE 'brickranker' BEFORE 'self';--> statement-breakpoint
CREATE TABLE "product_tags" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(100) NOT NULL,
	"description" text,
	"end_date" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "product_tags_name_unique" UNIQUE("name")
);
--> statement-breakpoint
CREATE TABLE "scrape_raw_data" (
	"id" serial PRIMARY KEY NOT NULL,
	"scrape_session_id" integer NOT NULL,
	"source" "product_source" NOT NULL,
	"source_url" text NOT NULL,
	"raw_html_compressed" text NOT NULL,
	"raw_html_size" integer NOT NULL,
	"compressed_size" integer NOT NULL,
	"content_type" varchar(100) DEFAULT 'text/html',
	"http_status" integer,
	"scraped_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "products" ADD COLUMN "tags" jsonb;--> statement-breakpoint
CREATE INDEX "idx_product_tags_name" ON "product_tags" USING btree ("name");--> statement-breakpoint
CREATE INDEX "idx_product_tags_end_date" ON "product_tags" USING btree ("end_date");--> statement-breakpoint
CREATE INDEX "idx_scrape_raw_data_session_id" ON "scrape_raw_data" USING btree ("scrape_session_id");--> statement-breakpoint
CREATE INDEX "idx_scrape_raw_data_source" ON "scrape_raw_data" USING btree ("source");--> statement-breakpoint
CREATE INDEX "idx_scrape_raw_data_scraped_at" ON "scrape_raw_data" USING btree ("scraped_at");--> statement-breakpoint
CREATE INDEX "idx_scrape_raw_data_session_source" ON "scrape_raw_data" USING btree ("scrape_session_id","source");
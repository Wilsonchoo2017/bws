CREATE TYPE "public"."watch_status" AS ENUM('active', 'paused', 'stopped', 'archived');--> statement-breakpoint
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
ALTER TABLE "bricklink_items" ADD COLUMN "watch_status" "watch_status" DEFAULT 'active' NOT NULL;--> statement-breakpoint
ALTER TABLE "shopee_items" ADD COLUMN "watch_status" "watch_status" DEFAULT 'active' NOT NULL;--> statement-breakpoint
CREATE INDEX "idx_bricklink_price_history_item_time" ON "bricklink_price_history" USING btree ("item_id","recorded_at");--> statement-breakpoint
CREATE INDEX "idx_bricklink_watch_status" ON "bricklink_items" USING btree ("watch_status");--> statement-breakpoint
CREATE INDEX "idx_shopee_watch_status" ON "shopee_items" USING btree ("watch_status");
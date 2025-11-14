CREATE TYPE "public"."discount_type" AS ENUM('percentage', 'fixed');--> statement-breakpoint
CREATE TYPE "public"."voucher_type" AS ENUM('platform', 'shop', 'item_tag');--> statement-breakpoint
CREATE TABLE "vouchers" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(255) NOT NULL,
	"description" text,
	"voucher_type" "voucher_type" NOT NULL,
	"discount_type" "discount_type" NOT NULL,
	"discount_value" integer NOT NULL,
	"platform" varchar(50),
	"shop_id" bigint,
	"shop_name" varchar(255),
	"min_purchase" integer,
	"max_discount" integer,
	"required_tag_ids" uuid[],
	"tiered_discounts" jsonb,
	"is_active" boolean DEFAULT true NOT NULL,
	"start_date" timestamp,
	"end_date" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE INDEX "idx_vouchers_active" ON "vouchers" USING btree ("is_active");--> statement-breakpoint
CREATE INDEX "idx_vouchers_platform" ON "vouchers" USING btree ("platform");--> statement-breakpoint
CREATE INDEX "idx_vouchers_end_date" ON "vouchers" USING btree ("end_date");--> statement-breakpoint
CREATE INDEX "idx_vouchers_start_date" ON "vouchers" USING btree ("start_date");
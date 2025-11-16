CREATE TABLE "bricklink_monthly_sales" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"month" varchar(7) NOT NULL,
	"condition" "condition_type" NOT NULL,
	"times_sold" integer NOT NULL,
	"total_quantity" integer NOT NULL,
	"min_price" integer,
	"max_price" integer,
	"avg_price" integer,
	"currency" varchar(3) DEFAULT 'USD' NOT NULL,
	"scraped_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "unique_bricklink_monthly_summary" UNIQUE("item_id","month","condition")
);
--> statement-breakpoint
CREATE INDEX "idx_bricklink_monthly_sales_item_month" ON "bricklink_monthly_sales" USING btree ("item_id","month");--> statement-breakpoint
CREATE INDEX "idx_bricklink_monthly_sales_month" ON "bricklink_monthly_sales" USING btree ("month");--> statement-breakpoint
CREATE INDEX "idx_bricklink_monthly_sales_condition" ON "bricklink_monthly_sales" USING btree ("condition");
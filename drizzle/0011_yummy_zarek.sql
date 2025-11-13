CREATE TABLE "bricklink_past_sales" (
	"id" serial PRIMARY KEY NOT NULL,
	"item_id" varchar(50) NOT NULL,
	"date_sold" timestamp NOT NULL,
	"condition" "condition_type" NOT NULL,
	"price" integer NOT NULL,
	"currency" varchar(3) DEFAULT 'USD' NOT NULL,
	"seller_location" varchar(100),
	"quantity" integer,
	"scraped_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "unique_bricklink_past_sale" UNIQUE("item_id","date_sold","condition","price")
);
--> statement-breakpoint
CREATE INDEX "idx_bricklink_past_sales_item_date" ON "bricklink_past_sales" USING btree ("item_id","date_sold");--> statement-breakpoint
CREATE INDEX "idx_bricklink_past_sales_date_sold" ON "bricklink_past_sales" USING btree ("date_sold");--> statement-breakpoint
CREATE INDEX "idx_bricklink_past_sales_condition" ON "bricklink_past_sales" USING btree ("condition");
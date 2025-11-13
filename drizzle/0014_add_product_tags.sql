-- Create product_tags table for managing tag definitions
CREATE TABLE IF NOT EXISTS "product_tags" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(100) NOT NULL,
	"description" text,
	"end_date" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "product_tags_name_unique" UNIQUE("name")
);

-- Create indexes for product_tags
CREATE INDEX IF NOT EXISTS "idx_product_tags_name" ON "product_tags" USING btree ("name");
CREATE INDEX IF NOT EXISTS "idx_product_tags_end_date" ON "product_tags" USING btree ("end_date");

-- Add tags column to products table
ALTER TABLE "products" ADD COLUMN "tags" jsonb;

-- Create a comment to document the tags column structure
COMMENT ON COLUMN "products"."tags" IS 'Array of {tagId: string, addedAt: string} objects';

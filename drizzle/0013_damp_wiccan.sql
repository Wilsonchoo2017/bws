-- Drop existing data since we're doing a fresh start (if tables exist)
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'product_analysis') THEN
    DELETE FROM "product_analysis";
  END IF;
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'price_history') THEN
    DELETE FROM "price_history";
  END IF;
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'shopee_scrapes') THEN
    DELETE FROM "shopee_scrapes";
  END IF;
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'products') THEN
    DELETE FROM "products";
  END IF;
END $$;--> statement-breakpoint
-- Alter column types to UUID (using USING clause to cast from varchar)
ALTER TABLE "price_history" ALTER COLUMN "product_id" SET DATA TYPE uuid USING product_id::uuid;--> statement-breakpoint
ALTER TABLE "shopee_scrapes" ALTER COLUMN "product_id" SET DATA TYPE uuid USING product_id::uuid;--> statement-breakpoint
ALTER TABLE "products" ALTER COLUMN "product_id" SET DATA TYPE uuid USING product_id::uuid;--> statement-breakpoint
ALTER TABLE "products" ALTER COLUMN "product_id" SET DEFAULT gen_random_uuid();--> statement-breakpoint
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'product_analysis' AND column_name = 'product_id') THEN
    ALTER TABLE "product_analysis" ALTER COLUMN "product_id" SET DATA TYPE uuid USING product_id::uuid;
  END IF;
END $$;
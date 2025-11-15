ALTER TABLE "bricklink_items" ADD COLUMN "year_released" integer;--> statement-breakpoint
CREATE INDEX "idx_bricklink_year_released" ON "bricklink_items" USING btree ("year_released");
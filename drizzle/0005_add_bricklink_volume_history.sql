-- Create enums for condition and time period
CREATE TYPE "condition_type" AS ENUM('new', 'used');
CREATE TYPE "time_period" AS ENUM('six_month', 'current');

-- Create bricklink_volume_history table for normalized time-series tracking
CREATE TABLE "bricklink_volume_history" (
  "id" serial PRIMARY KEY NOT NULL,
  "item_id" varchar(50) NOT NULL,
  "condition" "condition_type" NOT NULL,
  "time_period" "time_period" NOT NULL,
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

-- Create indexes for efficient queries
CREATE INDEX "idx_bricklink_volume_item_condition_time" ON "bricklink_volume_history" ("item_id", "condition", "time_period", "recorded_at");
CREATE INDEX "idx_bricklink_volume_condition" ON "bricklink_volume_history" ("condition");
CREATE INDEX "idx_bricklink_volume_recorded_at" ON "bricklink_volume_history" ("recorded_at");

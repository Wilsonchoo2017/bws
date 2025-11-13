-- Add unique constraint on (lego_set_number, subreddit) to prevent duplicate search results
-- This migration will:
-- 1. First, clean up any existing duplicates (keep the most recent one)
-- 2. Then add the unique constraint

-- Step 1: Delete duplicate rows, keeping only the most recent (highest id) for each (lego_set_number, subreddit) combination
DELETE FROM "reddit_search_results"
WHERE "id" NOT IN (
  SELECT MAX("id")
  FROM "reddit_search_results"
  GROUP BY "lego_set_number", "subreddit"
);--> statement-breakpoint

-- Step 2: Add the unique constraint
ALTER TABLE "reddit_search_results" ADD CONSTRAINT "unique_lego_set_subreddit" UNIQUE("lego_set_number", "subreddit");

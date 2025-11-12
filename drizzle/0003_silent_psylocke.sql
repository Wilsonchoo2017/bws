CREATE TABLE "reddit_search_results" (
	"id" serial PRIMARY KEY NOT NULL,
	"lego_set_number" varchar(20) NOT NULL,
	"subreddit" varchar(50) DEFAULT 'lego' NOT NULL,
	"total_posts" integer DEFAULT 0 NOT NULL,
	"posts" jsonb,
	"searched_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE INDEX "idx_reddit_lego_set_number" ON "reddit_search_results" USING btree ("lego_set_number");--> statement-breakpoint
CREATE INDEX "idx_reddit_searched_at" ON "reddit_search_results" USING btree ("searched_at");
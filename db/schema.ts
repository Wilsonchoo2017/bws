import {
  bigint,
  boolean,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  serial,
  text,
  timestamp,
  varchar,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

// Enum for watch status
export const watchStatusEnum = pgEnum("watch_status", [
  "active",
  "paused",
  "stopped",
  "archived",
]);

// Enum for product source/platform
export const productSourceEnum = pgEnum("product_source", [
  "shopee",
  "toysrus",
  "self",
]);

// Bricklink scraped items
export const bricklinkItems = pgTable(
  "bricklink_items",
  {
    id: serial("id").primaryKey(),
    itemId: varchar("item_id", { length: 50 }).notNull().unique(),
    itemType: varchar("item_type", { length: 10 }).notNull(),
    title: text("title"),
    weight: varchar("weight", { length: 50 }),

    // Store pricing data as JSONB for flexibility
    sixMonthNew: jsonb("six_month_new"),
    sixMonthUsed: jsonb("six_month_used"),
    currentNew: jsonb("current_new"),
    currentUsed: jsonb("current_used"),

    // Watch status for price tracking
    watchStatus: watchStatusEnum("watch_status").default("active").notNull(),

    // Scraping schedule configuration
    scrapeIntervalDays: integer("scrape_interval_days").default(30).notNull(),
    lastScrapedAt: timestamp("last_scraped_at"),
    nextScrapeAt: timestamp("next_scrape_at"),

    // Metadata
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for filtering by watch status
    watchStatusIdx: index("idx_bricklink_watch_status").on(table.watchStatus),
    // Index for efficient scraping queue queries
    nextScrapeAtIdx: index("idx_bricklink_next_scrape_at").on(
      table.nextScrapeAt,
    ),
  }),
);

// Unified products table (supports multiple platforms)
export const products = pgTable(
  "products",
  {
    id: serial("id").primaryKey(),

    // Source platform
    source: productSourceEnum("source").notNull(),

    // Core product fields (all platforms)
    productId: varchar("product_id", { length: 100 }).notNull().unique(),
    name: text("name"),
    brand: varchar("brand", { length: 255 }),

    // Pricing (all platforms)
    currency: varchar("currency", { length: 10 }),
    price: bigint("price", { mode: "number" }),
    priceMin: bigint("price_min", { mode: "number" }),
    priceMax: bigint("price_max", { mode: "number" }),
    priceBeforeDiscount: bigint("price_before_discount", { mode: "number" }),

    // Media (all platforms)
    image: text("image"),
    images: jsonb("images"),

    // LEGO specific (all platforms)
    legoSetNumber: varchar("lego_set_number", { length: 10 }),

    // Watch status for price tracking (all platforms)
    watchStatus: watchStatusEnum("watch_status").default("active").notNull(),

    // Shopee-specific fields (nullable)
    unitsSold: bigint("units_sold", { mode: "number" }),
    lifetimeSold: bigint("lifetime_sold", { mode: "number" }),
    liked_count: bigint("liked_count", { mode: "number" }),
    commentCount: bigint("comment_count", { mode: "number" }),
    view_count: bigint("view_count", { mode: "number" }),
    avgStarRating: bigint("avg_star_rating", { mode: "number" }),
    ratingCount: jsonb("rating_count"),
    stockInfoSummary: text("stock_info_summary"),
    stockType: bigint("stock_type", { mode: "number" }),
    currentStock: bigint("current_stock", { mode: "number" }),
    isAdult: boolean("is_adult"),
    isMart: boolean("is_mart"),
    isPreferred: boolean("is_preferred"),
    isServiceByShopee: boolean("is_service_by_shopee"),
    shopId: bigint("shop_id", { mode: "number" }),
    shopName: varchar("shop_name", { length: 255 }),
    shopLocation: varchar("shop_location", { length: 255 }),

    // Toys"R"Us-specific fields (nullable)
    sku: varchar("sku", { length: 50 }),
    categoryNumber: varchar("category_number", { length: 50 }),
    categoryName: varchar("category_name", { length: 255 }),
    ageRange: varchar("age_range", { length: 100 }),

    // Full data dump for reference (all platforms)
    rawData: jsonb("raw_data"),

    // Metadata
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Indexes for read performance
    sourceIdx: index("idx_products_source").on(table.source),
    productIdIdx: index("idx_products_product_id").on(table.productId),
    priceIdx: index("idx_products_price").on(table.price),
    soldIdx: index("idx_products_sold").on(table.unitsSold),
    shopIdIdx: index("idx_products_shop_id").on(table.shopId),
    createdAtIdx: index("idx_products_created_at").on(table.createdAt),
    legoSetNumberIdx: index("idx_products_lego_set").on(table.legoSetNumber),
    watchStatusIdx: index("idx_products_watch_status").on(table.watchStatus),
    // Full-text search index on name
    nameSearchIdx: index("idx_products_name_search").using(
      "gin",
      sql`to_tsvector('english', ${table.name})`,
    ),
    // Composite index for source + common queries
    sourceLegoSetIdx: index("idx_products_source_lego").on(
      table.source,
      table.legoSetNumber,
    ),
  }),
);

// Unified price history for tracking price changes over time (all platforms)
export const priceHistory = pgTable(
  "price_history",
  {
    id: serial("id").primaryKey(),
    productId: varchar("product_id", { length: 100 }).notNull(),
    price: bigint("price", { mode: "number" }),
    priceBeforeDiscount: bigint("price_before_discount", { mode: "number" }),
    unitsSoldSnapshot: bigint("units_sold_snapshot", { mode: "number" }),
    recordedAt: timestamp("recorded_at").defaultNow().notNull(),
  },
  (table) => ({
    // Composite index for efficient time-series queries
    productTimeIdx: index("idx_price_history_product_time").on(
      table.productId,
      table.recordedAt,
    ),
  }),
);

// Bricklink price history for tracking price changes over time
export const bricklinkPriceHistory = pgTable(
  "bricklink_price_history",
  {
    id: serial("id").primaryKey(),
    itemId: varchar("item_id", { length: 50 }).notNull(),
    sixMonthNew: jsonb("six_month_new"),
    sixMonthUsed: jsonb("six_month_used"),
    currentNew: jsonb("current_new"),
    currentUsed: jsonb("current_used"),
    recordedAt: timestamp("recorded_at").defaultNow().notNull(),
  },
  (table) => ({
    // Composite index for efficient time-series queries
    itemTimeIdx: index("idx_bricklink_price_history_item_time").on(
      table.itemId,
      table.recordedAt,
    ),
  }),
);

// Unified scrape sessions for tracking scraping metadata (all platforms)
export const scrapeSessions = pgTable(
  "scrape_sessions",
  {
    id: serial("id").primaryKey(),
    source: productSourceEnum("source").notNull(),
    sourceUrl: text("source_url"),
    productsFound: integer("products_found").notNull().default(0),
    productsStored: integer("products_stored").notNull().default(0),
    status: varchar("status", { length: 20 }).notNull().default("success"), // success, partial, failed
    errorMessage: text("error_message"),
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    scrapedAtIdx: index("idx_scrape_sessions_scraped_at").on(table.scrapedAt),
    sourceIdx: index("idx_scrape_sessions_source").on(table.source),
  }),
);

// Reddit search results for LEGO sets
export const redditSearchResults = pgTable(
  "reddit_search_results",
  {
    id: serial("id").primaryKey(),
    legoSetNumber: varchar("lego_set_number", { length: 20 }).notNull(),
    subreddit: varchar("subreddit", { length: 50 }).notNull().default("lego"),
    totalPosts: integer("total_posts").notNull().default(0),
    posts: jsonb("posts"), // Array of post objects with title, url, score, num_comments, etc.
    searchedAt: timestamp("searched_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for looking up by LEGO set number
    legoSetNumberIdx: index("idx_reddit_lego_set_number").on(
      table.legoSetNumber,
    ),
    // Index for time-based queries
    searchedAtIdx: index("idx_reddit_searched_at").on(table.searchedAt),
  }),
);

// BrickRanker retirement tracking
export const brickrankerRetirementItems = pgTable(
  "brickranker_retirement_items",
  {
    id: serial("id").primaryKey(),
    setNumber: varchar("set_number", { length: 20 }).notNull().unique(),
    setName: text("set_name").notNull(),
    yearReleased: integer("year_released"),
    retiringSoon: boolean("retiring_soon").default(false).notNull(),
    expectedRetirementDate: varchar("expected_retirement_date", { length: 50 }),
    theme: varchar("theme", { length: 100 }),

    // Optional link to products table for sets we already track
    productId: integer("product_id"),

    // Track if set is still listed on the retirement tracker page
    isActive: boolean("is_active").default(true).notNull(),

    // Scraping schedule configuration
    scrapeIntervalDays: integer("scrape_interval_days").default(30).notNull(),
    lastScrapedAt: timestamp("last_scraped_at"),
    nextScrapeAt: timestamp("next_scrape_at"),

    // Metadata
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for fast lookups by set number
    setNumberIdx: index("idx_brickranker_set_number").on(table.setNumber),
    // Index for matching with products table
    productIdIdx: index("idx_brickranker_product_id").on(table.productId),
    // Index for theme filtering
    themeIdx: index("idx_brickranker_theme").on(table.theme),
    // Index for active items
    isActiveIdx: index("idx_brickranker_is_active").on(table.isActive),
    // Index for efficient scraping queue queries
    nextScrapeAtIdx: index("idx_brickranker_next_scrape_at").on(
      table.nextScrapeAt,
    ),
  }),
);

// Product analysis cache table
export const productAnalysis = pgTable(
  "product_analysis",
  {
    id: serial("id").primaryKey(),
    productId: varchar("product_id", { length: 100 }).notNull(),
    strategy: varchar("strategy", { length: 50 }).notNull(),

    // Overall score and recommendation
    overallScore: integer("overall_score").notNull(), // 0-100
    confidence: integer("confidence").notNull(), // 0-100 (confidence * 100)
    action: varchar("action", { length: 20 }).notNull(), // strong_buy, buy, hold, pass
    urgency: varchar("urgency", { length: 20 }).notNull(), // urgent, moderate, low, no_rush

    // Dimensional scores (JSONB for flexibility)
    dimensionalScores: jsonb("dimensional_scores").notNull(),

    // Investment metrics
    estimatedROI: integer("estimated_roi"), // Percentage
    timeHorizon: varchar("time_horizon", { length: 100 }),

    // Risks and opportunities
    risks: jsonb("risks"), // Array of strings
    opportunities: jsonb("opportunities"), // Array of strings

    // Full recommendation data (for detailed view)
    fullRecommendation: jsonb("full_recommendation").notNull(),

    // Metadata
    analyzedAt: timestamp("analyzed_at").defaultNow().notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => ({
    // Composite unique index for product + strategy
    productStrategyIdx: index("idx_analysis_product_strategy").on(
      table.productId,
      table.strategy,
    ),
    // Index for filtering by action
    actionIdx: index("idx_analysis_action").on(table.action),
    // Index for filtering by urgency
    urgencyIdx: index("idx_analysis_urgency").on(table.urgency),
    // Index for sorting by score
    scoreIdx: index("idx_analysis_score").on(table.overallScore),
    // Index for time-based cache invalidation
    analyzedAtIdx: index("idx_analysis_analyzed_at").on(table.analyzedAt),
  }),
);

// Type exports for TypeScript
export type BricklinkItem = typeof bricklinkItems.$inferSelect;
export type NewBricklinkItem = typeof bricklinkItems.$inferInsert;

export type BricklinkPriceHistory = typeof bricklinkPriceHistory.$inferSelect;
export type NewBricklinkPriceHistory =
  typeof bricklinkPriceHistory.$inferInsert;

export type Product = typeof products.$inferSelect;
export type NewProduct = typeof products.$inferInsert;

export type PriceHistory = typeof priceHistory.$inferSelect;
export type NewPriceHistory = typeof priceHistory.$inferInsert;

export type ScrapeSession = typeof scrapeSessions.$inferSelect;
export type NewScrapeSession = typeof scrapeSessions.$inferInsert;

export type RedditSearchResult = typeof redditSearchResults.$inferSelect;
export type NewRedditSearchResult = typeof redditSearchResults.$inferInsert;

export type BrickrankerRetirementItem =
  typeof brickrankerRetirementItems.$inferSelect;
export type NewBrickrankerRetirementItem =
  typeof brickrankerRetirementItems.$inferInsert;

export type ProductAnalysis = typeof productAnalysis.$inferSelect;
export type NewProductAnalysis = typeof productAnalysis.$inferInsert;

export type WatchStatus = "active" | "paused" | "stopped" | "archived";
export type ProductSource = "shopee" | "toysrus" | "self";

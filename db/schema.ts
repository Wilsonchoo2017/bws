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
  unique,
  uuid,
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
  "brickeconomy",
  "bricklink",
  "worldbricks",
  "brickranker",
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

    // Image fields
    imageUrl: text("image_url"),
    localImagePath: text("local_image_path"),
    imageDownloadedAt: timestamp("image_downloaded_at"),
    imageDownloadStatus: varchar("image_download_status", { length: 20 }),

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
    // Index for image download status
    imageStatusIdx: index("idx_bricklink_image_status").on(
      table.imageDownloadStatus,
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
    productId: uuid("product_id").notNull().unique().defaultRandom(),
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
    localImagePath: text("local_image_path"),
    localImages: jsonb("local_images"),
    imageDownloadedAt: timestamp("image_downloaded_at"),
    imageDownloadStatus: varchar("image_download_status", { length: 20 }),

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

    // Time-limited tags for promotions/vouchers
    tags: jsonb("tags"), // Array of {tagId: string, addedAt: string}

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
    imageStatusIdx: index("idx_products_image_status").on(
      table.imageDownloadStatus,
    ),
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

// Product tags for time-limited promotions/vouchers
export const productTags = pgTable(
  "product_tags",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    name: varchar("name", { length: 100 }).notNull().unique(),
    description: text("description"),
    endDate: timestamp("end_date"), // Null = no expiry
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for name lookup
    nameIdx: index("idx_product_tags_name").on(table.name),
    // Index for finding expired tags
    endDateIdx: index("idx_product_tags_end_date").on(table.endDate),
  }),
);

// Unified price history for tracking price changes over time (all platforms)
export const priceHistory = pgTable(
  "price_history",
  {
    id: serial("id").primaryKey(),
    productId: uuid("product_id").notNull(),
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

// Shopee scrapes table - time-series data for Shopee products
// This table stores product snapshots at each scrape time
// Only includes fields that are actually scraped from Shopee
export const shopeeScrapes = pgTable(
  "shopee_scrapes",
  {
    id: serial("id").primaryKey(),

    // Foreign key to products table
    productId: uuid("product_id").notNull(),

    // Foreign key to scrape session
    scrapeSessionId: integer("scrape_session_id"),

    // Price data (only what's actually scraped)
    price: bigint("price", { mode: "number" }),
    currency: varchar("currency", { length: 10 }),

    // Sales data
    unitsSold: bigint("units_sold", { mode: "number" }),

    // Shop data
    shopId: bigint("shop_id", { mode: "number" }),
    shopName: varchar("shop_name", { length: 255 }),

    // Product URL (may change over time)
    productUrl: text("product_url"),

    // Full data snapshot
    rawData: jsonb("raw_data"),

    // Timestamp - critical for timeline queries
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for product lookup
    productIdIdx: index("idx_shopee_scrapes_product_id").on(table.productId),

    // Index for session lookup
    sessionIdIdx: index("idx_shopee_scrapes_session_id").on(
      table.scrapeSessionId,
    ),

    // Composite index for time-series queries (most important!)
    productTimeIdx: index("idx_shopee_scrapes_product_time").on(
      table.productId,
      table.scrapedAt,
    ),

    // Index for shop queries
    shopIdIdx: index("idx_shopee_scrapes_shop_id").on(table.shopId),

    // Index for time-based queries
    scrapedAtIdx: index("idx_shopee_scrapes_scraped_at").on(table.scrapedAt),
  }),
);

// Bricklink price history for tracking price changes over time (legacy JSONB format)
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

// Enum for condition type (new vs used)
export const conditionEnum = pgEnum("condition_type", ["new", "used"]);

// Enum for time period (6-month vs current)
export const timePeriodEnum = pgEnum("time_period", ["six_month", "current"]);

// Normalized Bricklink volume history for dashboard-friendly time-series tracking
export const bricklinkVolumeHistory = pgTable(
  "bricklink_volume_history",
  {
    id: serial("id").primaryKey(),
    itemId: varchar("item_id", { length: 50 }).notNull(),

    // Condition and time period for this record
    condition: conditionEnum("condition").notNull(),
    timePeriod: timePeriodEnum("time_period").notNull(),

    // Volume and transaction metrics
    totalQty: integer("total_qty"), // Total quantity sold (main metric)
    timesSold: integer("times_sold"), // Number of transactions
    totalLots: integer("total_lots"), // Number of lots sold

    // Price metrics (stored as cents/smallest currency unit)
    minPrice: integer("min_price"),
    avgPrice: integer("avg_price"),
    qtyAvgPrice: integer("qty_avg_price"), // Quantity-weighted average
    maxPrice: integer("max_price"),
    currency: varchar("currency", { length: 3 }).default("USD"),

    // Timestamp for time-series tracking
    recordedAt: timestamp("recorded_at").defaultNow().notNull(),
  },
  (table) => ({
    // Composite index for efficient time-series queries
    itemConditionTimeIdx: index("idx_bricklink_volume_item_condition_time").on(
      table.itemId,
      table.condition,
      table.timePeriod,
      table.recordedAt,
    ),
    // Index for filtering by condition
    conditionIdx: index("idx_bricklink_volume_condition").on(table.condition),
    // Index for time-based queries
    recordedAtIdx: index("idx_bricklink_volume_recorded_at").on(
      table.recordedAt,
    ),
  }),
);

// Bricklink past sales transactions - individual sale records
export const bricklinkPastSales = pgTable(
  "bricklink_past_sales",
  {
    id: serial("id").primaryKey(),
    itemId: varchar("item_id", { length: 50 }).notNull(),

    // Transaction details
    dateSold: timestamp("date_sold").notNull(),
    condition: conditionEnum("condition").notNull(),

    // Price (stored as cents/smallest currency unit)
    price: integer("price").notNull(),
    currency: varchar("currency", { length: 3 }).notNull().default("USD"),

    // Optional fields
    sellerLocation: varchar("seller_location", { length: 100 }),
    quantity: integer("quantity"),

    // Metadata
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    // Composite index for efficient item queries
    itemDateIdx: index("idx_bricklink_past_sales_item_date").on(
      table.itemId,
      table.dateSold,
    ),
    // Index for date-based queries
    dateSoldIdx: index("idx_bricklink_past_sales_date_sold").on(
      table.dateSold,
    ),
    // Index for condition filtering
    conditionIdx: index("idx_bricklink_past_sales_condition").on(
      table.condition,
    ),
    // Unique constraint to prevent duplicate transactions
    uniqueTransaction: unique("unique_bricklink_past_sale").on(
      table.itemId,
      table.dateSold,
      table.condition,
      table.price,
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

    // Optional session label for promotion tracking (e.g., "12.12 Sale")
    sessionLabel: varchar("session_label", { length: 255 }),

    // Filter context - what shop filter was used during scrape
    filterContext: text("filter_context"),

    // Shop name for Shopee scrapes
    shopName: varchar("shop_name", { length: 255 }),

    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    scrapedAtIdx: index("idx_scrape_sessions_scraped_at").on(table.scrapedAt),
    sourceIdx: index("idx_scrape_sessions_source").on(table.source),
    shopNameIdx: index("idx_scrape_sessions_shop_name").on(table.shopName),
  }),
);

// Raw HTML/API response data for all scrapers
// Stores compressed raw data for debugging, testing, and re-parsing
export const scrapeRawData = pgTable(
  "scrape_raw_data",
  {
    id: serial("id").primaryKey(),

    // Foreign key to scrape session
    scrapeSessionId: integer("scrape_session_id").notNull(),

    // Source and URL information
    source: productSourceEnum("source").notNull(),
    sourceUrl: text("source_url").notNull(),

    // Raw HTML/data storage (gzip compressed)
    rawHtmlCompressed: text("raw_html_compressed").notNull(), // Base64-encoded gzipped data
    rawHtmlSize: integer("raw_html_size").notNull(), // Original size in bytes
    compressedSize: integer("compressed_size").notNull(), // Compressed size in bytes

    // Metadata
    contentType: varchar("content_type", { length: 100 }).default("text/html"),
    httpStatus: integer("http_status"), // HTTP response status code (if applicable)

    // Timestamp
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for scrape session lookup
    scrapeSessionIdIdx: index("idx_scrape_raw_data_session_id").on(table.scrapeSessionId),

    // Index for source filtering
    sourceIdx: index("idx_scrape_raw_data_source").on(table.source),

    // Index for time-based queries
    scrapedAtIdx: index("idx_scrape_raw_data_scraped_at").on(table.scrapedAt),

    // Composite index for efficient session + source queries
    sessionSourceIdx: index("idx_scrape_raw_data_session_source").on(
      table.scrapeSessionId,
      table.source,
    ),
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

    // Scheduling fields (similar to bricklink_items)
    watchStatus: watchStatusEnum("watch_status").default("active").notNull(),
    scrapeIntervalDays: integer("scrape_interval_days").default(30).notNull(),
    lastScrapedAt: timestamp("last_scraped_at"),
    nextScrapeAt: timestamp("next_scrape_at"),

    // Metadata
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for looking up by LEGO set number
    legoSetNumberIdx: index("idx_reddit_lego_set_number").on(
      table.legoSetNumber,
    ),
    // Index for time-based queries
    searchedAtIdx: index("idx_reddit_searched_at").on(table.searchedAt),
    // Index for filtering by watch status
    watchStatusIdx: index("idx_reddit_watch_status").on(table.watchStatus),
    // Index for efficient scraping queue queries
    nextScrapeAtIdx: index("idx_reddit_next_scrape_at").on(
      table.nextScrapeAt,
    ),
    // Unique constraint to prevent duplicate search results for same set/subreddit
    uniqueSetSubreddit: unique("unique_lego_set_subreddit").on(
      table.legoSetNumber,
      table.subreddit,
    ),
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

    // Image fields
    imageUrl: text("image_url"),
    localImagePath: text("local_image_path"),
    imageDownloadedAt: timestamp("image_downloaded_at"),
    imageDownloadStatus: varchar("image_download_status", { length: 20 }),

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
    // Index for image download status
    imageStatusIdx: index("idx_brickranker_image_status").on(
      table.imageDownloadStatus,
    ),
  }),
);

// Product analysis cache table
export const productAnalysis = pgTable(
  "product_analysis",
  {
    id: serial("id").primaryKey(),
    productId: uuid("product_id").notNull(),
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

export type BricklinkVolumeHistory = typeof bricklinkVolumeHistory.$inferSelect;
export type NewBricklinkVolumeHistory =
  typeof bricklinkVolumeHistory.$inferInsert;

export type Product = typeof products.$inferSelect;
export type NewProduct = typeof products.$inferInsert;

export type ProductTag = typeof productTags.$inferSelect;
export type NewProductTag = typeof productTags.$inferInsert;

export type PriceHistory = typeof priceHistory.$inferSelect;
export type NewPriceHistory = typeof priceHistory.$inferInsert;

export type ShopeeScrape = typeof shopeeScrapes.$inferSelect;
export type NewShopeeScrape = typeof shopeeScrapes.$inferInsert;

export type ScrapeSession = typeof scrapeSessions.$inferSelect;
export type NewScrapeSession = typeof scrapeSessions.$inferInsert;

export type ScrapeRawData = typeof scrapeRawData.$inferSelect;
export type NewScrapeRawData = typeof scrapeRawData.$inferInsert;

export type RedditSearchResult = typeof redditSearchResults.$inferSelect;
export type NewRedditSearchResult = typeof redditSearchResults.$inferInsert;

export type BrickrankerRetirementItem =
  typeof brickrankerRetirementItems.$inferSelect;
export type NewBrickrankerRetirementItem =
  typeof brickrankerRetirementItems.$inferInsert;

export type ProductAnalysis = typeof productAnalysis.$inferSelect;
export type NewProductAnalysis = typeof productAnalysis.$inferInsert;

// WorldBricks LEGO set information
export const worldbricksSets = pgTable(
  "worldbricks_sets",
  {
    id: serial("id").primaryKey(),
    setNumber: varchar("set_number", { length: 20 }).notNull().unique(),
    setName: text("set_name"),
    description: text("description"),

    // Primary fields (year released and retired year are high priority)
    yearReleased: integer("year_released"),
    yearRetired: integer("year_retired"),

    // Secondary fields
    designer: varchar("designer", { length: 255 }),
    partsCount: integer("parts_count"),
    dimensions: varchar("dimensions", { length: 255 }),

    // Media
    imageUrl: text("image_url"),
    localImagePath: text("local_image_path"),
    imageDownloadedAt: timestamp("image_downloaded_at"),
    imageDownloadStatus: varchar("image_download_status", { length: 20 }),

    // Source tracking
    sourceUrl: text("source_url"),

    // Scraping metadata
    lastScrapedAt: timestamp("last_scraped_at"),
    scrapeStatus: varchar("scrape_status", { length: 20 }), // success, failed, partial

    // Scheduling fields for automated scraping
    scrapeIntervalDays: integer("scrape_interval_days").default(90), // 90 days = 3 months
    nextScrapeAt: timestamp("next_scrape_at"),

    // Timestamps
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for fast lookups by set number
    setNumberIdx: index("idx_worldbricks_set_number").on(table.setNumber),
    // Index for year filtering
    yearReleasedIdx: index("idx_worldbricks_year_released").on(
      table.yearReleased,
    ),
    yearRetiredIdx: index("idx_worldbricks_year_retired").on(table.yearRetired),
    // Index for image download status
    imageStatusIdx: index("idx_worldbricks_image_status").on(
      table.imageDownloadStatus,
    ),
    // Index for scrape status
    scrapeStatusIdx: index("idx_worldbricks_scrape_status").on(
      table.scrapeStatus,
    ),
    // Index for next scrape scheduling
    nextScrapeAtIdx: index("idx_worldbricks_next_scrape_at").on(
      table.nextScrapeAt,
    ),
  }),
);

export type WorldbricksSet = typeof worldbricksSets.$inferSelect;
export type NewWorldbricksSet = typeof worldbricksSets.$inferInsert;

export type WatchStatus = "active" | "paused" | "stopped" | "archived";
export type ProductSource = "shopee" | "toysrus" | "self";

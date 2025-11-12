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

    // Metadata
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Index for filtering by watch status
    watchStatusIdx: index("idx_bricklink_watch_status").on(table.watchStatus),
  }),
);

// Shopee scraped items
export const shopeeItems = pgTable(
  "shopee_items",
  {
    id: serial("id").primaryKey(),
    productId: varchar("product_id", { length: 100 }).notNull().unique(),
    name: text("name"),
    brand: varchar("brand", { length: 255 }),

    // Pricing
    currency: varchar("currency", { length: 10 }),
    price: bigint("price", { mode: "number" }),
    priceMin: bigint("price_min", { mode: "number" }),
    priceMax: bigint("price_max", { mode: "number" }),
    priceBeforeDiscount: bigint("price_before_discount", { mode: "number" }),

    // Stats
    sold: bigint("sold", { mode: "number" }),
    historical_sold: bigint("historical_sold", { mode: "number" }),
    liked_count: bigint("liked_count", { mode: "number" }),
    cmt_count: bigint("cmt_count", { mode: "number" }),
    view_count: bigint("view_count", { mode: "number" }),

    // Ratings
    itemRatingStarRating: bigint("item_rating_star_rating", {
      mode: "number",
    }),
    itemRatingRatingCount: jsonb("item_rating_rating_count"),

    // Product details
    stockInfoSummary: text("stock_info_summary"),
    stockInfoStockType: bigint("stock_info_stock_type", { mode: "number" }),
    stockInfoCurrentStock: bigint("stock_info_current_stock", {
      mode: "number",
    }),

    // Flags
    isAdult: boolean("is_adult"),
    isMart: boolean("is_mart"),
    isPreferred: boolean("is_preferred"),
    isServiceByShopee: boolean("is_service_by_shopee"),

    // Media
    image: text("image"),
    images: jsonb("images"),

    // Additional metadata
    shopId: bigint("shop_id", { mode: "number" }),
    shopName: varchar("shop_name", { length: 255 }),
    shopLocation: varchar("shop_location", { length: 255 }),

    // LEGO specific
    legoSetNumber: varchar("lego_set_number", { length: 10 }),

    // Full data dump for reference
    rawData: jsonb("raw_data"),

    // Watch status for price tracking
    watchStatus: watchStatusEnum("watch_status").default("active").notNull(),

    // Metadata
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => ({
    // Indexes for read performance
    productIdIdx: index("idx_shopee_product_id").on(table.productId),
    priceIdx: index("idx_shopee_price").on(table.price),
    soldIdx: index("idx_shopee_sold").on(table.sold),
    shopIdIdx: index("idx_shopee_shop_id").on(table.shopId),
    createdAtIdx: index("idx_shopee_created_at").on(table.createdAt),
    legoSetNumberIdx: index("idx_shopee_lego_set").on(table.legoSetNumber),
    watchStatusIdx: index("idx_shopee_watch_status").on(table.watchStatus),
    // Full-text search index on name
    nameSearchIdx: index("idx_shopee_name_search").using(
      "gin",
      sql`to_tsvector('english', ${table.name})`,
    ),
  }),
);

// Shopee price history for tracking price changes over time
export const shopeePriceHistory = pgTable(
  "shopee_price_history",
  {
    id: serial("id").primaryKey(),
    productId: varchar("product_id", { length: 100 }).notNull(),
    price: bigint("price", { mode: "number" }),
    priceBeforeDiscount: bigint("price_before_discount", { mode: "number" }),
    soldAtTime: bigint("sold_at_time", { mode: "number" }),
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

// Shopee scrape sessions for tracking scraping metadata
export const shopeeScrapeSessions = pgTable(
  "shopee_scrape_sessions",
  {
    id: serial("id").primaryKey(),
    sourceUrl: text("source_url"),
    productsFound: integer("products_found").notNull().default(0),
    productsStored: integer("products_stored").notNull().default(0),
    status: varchar("status", { length: 20 }).notNull().default("success"), // success, partial, failed
    errorMessage: text("error_message"),
    scrapedAt: timestamp("scraped_at").defaultNow().notNull(),
  },
  (table) => ({
    scrapedAtIdx: index("idx_scrape_sessions_scraped_at").on(table.scrapedAt),
  }),
);

// Type exports for TypeScript
export type BricklinkItem = typeof bricklinkItems.$inferSelect;
export type NewBricklinkItem = typeof bricklinkItems.$inferInsert;

export type BricklinkPriceHistory = typeof bricklinkPriceHistory.$inferSelect;
export type NewBricklinkPriceHistory = typeof bricklinkPriceHistory.$inferInsert;

export type ShopeeItem = typeof shopeeItems.$inferSelect;
export type NewShopeeItem = typeof shopeeItems.$inferInsert;

export type ShopeePriceHistory = typeof shopeePriceHistory.$inferSelect;
export type NewShopeePriceHistory = typeof shopeePriceHistory.$inferInsert;

export type ShopeeScrapeSessions = typeof shopeeScrapeSessions.$inferSelect;
export type NewShopeeScrapeSessions = typeof shopeeScrapeSessions.$inferInsert;

export type WatchStatus = "active" | "paused" | "stopped" | "archived";

import {
  bigint,
  boolean,
  jsonb,
  pgTable,
  serial,
  text,
  timestamp,
  varchar,
} from "drizzle-orm/pg-core";

// Bricklink scraped items
export const bricklinkItems = pgTable("bricklink_items", {
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

  // Metadata
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

// Shopee scraped items
export const shopeeItems = pgTable("shopee_items", {
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
  itemRatingStarRating: bigint("item_rating_star_rating", { mode: "number" }),
  itemRatingRatingCount: jsonb("item_rating_rating_count"),

  // Product details
  stockInfoSummary: text("stock_info_summary"),
  stockInfoStockType: bigint("stock_info_stock_type", { mode: "number" }),
  stockInfoCurrentStock: bigint("stock_info_current_stock", { mode: "number" }),

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

  // Full data dump for reference
  rawData: jsonb("raw_data"),

  // Metadata
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

// Type exports for TypeScript
export type BricklinkItem = typeof bricklinkItems.$inferSelect;
export type NewBricklinkItem = typeof bricklinkItems.$inferInsert;

export type ShopeeItem = typeof shopeeItems.$inferSelect;
export type NewShopeeItem = typeof shopeeItems.$inferInsert;

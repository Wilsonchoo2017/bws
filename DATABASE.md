# Database Setup Guide

PostgreSQL integration for Fresh.js API using Drizzle ORM.

## Tech Stack

- **PostgreSQL** - Database (via Docker)
- **Drizzle ORM** - Type-safe ORM with excellent TypeScript support
- **postgres** - Native Deno PostgreSQL driver
- **Zod** - Runtime schema validation

## Quick Start

### 1. Start PostgreSQL

From the root directory:

```bash
npm run db:up
```

This starts PostgreSQL on `localhost:5432` with:

- Database: `bws`
- User: `postgres`
- Password: `postgres`

### 2. Configure Environment

```bash
cd packages/api/api
cp .env.example .env
```

Edit `.env` if needed (default works with docker-compose setup).

### 3. Generate and Run Migrations

```bash
# Generate migration files from schema
deno task db:generate

# Apply migrations to database
deno task db:migrate
```

### 4. Start the API

```bash
deno task start
```

## Database Schema

### Bricklink Items

Stores scraped Bricklink product data with pricing history.

**Table**: `bricklink_items`

| Column         | Type        | Description                   |
| -------------- | ----------- | ----------------------------- |
| id             | serial      | Primary key                   |
| item_id        | varchar(50) | Bricklink item ID (unique)    |
| item_type      | varchar(10) | Type (P, S, M, G, C, I, O, B) |
| title          | text        | Item title                    |
| weight         | varchar(50) | Item weight                   |
| six_month_new  | jsonb       | 6-month new pricing data      |
| six_month_used | jsonb       | 6-month used pricing data     |
| current_new    | jsonb       | Current new pricing data      |
| current_used   | jsonb       | Current used pricing data     |
| created_at     | timestamp   | Creation timestamp            |
| updated_at     | timestamp   | Last update timestamp         |

### Shopee Items

Stores scraped Shopee product data.

**Table**: `shopee_items`

| Column     | Type         | Description                      |
| ---------- | ------------ | -------------------------------- |
| id         | serial       | Primary key                      |
| product_id | varchar(100) | Shopee product ID (unique)       |
| name       | text         | Product name                     |
| price      | bigint       | Current price                    |
| sold       | bigint       | Units sold                       |
| ...        | ...          | Many more fields (see schema.ts) |

## API Endpoints

### Bricklink Items

#### List all items

```bash
GET /api/bricklink-items
```

#### Get specific item

```bash
GET /api/bricklink-items?item_id=75192
```

#### Create item

```bash
POST /api/bricklink-items
Content-Type: application/json

{
  "item_id": "75192",
  "item_type": "S",
  "title": "Millennium Falcon",
  "weight": "10kg",
  "current_new": {
    "times_sold": 100,
    "avg_price": {
      "currency": "USD",
      "amount": 849.99
    }
  }
}
```

#### Update item

```bash
PUT /api/bricklink-items?item_id=75192
Content-Type: application/json

{
  "title": "Updated Title",
  "current_new": { ... }
}
```

#### Delete item

```bash
DELETE /api/bricklink-items?item_id=75192
```

### Scraper Integration

The scraper endpoint now supports auto-saving to database:

```bash
# Scrape and save to database
GET /api/scrape-bricklink?url=https://www.bricklink.com/v2/catalog/catalogitem.page?S=75192&save=true

# Scrape only (no save)
GET /api/scrape-bricklink?url=https://www.bricklink.com/v2/catalog/catalogitem.page?S=75192
```

## Database Tasks

### Generate Migration

After modifying `db/schema.ts`:

```bash
deno task db:generate
```

### Run Migrations

```bash
deno task db:migrate
```

### Open Drizzle Studio

Visual database browser:

```bash
deno task db:studio
```

## Development Workflow

1. **Modify Schema** - Edit `db/schema.ts`
2. **Generate Migration** - `deno task db:generate`
3. **Review Migration** - Check `drizzle/` directory
4. **Apply Migration** - `deno task db:migrate`
5. **Use in Routes** - Import `db` from `db/client.ts`

## Type Safety

Everything is fully typed:

```typescript
import { db } from "../db/client.ts";
import { bricklinkItems } from "../db/schema.ts";
import { eq } from "drizzle-orm";

// Type-safe queries
const items = await db.select().from(bricklinkItems);
// items is: BricklinkItem[]

const item = await db.query.bricklinkItems.findFirst({
  where: eq(bricklinkItems.itemId, "75192"),
});
// item is: BricklinkItem | undefined

// Type-safe inserts
await db.insert(bricklinkItems).values({
  itemId: "75192",
  itemType: "S",
  // TypeScript ensures all required fields are present
});
```

## Connection Management

The database connection pool is automatically managed:

- Max 10 connections
- 20s idle timeout
- Graceful shutdown on SIGINT/SIGTERM

## Troubleshooting

### Can't connect to database

1. Ensure PostgreSQL is running: `npm run db:up`
2. Check connection string in `.env`
3. Verify database exists: `psql -h localhost -U postgres -d bws`

### Migration errors

1. Check schema syntax in `db/schema.ts`
2. Review generated migration in `drizzle/` directory
3. Drop and recreate database if needed (dev only):
   ```bash
   npm run db:down
   npm run db:up
   deno task db:migrate
   ```

### Type errors

Run `deno check **/*.ts` to verify TypeScript compilation.

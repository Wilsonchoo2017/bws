# BWS - Bricklink Warehouse System

A Fresh.js web application for scraping and managing LEGO product data from
Bricklink and Shopee, with PostgreSQL integration.

## Features

- Web scraping for Bricklink product data
- Shopee HTML parsing and data extraction
- PostgreSQL database with Drizzle ORM
- Type-safe database queries
- Price history tracking
- RESTful API endpoints

## Prerequisites

- [Deno](https://deno.land/manual/getting_started/installation) 1.37 or higher
- [Docker](https://docs.docker.com/get-docker/) (for PostgreSQL)
- Node.js/npm (for docker-compose commands)

## Quick Start

### 1. Start the Database

```bash
npm run db:up
```

This starts PostgreSQL on `localhost:5432` with:

- Database: `bws`
- User: `postgres`
- Password: `postgres`

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` if you want to customize the database connection.

### 3. Run Migrations

```bash
# Generate migration files from schema
deno task db:generate

# Apply migrations to database
deno task db:migrate
```

### 4. Start the Development Server

```bash
deno task start
```

The app will be available at `http://localhost:8000`

## Project Structure

```
.
├── db/                      # Database configuration
│   ├── client.ts           # Database connection
│   ├── schema.ts           # Drizzle ORM schema
│   ├── migrate.ts          # Migration runner
│   └── utils.ts            # Helper functions
├── routes/                  # Fresh.js routes
│   ├── api/
│   │   ├── bricklink-items.ts    # Bricklink CRUD API
│   │   ├── scrape-bricklink.ts   # Bricklink scraper
│   │   └── parse-shopee.ts       # Shopee parser
│   └── index.tsx           # Home page
├── drizzle/                # Generated migrations
├── docker-compose.yml      # PostgreSQL setup
└── DATABASE.md            # Detailed database docs
```

## API Endpoints

### Bricklink Items

- `GET /api/bricklink-items` - List all items
- `GET /api/bricklink-items?item_id=75192` - Get specific item
- `POST /api/bricklink-items` - Create item
- `PUT /api/bricklink-items?item_id=75192` - Update item
- `DELETE /api/bricklink-items?item_id=75192` - Delete item

### Scrapers

- `GET /api/scrape-bricklink?url=...&save=true` - Scrape Bricklink page
- `POST /api/parse-shopee` - Parse Shopee HTML

See [DATABASE.md](./DATABASE.md) for detailed API documentation.

## Available Tasks

### Development

- `deno task start` - Start dev server with hot reload
- `deno task check` - Run linting and type checking
- `deno task build` - Build for production
- `deno task preview` - Preview production build

### Database

- `deno task db:generate` - Generate migrations from schema
- `deno task db:migrate` - Run pending migrations
- `deno task db:studio` - Open Drizzle Studio (visual DB browser)

### Docker

- `npm run db:up` - Start PostgreSQL container
- `npm run db:down` - Stop and remove containers
- `npm run db:logs` - View PostgreSQL logs

## Database Schema

### Bricklink Items

Stores scraped product data from Bricklink with pricing history in JSONB format.

### Shopee Items

Stores scraped product data from Shopee with:

- Product details (name, brand, price)
- Sales metrics (sold, views, likes)
- Rating information
- Shop details
- LEGO set number extraction
- Full-text search support

### Price History

Tracks Shopee price changes over time.

See [DATABASE.md](./DATABASE.md) for complete schema documentation.

## Development

The project uses Fresh 1.7.3 with:

- Preact for UI components
- Drizzle ORM for type-safe database queries
- PostgreSQL for data storage
- Tailwind CSS & DaisyUI for styling

## License

ISC

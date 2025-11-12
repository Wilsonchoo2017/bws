# Bricklink Scraper Architecture

## Overview

The Bricklink scraper has been refactored following SOLID principles with
maximum anti-bot protection, conservative rate limiting (2-5 minute delays), and
background job processing.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     HTTP Request Layer                       │
│  routes/api/scrape-bricklink.ts                              │
│  routes/api/scrape-queue-status.ts                           │
│  routes/api/scrape-scheduler.ts                              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                    Service Layer                             │
│                                                              │
│  ┌─────────────────────────────────────────────────┐        │
│  │  QueueService (BullMQ + Redis)                  │        │
│  │  - Job queue management                          │        │
│  │  - Worker processing                             │        │
│  │  - Retry logic                                   │        │
│  └──────────────────┬──────────────────────────────┘        │
│                     │                                         │
│  ┌─────────────────▼──────────────────────────────┐         │
│  │  BricklinkScraperService (Orchestrator)        │         │
│  │  - Workflow coordination                        │         │
│  │  - Circuit breaker                              │         │
│  │  - Error handling                               │         │
│  └──┬──────────┬──────────┬─────────────────────┬─┘         │
│     │          │          │                     │            │
│  ┌──▼──┐  ┌───▼────┐  ┌──▼────────┐  ┌────────▼─────┐      │
│  │HTTP │  │Rate    │  │Parser     │  │Repository    │      │
│  │Client│  │Limiter │  │(Pure Fns) │  │(Data Access) │      │
│  └──────┘  └────────┘  └───────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. HttpClientService (`services/http/HttpClientService.ts`)

**Responsibility**: Manage browser automation with maximum anti-bot protection

**Features**:

- Puppeteer browser automation
- User agent rotation (30+ agents)
- Viewport randomization
- Request header rotation
- Cookie and session management
- Human behavior simulation (mouse movements, scrolling, delays)
- Removes automation indicators

**Anti-Bot Measures**:

- ✅ Browser fingerprinting prevention
- ✅ User agent rotation
- ✅ Random viewports
- ✅ Human-like behavior simulation
- ✅ Natural timing patterns
- ✅ Automated detection removal

### 2. RateLimiterService (`services/rate-limiter/RateLimiterService.ts`)

**Responsibility**: Enforce conservative rate limiting (2-5 minutes between
requests)

**Features**:

- Token bucket algorithm
- Random delays with jitter (2-5 minutes)
- Per-domain rate limiting
- Hourly request limits (max 15 requests/hour)
- Request history tracking

**Configuration**:

- Min delay: 2 minutes
- Max delay: 5 minutes
- Max concurrent jobs: 1
- Max requests per hour: 15

### 3. BricklinkParser (`services/bricklink/BricklinkParser.ts`)

**Responsibility**: Pure functions for HTML parsing and data extraction

**Features**:

- URL parsing and validation
- Item information extraction
- Price guide parsing
- Data comparison utilities
- Zero side effects (testable)

**Functions**:

- `parseBricklinkUrl()` - Extract item type and ID
- `parseItemInfo()` - Extract title and weight
- `parsePriceGuide()` - Extract pricing boxes
- `extractPriceBox()` - Parse individual pricing data
- `hasDataChanged()` - Compare pricing data

### 4. BricklinkRepository (`services/bricklink/BricklinkRepository.ts`)

**Responsibility**: Database access layer following Repository pattern

**Features**:

- CRUD operations for bricklink_items
- Price history management
- Query building
- Upsert logic
- Scraping timestamp management

**Methods**:

- `findByItemId()` - Get item by Bricklink ID
- `create()` - Create new item
- `update()` - Update existing item
- `upsert()` - Create or update
- `findItemsNeedingScraping()` - Get items needing scraping
- `createPriceHistory()` - Record price changes

### 5. BricklinkScraperService (`services/bricklink/BricklinkScraperService.ts`)

**Responsibility**: High-level orchestration of scraping workflow

**Features**:

- Coordinate all services
- Retry logic with exponential backoff
- Circuit breaker pattern
- Error handling
- Database persistence

**Circuit Breaker**:

- Opens after 5 consecutive failures
- Timeout: 10 minutes
- Prevents cascade failures

### 6. QueueService (`services/queue/QueueService.ts`)

**Responsibility**: Background job processing with BullMQ

**Features**:

- Job queue management (BullMQ + Redis)
- Worker processing
- Job types: single scrape, bulk scrape, scheduled scrape
- Retry with exponential backoff
- Job monitoring and status

**Job Types**:

- `scrape-single-item` - Single URL scraping
- `scrape-bulk-items` - Multiple URLs
- `scrape-scheduled-items` - Automated interval-based scraping

### 7. SchedulerService (`services/scheduler/SchedulerService.ts`)

**Responsibility**: Automated interval-based scraping

**Features**:

- Find items needing scraping
- Enqueue jobs automatically
- Preview upcoming scrapes
- Clean old jobs

## Database Schema

### bricklink_items Table

New columns added:

- `scrape_interval_days` (integer, default: 30) - Scraping frequency
- `last_scraped_at` (timestamp, nullable) - Last scrape time
- `next_scrape_at` (timestamp, nullable) - Next scheduled scrape

**Index**: `idx_bricklink_next_scrape_at` for efficient scheduling queries

## API Endpoints

### 1. POST /api/scrape-bricklink?url=...&save=true

Enqueue a scraping job for a single Bricklink item.

**Parameters**:

- `url` (required) - Bricklink item URL
- `save` (optional, default: true) - Save to database

**Response**:

```json
{
  "message": "Scraping job enqueued successfully",
  "job": {
    "id": "1234",
    "itemId": "75192",
    "itemType": "S",
    "url": "https://...",
    "saveToDb": true,
    "status": "queued"
  }
}
```

### 2. GET /api/scrape-queue-status?job_id=...

Get status of scraping jobs.

**Without job_id**: Get queue statistics **With job_id**: Get specific job
status

**Response (without job_id)**:

```json
{
  "queue": {
    "name": "bricklink-scraper",
    "counts": {
      "waiting": 3,
      "active": 1,
      "completed": 10,
      "failed": 0,
      "delayed": 0
    }
  },
  "jobs": {
    "waiting": [...],
    "active": [...],
    "completed": [...],
    "failed": [...]
  }
}
```

### 3. GET /api/scrape-scheduler

Preview items that will be scraped in the next scheduler run.

**Response**:

```json
{
  "preview": {
    "count": 5,
    "items": [
      {
        "itemId": "75192",
        "itemType": "S",
        "title": "Millennium Falcon",
        "lastScrapedAt": "2024-01-01T00:00:00Z",
        "nextScrapeAt": "2024-01-31T00:00:00Z",
        "scrapeIntervalDays": 30
      }
    ]
  }
}
```

### 4. POST /api/scrape-scheduler

Trigger the scheduler to enqueue jobs for items needing scraping.

**Response**:

```json
{
  "message": "Scheduler run completed successfully",
  "result": {
    "itemsFound": 5,
    "jobsEnqueued": 5,
    "errors": [],
    "timestamp": "2024-01-15T10:00:00Z"
  }
}
```

### 5. PUT /api/bricklink-items?item_id=...

Update item configuration (including scrape interval).

**Body**:

```json
{
  "scrape_interval_days": 7,
  "watch_status": "active"
}
```

## Configuration

### Environment Variables

Create a `.env` file:

```bash
# Redis Configuration (required for queue)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Proxy Configuration (optional)
PROXY_ENABLED=false
PROXY_LIST=proxy1.com:8080,proxy2.com:8080

# Database (already configured)
DATABASE_URL=postgresql://...
```

### Scraper Configuration

Edit `config/scraper.config.ts`:

```typescript
export const RATE_LIMIT_CONFIG = {
  MIN_DELAY_MS: 2 * 60 * 1000, // 2 minutes
  MAX_DELAY_MS: 5 * 60 * 1000, // 5 minutes
  MAX_CONCURRENT_JOBS: 1,
  MAX_REQUESTS_PER_HOUR: 15,
};

export const SCRAPE_INTERVALS = {
  DEFAULT_INTERVAL_DAYS: 30,
  MIN_INTERVAL_DAYS: 1,
  MAX_INTERVAL_DAYS: 365,
};
```

## Setup Instructions

### 1. Install Redis

**macOS**:

```bash
brew install redis
brew services start redis
```

**Linux**:

```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Docker**:

```bash
docker run -d -p 6379:6379 redis:latest
```

### 2. Run Database Migration

```bash
deno task db:migrate
```

### 3. Start the Application

```bash
deno task start
```

The queue worker will automatically start and begin processing jobs.

## Usage Examples

### 1. Scrape a Single Item

```bash
curl -X POST "http://localhost:8000/api/scrape-bricklink?url=https://www.bricklink.com/v2/catalog/catalogitem.page?S=75192"
```

### 2. Check Job Status

```bash
curl "http://localhost:8000/api/scrape-queue-status?job_id=1234"
```

### 3. Preview Scheduled Scrapes

```bash
curl "http://localhost:8000/api/scrape-scheduler"
```

### 4. Trigger Scheduler

```bash
curl -X POST "http://localhost:8000/api/scrape-scheduler"
```

### 5. Update Scraping Interval

```bash
curl -X PUT "http://localhost:8000/api/bricklink-items?item_id=75192" \
  -H "Content-Type: application/json" \
  -d '{"scrape_interval_days": 7}'
```

## Automated Scheduling (Optional)

To run the scheduler automatically, set up a cron job:

```bash
# Run scheduler every hour
0 * * * * curl -X POST http://localhost:8000/api/scrape-scheduler

# Run scheduler every 6 hours
0 */6 * * * curl -X POST http://localhost:8000/api/scrape-scheduler

# Run scheduler daily at midnight
0 0 * * * curl -X POST http://localhost:8000/api/scrape-scheduler
```

Or use Deno cron in `main.ts`:

```typescript
Deno.cron("scrape scheduler", "0 */6 * * *", async () => {
  const scheduler = getScheduler();
  await scheduler.run();
});
```

## SOLID Principles Applied

### Single Responsibility Principle (SRP)

- Each service has ONE clear responsibility
- HttpClientService → HTTP requests
- RateLimiterService → Rate limiting
- BricklinkParser → Parsing
- BricklinkRepository → Database access
- BricklinkScraperService → Orchestration
- QueueService → Job management

### Open/Closed Principle (OCP)

- Services are open for extension (can add new features)
- Closed for modification (core logic doesn't need changes)
- Configuration-driven behavior

### Liskov Substitution Principle (LSP)

- Services can be substituted with mocks for testing
- Interfaces are consistent

### Interface Segregation Principle (ISP)

- Focused interfaces
- No bloated service objects
- Clear method purposes

### Dependency Inversion Principle (DIP)

- Services depend on abstractions
- Dependency injection used throughout
- Easy to swap implementations

## Testing

The architecture makes testing easy:

```typescript
// Mock HTTP client for testing
const mockHttpClient = {
  fetch: () => Promise.resolve({ html: "...", status: 200, url: "..." }),
  close: () => Promise.resolve(),
};

// Mock rate limiter for testing (no delays)
const mockRateLimiter = {
  waitForNextRequest: () => Promise.resolve(),
};

// Test scraper with mocks
const scraper = createBricklinkScraperService(
  mockHttpClient,
  mockRateLimiter,
  repository,
);
```

## Monitoring

### Queue Dashboard

Install Bull Board for visual monitoring:

```typescript
// Add to main.ts
import { createBullBoard } from "@bull-board/api";
import { BullMQAdapter } from "@bull-board/api/bullMQAdapter";
import { ExpressAdapter } from "@bull-board/express";

const serverAdapter = new ExpressAdapter();
createBullBoard({
  queues: [new BullMQAdapter(queueService.queue)],
  serverAdapter: serverAdapter,
});

serverAdapter.setBasePath("/admin/queues");
```

Access at: `http://localhost:8000/admin/queues`

### Logs

All services log their activities:

- 🔗 Navigation logs
- ⏳ Rate limit delays
- ✅ Successful scrapes
- ❌ Errors and retries
- 🔄 Queue processing

## Troubleshooting

### Redis Connection Issues

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Check Redis connection
redis-cli
127.0.0.1:6379> INFO
```

### Browser/Puppeteer Issues

If Puppeteer fails to launch:

```bash
# Install Chromium dependencies (Linux)
sudo apt-get install -y \
  libnss3 \
  libatk-bridge2.0-0 \
  libdrm2 \
  libxkbcommon0 \
  libgbm1 \
  libasound2
```

### Queue Not Processing

1. Check Redis is running
2. Check logs for worker errors
3. Restart the application
4. Clean old jobs: `curl -X DELETE /api/scrape-queue-status`

## Performance

With the current configuration:

- **Rate**: ~15 items per hour (conservative)
- **Delay**: 2-5 minutes between requests
- **Concurrency**: 1 job at a time
- **Safety**: Maximum anti-bot protection

To scrape faster (at your own risk):

1. Reduce `MIN_DELAY_MS` in config
2. Increase `MAX_CONCURRENT_JOBS`
3. Increase `MAX_REQUESTS_PER_HOUR`

⚠️ **Warning**: Faster scraping increases detection risk!

## Future Enhancements

Potential improvements:

- [ ] Proxy rotation integration
- [ ] CAPTCHA handling
- [ ] Advanced browser fingerprinting
- [ ] Distributed scraping (multiple workers)
- [ ] Priority queue (urgent items first)
- [ ] Notification system for price changes
- [ ] API rate limit detection and backoff
- [ ] Health check endpoint

## Support

For issues or questions about the scraper architecture, check:

1. This documentation
2. Service-level comments in code
3. Configuration file (`config/scraper.config.ts`)
4. API helper utilities (`utils/api-helpers.ts`)

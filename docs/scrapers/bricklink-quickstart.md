# Bricklink Scraper Quick Start Guide

## Prerequisites

- Deno installed
- PostgreSQL database
- Redis server

## Quick Setup (5 minutes)

### 1. Install and Start Redis

**macOS**:

```bash
brew install redis
brew services start redis
```

**Docker** (recommended):

```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

Verify Redis is running:

```bash
redis-cli ping
# Should return: PONG
```

### 2. Set Environment Variables

Create or update `.env`:

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Database (should already be set)
DATABASE_URL=postgresql://user:password@localhost:5432/database
```

### 3. Run Database Migration

```bash
deno task db:migrate
```

This adds the new columns:

- `scrape_interval_days` (default: 30 days)
- `last_scraped_at`
- `next_scrape_at`

### 4. Start the Application

```bash
deno task start
```

You should see:

```
🚀 Initializing BullMQ queue service...
✅ Redis connection established
✅ Queue service initialized successfully
```

## Basic Usage

### 1. Scrape a Single Item

```bash
curl -X POST "http://localhost:8000/api/scrape-bricklink?url=https://www.bricklink.com/v2/catalog/catalogitem.page?S=75192"
```

Response:

```json
{
  "message": "Scraping job enqueued successfully",
  "job": {
    "id": "1",
    "itemId": "75192",
    "itemType": "S",
    "status": "queued"
  }
}
```

### 2. Check Job Status

```bash
curl "http://localhost:8000/api/scrape-queue-status?job_id=1"
```

### 3. Check Queue Status

```bash
curl "http://localhost:8000/api/scrape-queue-status"
```

### 4. Configure Scraping Interval

Update an item to scrape every 7 days instead of default 30:

```bash
curl -X PUT "http://localhost:8000/api/bricklink-items?item_id=75192" \
  -H "Content-Type: application/json" \
  -d '{
    "scrape_interval_days": 7,
    "watch_status": "active"
  }'
```

### 5. Preview Items Needing Scraping

```bash
curl "http://localhost:8000/api/scrape-scheduler"
```

### 6. Trigger Scheduled Scraping

```bash
curl -X POST "http://localhost:8000/api/scrape-scheduler"
```

## Key Features

✅ **Anti-Bot Protection**

- Browser automation (Puppeteer)
- 30+ rotating user agents
- Random viewports and headers
- Human behavior simulation
- Automation detection removal

✅ **Conservative Rate Limiting**

- 2-5 minute delays between requests
- Maximum 15 requests per hour
- Randomized timing patterns
- Per-domain tracking

✅ **Background Processing**

- BullMQ job queue
- Async processing
- Automatic retries (3 attempts)
- Exponential backoff

✅ **Flexible Scheduling**

- Configurable intervals per item
- Default: 30 days
- Automated scheduling
- Preview upcoming scrapes

✅ **Monitoring**

- Job status tracking
- Queue statistics
- Failed job inspection
- Circuit breaker protection

## Configuration

Edit `config/scraper.config.ts` to adjust:

```typescript
// Rate limiting (2-5 minutes per request)
MIN_DELAY_MS: 2 * 60 * 1000,
MAX_DELAY_MS: 5 * 60 * 1000,

// Hourly limit
MAX_REQUESTS_PER_HOUR: 15,

// Concurrency (process one at a time)
MAX_CONCURRENT_JOBS: 1,

// Default scraping interval
DEFAULT_INTERVAL_DAYS: 30,
```

## Automated Scheduling

### Option 1: Cron Job

```bash
# Add to crontab (crontab -e)
# Run every 6 hours
0 */6 * * * curl -X POST http://localhost:8000/api/scrape-scheduler
```

### Option 2: Deno Cron

Add to `main.ts`:

```typescript
Deno.cron("bricklink-scheduler", "0 */6 * * *", async () => {
  const scheduler = getScheduler();
  await scheduler.run();
});
```

## Common Issues

### "Queue service is not available"

**Cause**: Redis is not running or cannot be reached

**Solution**:

```bash
# Check Redis
redis-cli ping

# Start Redis
brew services start redis
# OR
docker start redis
```

### Jobs Not Processing

**Cause**: Worker not running or crashed

**Solution**:

1. Restart the application
2. Check logs for errors
3. Verify Redis connection

### "Circuit breaker is open"

**Cause**: Too many recent failures (5+ in a row)

**Solution**:

- Wait 10 minutes for automatic reset
- Check Bricklink website availability
- Review error logs for root cause

## Performance

With default settings:

- **~15 items per hour** (conservative)
- **2-5 minute delays** (random)
- **1 concurrent job** (safe)
- **Low detection risk** (maximum protection)

## Next Steps

1. ✅ Read full architecture docs: `docs/BRICKLINK_SCRAPER_ARCHITECTURE.md`
2. ✅ Configure scraping intervals for your items
3. ✅ Set up automated scheduling (cron)
4. ✅ Monitor the queue periodically
5. ✅ Review and adjust rate limits if needed

## API Endpoints Summary

| Endpoint                   | Method | Purpose                 |
| -------------------------- | ------ | ----------------------- |
| `/api/scrape-bricklink`    | POST   | Enqueue scraping job    |
| `/api/scrape-queue-status` | GET    | Check queue/job status  |
| `/api/scrape-scheduler`    | GET    | Preview scheduled items |
| `/api/scrape-scheduler`    | POST   | Trigger scheduler       |
| `/api/bricklink-items`     | GET    | List items              |
| `/api/bricklink-items`     | PUT    | Update item config      |

## Support

- 📖 Architecture: `docs/BRICKLINK_SCRAPER_ARCHITECTURE.md`
- ⚙️ Configuration: `config/scraper.config.ts`
- 🐛 Issues: Check logs and Redis connection

---

**Ready to scrape!** 🚀

The scraper will now:

1. Queue jobs asynchronously
2. Process with 2-5 minute delays
3. Use browser automation
4. Rotate user agents
5. Avoid detection
6. Track price history
7. Respect rate limits

Enjoy safe, reliable Bricklink scraping! 🎉

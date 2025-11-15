# BWS Quick Start Guide

## Development Setup

### 1. Start Local Services (PostgreSQL & Redis)

```bash
docker compose up -d
```

### 2. Run Database Migrations

```bash
deno task db:push
```

### 3. Start the Deno/Fresh App

```bash
deno task dev
```

The app will be available at: `http://localhost:8000`

## Tailscale Access

### Enable Tailscale Serve

```bash
tailscale serve --bg --https=8125 8000
```

Access from any device on your Tailnet:
- **HTTPS URL**: `https://yees-mac-mini.tail83c2f.ts.net:8125`

### Disable Tailscale Serve

```bash
tailscale serve --https=8125 off
```

## Production Deployment

### Build and Start Production Services

```bash
# Create .env.production file first
cp .env.production.example .env.production
# Edit .env.production with your values

# Start all services (Postgres, Redis, App, Caddy)
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### Configure Tailscale Serve for Production

```bash
# Proxy to Docker container's exposed port
tailscale serve --bg --https=8125 8001
```

## Common Commands

### Development

```bash
# Start dev server with watch mode
deno task dev

# Run linter
deno task lint

# Run tests
deno task test

# Format code
deno task fmt

# Check types
deno task check
```

### Database

```bash
# Push schema changes
deno task db:push

# Generate migrations
deno task db:generate

# Open Drizzle Studio
deno task db:studio

# Drop all tables and recreate (DANGEROUS!)
deno task db:drop
```

### Docker

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Rebuild and restart
docker compose up -d --build

# Production
docker compose -f docker-compose.prod.yml up -d --build
```

### Tailscale

```bash
# View all Tailscale Serve configurations
tailscale serve status

# Enable Tailscale Serve
tailscale serve --bg --https=8125 8000

# Disable Tailscale Serve
tailscale serve --https=8125 off

# Check Tailscale status
tailscale status
```

## Useful URLs

- **Local Dev**: http://localhost:8000
- **Tailscale (Dev)**: https://yees-mac-mini.tail83c2f.ts.net:8125
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **PgAdmin** (if using dev compose): http://localhost:5050

## Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bws

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# External APIs
REBRICKABLE_API_KEY=your_key_here
BRICKLINK_CONSUMER_KEY=your_key_here
BRICKLINK_CONSUMER_SECRET=your_secret_here
BRICKLINK_TOKEN_VALUE=your_token_here
BRICKLINK_TOKEN_SECRET=your_secret_here
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Database Connection Failed

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Restart PostgreSQL
docker compose restart postgres

# Check logs
docker compose logs postgres
```

### Redis Connection Failed

```bash
# Check if Redis is running
docker ps | grep redis

# Test Redis connection
docker exec -it bws-redis redis-cli ping

# Restart Redis
docker compose restart redis
```

### Tailscale Access Not Working

```bash
# Check Tailscale status
tailscale status

# Check Tailscale Serve configuration
tailscale serve status

# Reconfigure Tailscale Serve
tailscale serve --https=8125 off
tailscale serve --bg --https=8125 8000

# Test local access first
curl http://localhost:8000
```

## Next Steps

1. ✅ Set up development environment
2. ✅ Configure Tailscale access
3. 📖 Read [PRODUCTION_SETUP.md](./PRODUCTION_SETUP.md) for production deployment
4. 📖 Read [TAILSCALE_SETUP.md](./TAILSCALE_SETUP.md) for detailed Tailscale configuration
5. 🔧 Configure external API keys for Rebrickable and Bricklink

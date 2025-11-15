# Production Deployment Guide

Complete guide for deploying BWS (Bricklink Worth Scraper) to production with Docker, including Caddy reverse proxy for Tailscale access.

## Architecture Overview

```
                    Tailscale Network
                          ↓
                  Caddy (:8001)
                          ↓
              BWS App (:8000) ←→ Redis (:6379)
                          ↓
                   PostgreSQL (:5432)
```

## Services

| Service | Container Name | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------------|---------|
| Caddy | bws-caddy | 8001 | 8001 | Reverse proxy for Tailscale access |
| App | bws-app | 8000 | - | Deno/Fresh application |
| PostgreSQL | bws-postgres | 5432 | - | Database |
| Redis | bws-redis | 6379 | - | Queue service for BullMQ |

## Prerequisites

1. **Docker & Docker Compose** installed
2. **Environment variables** configured
3. **Network access** to Tailscale
4. **Sufficient resources**:
   - CPU: 4 cores recommended
   - RAM: 4GB minimum, 8GB recommended
   - Disk: 10GB+ for data

## Initial Setup

### 1. Configure Environment Variables

Create `.env.production` from the example:

```bash
cp .env.production.example .env.production
```

Edit `.env.production` and fill in all required values:

```bash
# REQUIRED - Generate strong passwords
POSTGRES_PASSWORD=<generate-strong-password>
REDIS_PASSWORD=<generate-strong-password>

# REQUIRED - API Keys
REBRICKABLE_API_KEY=<your-key>
BRICKLINK_CONSUMER_KEY=<your-key>
BRICKLINK_CONSUMER_SECRET=<your-secret>
BRICKLINK_TOKEN_VALUE=<your-token>
BRICKLINK_TOKEN_SECRET=<your-secret>
```

**Security Tips:**
- Use strong, unique passwords (20+ characters)
- Never commit `.env.production` to git
- Consider using a secrets manager in production

### 2. Initialize the Database

On first deployment, you'll need to run migrations:

```bash
# Start only PostgreSQL first
docker compose -f docker-compose.prod.yml up -d postgres

# Wait for PostgreSQL to be healthy
docker compose -f docker-compose.prod.yml ps

# Run migrations (adjust based on your migration setup)
deno task db:migrate
# or if using Drizzle:
deno task drizzle:push
```

### 3. Build and Deploy All Services

```bash
# Build and start all services
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Check service health
docker compose -f docker-compose.prod.yml ps
```

## Accessing the Application

### Via Tailscale

Once deployed, access your application through Tailscale:

- **By hostname**: `http://yees-mac-mini:8001`
- **By Tailscale IP**: `http://<tailscale-ip>:8001`
- **Local (on host)**: `http://localhost:8001`

### CORS Support

Caddy is configured with full CORS support, allowing web access from any origin with proper headers.

## Service Management

### Starting Services

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# Start specific service
docker compose -f docker-compose.prod.yml up -d app
```

### Stopping Services

```bash
# Stop all services
docker compose -f docker-compose.prod.yml down

# Stop and remove volumes (WARNING: deletes data)
docker compose -f docker-compose.prod.yml down -v
```

### Restarting Services

```bash
# Restart all services
docker compose -f docker-compose.prod.yml restart

# Restart specific service
docker compose -f docker-compose.prod.yml restart app
```

### Viewing Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f app
docker compose -f docker-compose.prod.yml logs -f caddy

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100
```

## Updates and Deployments

### Deploying Code Updates

```bash
# Pull latest code
git pull

# Rebuild and restart app container
docker compose -f docker-compose.prod.yml up -d --build app

# Or rebuild everything
docker compose -f docker-compose.prod.yml up -d --build
```

### Database Migrations

```bash
# Run migrations before deploying new app version
deno task db:migrate

# Then deploy the updated app
docker compose -f docker-compose.prod.yml up -d --build app
```

## Backup and Restore

### PostgreSQL Backup

```bash
# Create backup
docker exec bws-postgres pg_dump -U postgres bws > backup-$(date +%Y%m%d-%H%M%S).sql

# Or with compression
docker exec bws-postgres pg_dump -U postgres bws | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz
```

### PostgreSQL Restore

```bash
# From SQL file
docker exec -i bws-postgres psql -U postgres bws < backup.sql

# From compressed file
gunzip -c backup.sql.gz | docker exec -i bws-postgres psql -U postgres bws
```

### Redis Backup

Redis is configured with AOF (Append Only File) persistence, so data is automatically persisted in the `redis_data` volume.

```bash
# Manual backup
docker exec bws-redis redis-cli BGSAVE

# Copy RDB file
docker cp bws-redis:/data/dump.rdb ./redis-backup-$(date +%Y%m%d-%H%M%S).rdb
```

### Volume Backup

```bash
# Backup all volumes
docker run --rm -v bws_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-data-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

docker run --rm -v bws_redis_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/redis-data-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
```

## Monitoring

### Health Checks

All services have health checks configured:

```bash
# View health status
docker compose -f docker-compose.prod.yml ps

# Detailed inspect
docker inspect bws-app | grep -A 10 Health
```

### Resource Usage

```bash
# Real-time stats
docker stats

# Specific containers
docker stats bws-app bws-postgres bws-redis bws-caddy
```

### Caddy Access Logs

```bash
# View access logs
docker exec bws-caddy cat /var/log/caddy/access.log

# Follow access logs
docker exec bws-caddy tail -f /var/log/caddy/access.log
```

## Troubleshooting

### App Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs app

# Check environment variables
docker exec bws-app env

# Check file permissions
docker exec bws-app ls -la /app
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose -f docker-compose.prod.yml ps postgres

# Test connection
docker exec bws-app deno eval "console.log('Testing DB connection...')"

# Check network
docker network inspect bws_bws-network
```

### Redis Connection Issues

```bash
# Test Redis connection
docker exec bws-redis redis-cli ping

# Check if password is set correctly
docker exec bws-redis redis-cli AUTH your_password ping
```

### Caddy Issues

```bash
# Validate Caddyfile
docker exec bws-caddy caddy validate --config /etc/caddy/Caddyfile

# Reload Caddy configuration
docker exec bws-caddy caddy reload --config /etc/caddy/Caddyfile

# Check Caddy logs
docker compose -f docker-compose.prod.yml logs caddy
```

### Port Already in Use

```bash
# Find what's using port 8001
sudo lsof -i :8001

# Or with netstat
netstat -an | grep 8001
```

## Performance Tuning

### Resource Limits

Services have resource limits configured in docker-compose.prod.yml:

- **App**: 2 CPU cores, 2GB RAM
- **PostgreSQL**: 1 CPU core, 1GB RAM
- **Redis**: 0.5 CPU cores, 256MB RAM
- **Caddy**: 0.5 CPU cores, 256MB RAM

Adjust these based on your workload:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

### PostgreSQL Tuning

For better performance, create `postgresql.conf` and mount it:

```yaml
volumes:
  - ./config/postgresql.conf:/etc/postgresql/postgresql.conf
```

Example optimizations:
```ini
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
```

## Security Checklist

- [ ] Strong passwords for PostgreSQL and Redis
- [ ] `.env.production` not committed to git
- [ ] Services only expose necessary ports
- [ ] App runs as non-root user
- [ ] Regular backups scheduled
- [ ] Firewall configured (only port 8001 for Tailscale)
- [ ] Health checks configured
- [ ] Logs regularly reviewed

## Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Compose File | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
| Caddyfile | `Caddyfile` | `Caddyfile.prod` |
| Port Exposure | Direct ports | Only Caddy |
| Logging | Stdout | File + Stdout |
| Restart Policy | `unless-stopped` | `unless-stopped` |
| Resource Limits | None | Enforced |
| Health Checks | Basic | Comprehensive |

## Next Steps

1. **Set up automated backups** - Create cron jobs for regular backups
2. **Configure monitoring** - Set up Prometheus/Grafana or similar
3. **SSL/TLS** - If exposing publicly, configure HTTPS in Caddy
4. **Log rotation** - Configure log rotation for Caddy logs
5. **Alerts** - Set up alerts for service failures

## Quick Reference

```bash
# Start production
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop production
docker compose -f docker-compose.prod.yml down

# Rebuild and deploy
docker compose -f docker-compose.prod.yml up -d --build

# Backup database
docker exec bws-postgres pg_dump -U postgres bws | gzip > backup.sql.gz

# Check status
docker compose -f docker-compose.prod.yml ps
```

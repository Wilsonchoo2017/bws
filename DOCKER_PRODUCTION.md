# Production Docker Deployment Guide

This guide covers deploying the BWS (LEGO Price Tracker) application in production using Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose V2
- At least 4GB of available RAM
- At least 10GB of available disk space

## Quick Start

### 1. Prepare Environment Variables

Copy the production environment template:
```bash
cp .env.production.example .env.production
```

Edit `.env.production` and set secure values for:
- `POSTGRES_PASSWORD` - Strong password for PostgreSQL
- `REDIS_PASSWORD` - Strong password for Redis (optional but recommended)
- `REBRICKABLE_API_KEY` - Your Rebrickable API key for LEGO data

### 2. Build and Start Services

```bash
# Build the application image
docker-compose -f docker-compose.prod.yml build

# Start all services
docker-compose -f docker-compose.prod.yml up -d
```

### 3. Run Database Migrations

```bash
# Run migrations inside the app container
docker-compose -f docker-compose.prod.yml exec app deno task db:migrate
```

### 4. Verify Deployment

```bash
# Check all services are running
docker-compose -f docker-compose.prod.yml ps

# Check application logs
docker-compose -f docker-compose.prod.yml logs -f app

# Test the application
curl http://localhost:8000
```

## Architecture

The production stack consists of three services:

### 1. **app** (Deno Application)
- Built from Dockerfile
- Runs Fresh.js application
- Includes Chromium for web scraping
- Exposes port 8000
- Resource limits: 2GB RAM, 2 CPUs

### 2. **postgres** (Database)
- PostgreSQL 15 Alpine
- Persistent data volume
- Health checks enabled
- Resource limits: 1GB RAM, 1 CPU

### 3. **redis** (Job Queue)
- Redis 7 Alpine
- Persistent data with appendonly mode
- Health checks enabled
- Resource limits: 256MB RAM, 0.5 CPU

## Service Management

### Start Services
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Stop Services
```bash
docker-compose -f docker-compose.prod.yml down
```

### Restart a Service
```bash
docker-compose -f docker-compose.prod.yml restart app
```

### View Logs
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f app
```

### Execute Commands
```bash
# Access app shell
docker-compose -f docker-compose.prod.yml exec app sh

# Run migrations
docker-compose -f docker-compose.prod.yml exec app deno task db:migrate

# Access PostgreSQL
docker-compose -f docker-compose.prod.yml exec postgres psql -U postgres -d bws

# Access Redis CLI
docker-compose -f docker-compose.prod.yml exec redis redis-cli
```

## Maintenance

### Backup Database
```bash
# Create backup
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U postgres bws > backup_$(date +%Y%m%d_%H%M%S).sql

# Or using Docker volume backup
docker run --rm \
  --volumes-from bws-postgres \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /var/lib/postgresql/data
```

### Restore Database
```bash
# From SQL dump
cat backup_YYYYMMDD_HHMMSS.sql | \
  docker-compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres bws
```

### Backup Redis
```bash
# Trigger Redis save
docker-compose -f docker-compose.prod.yml exec redis redis-cli BGSAVE

# Copy RDB file
docker cp bws-redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb
```

### Update Application
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose -f docker-compose.prod.yml build app
docker-compose -f docker-compose.prod.yml up -d app

# Run any new migrations
docker-compose -f docker-compose.prod.yml exec app deno task db:migrate
```

### Clean Up Old Data
```bash
# Remove stopped containers
docker-compose -f docker-compose.prod.yml rm

# Clean unused images
docker image prune -a

# View volume usage
docker system df -v
```

## Monitoring

### Health Checks
All services have health checks configured:

```bash
# Check health status
docker-compose -f docker-compose.prod.yml ps

# View detailed health info
docker inspect bws-app | jq '.[0].State.Health'
```

### Resource Usage
```bash
# Real-time stats
docker stats bws-app bws-postgres bws-redis

# Check logs for errors
docker-compose -f docker-compose.prod.yml logs --tail=100 | grep -i error
```

### Queue Monitoring
```bash
# Check queue status via API
curl http://localhost:8000/api/scrape-queue-status | jq

# Monitor Redis queue keys
docker-compose -f docker-compose.prod.yml exec redis redis-cli KEYS "bull:*"
```

## Troubleshooting

### Application Won't Start

**Check logs:**
```bash
docker-compose -f docker-compose.prod.yml logs app
```

**Common issues:**
- Database not ready: Wait for PostgreSQL health check
- Redis not ready: Wait for Redis health check
- Permission errors: Check file ownership in container

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_isready -U postgres

# Check database exists
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U postgres -l
```

### Redis Connection Issues

```bash
# Test Redis connection
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# Check Redis info
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO
```

### Scraping Jobs Not Processing

```bash
# Check if worker is running (in app logs)
docker-compose -f docker-compose.prod.yml logs app | grep "Worker"

# Check queue status
curl http://localhost:8000/api/scrape-queue-status

# Check Redis for stuck jobs
docker-compose -f docker-compose.prod.yml exec redis redis-cli \
  LLEN "bull:bricklink-scraper:active"
```

### High Memory Usage

```bash
# Check container stats
docker stats --no-stream

# Adjust resource limits in docker-compose.prod.yml:
# deploy:
#   resources:
#     limits:
#       memory: 4G  # Increase if needed
```

## Security Best Practices

1. **Change Default Passwords**: Always set strong passwords in `.env.production`
2. **Use Redis Password**: Set `REDIS_PASSWORD` for production
3. **Firewall Rules**: Only expose port 8000 (or use reverse proxy)
4. **Regular Updates**: Keep base images updated
5. **Scan Images**: Use `docker scan` to check for vulnerabilities
6. **Secrets Management**: Consider using Docker secrets or external secret managers

## Performance Tuning

### Database Optimization
```bash
# Increase PostgreSQL shared buffers (in docker-compose.prod.yml):
command: postgres -c shared_buffers=256MB -c max_connections=100
```

### Redis Optimization
```bash
# Adjust maxmemory and eviction policy:
command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru --appendonly yes
```

### Application Scaling
```bash
# Increase resource limits in docker-compose.prod.yml
# Or run multiple app instances behind a load balancer
```

## Reverse Proxy Setup (Optional)

### Nginx Configuration Example
```nginx
upstream bws_app {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://bws_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Using Traefik (Alternative)
Add labels to app service in docker-compose.prod.yml:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.bws.rule=Host(`your-domain.com`)"
  - "traefik.http.services.bws.loadbalancer.server.port=8000"
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Deno Docker Guide](https://deno.land/manual/advanced/deploying_deno/docker)
- [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)
- [Redis Docker Hub](https://hub.docker.com/_/redis)

## Support

For issues specific to this application, check:
- Application logs: `docker-compose -f docker-compose.prod.yml logs app`
- Database migrations: Ensure all migrations are applied
- Queue status: Check `/api/scrape-queue-status` endpoint

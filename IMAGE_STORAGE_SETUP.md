# Image Storage Docker Mount Point Setup

## Overview

This document explains the image storage configuration for both development and production environments.

## Directory Structure

```
bws/
├── static/
│   └── images/
│       └── products/          # Product images stored here
│           ├── abc123.jpg
│           ├── def456.png
│           └── ...
```

## Configuration

### Environment Variables

**Development (.env)**
```bash
IMAGE_STORAGE_PATH=static/images/products
```

**Production (.env.production)**
```bash
IMAGE_STORAGE_PATH=/app/static/images/products
```

### Docker Mount Points

The `docker-compose.prod.yml` includes a volume mount that maps your local images directory to the container:

```yaml
volumes:
  - ./logs:/app/logs
  - ./static/images:/app/static/images  # Images persist on host
```

## How It Works

### Development Mode
- Images are stored directly in `./static/images/products/`
- No Docker involved, files are saved to your local filesystem
- Accessible at `/images/products/` URL path

### Production Mode (Docker)
- Images are mounted from host to container: `./static/images` → `/app/static/images`
- Inside the container, code uses `/app/static/images/products`
- Files persist on your host machine even if container is recreated
- Accessible at `/images/products/` URL path

## Benefits

1. **Data Persistence**: Images survive container restarts and rebuilds
2. **Easy Access**: You can browse/manage images directly on the host filesystem
3. **Backup**: Simple to backup - just copy `./static/images/` directory
4. **Sharing**: Multiple containers can share the same image directory if needed

## Current Status

- **227 product images** already exist in `./static/images/products/`
- Mount point configured in `docker-compose.prod.yml`
- Environment variables set in all `.env` files
- Image config updated to use `IMAGE_STORAGE_PATH` env var

## Usage

### Local Development
```bash
# Images automatically saved to ./static/images/products/
deno task start
```

### Production (Docker)
```bash
# Build and run with image persistence
docker-compose -f docker-compose.prod.yml up -d

# Your images in ./static/images/ will be accessible inside container
```

## Troubleshooting

### Images not persisting after container restart
- Check that the volume mount exists in docker-compose.prod.yml
- Verify permissions: `ls -la ./static/images/`

### Images not found in production
- Ensure `IMAGE_STORAGE_PATH` is set in .env.production
- Check container logs: `docker logs bws-app`
- Verify mount: `docker exec bws-app ls -la /app/static/images/products`

### Permission issues
```bash
# Fix permissions if needed
chmod -R 755 ./static/images/
```

## Future Enhancements

The image storage system is designed to support multiple backends:

- **local** (current): Files stored on filesystem
- **supabase**: Cloud storage with Supabase
- **r2**: Cloudflare R2 object storage

To switch storage backend, update `IMAGE_CONFIG.STORAGE.TYPE` in `config/image.config.ts`.

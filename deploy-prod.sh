#!/bin/bash

# Production Deployment Script for BWS
# This script helps deploy BWS to production with Docker

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  BWS Production Deployment Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo -e "${RED}ERROR: .env.production file not found!${NC}"
    echo -e "${YELLOW}Creating from template...${NC}"
    cp .env.production.example .env.production
    echo ""
    echo -e "${YELLOW}⚠️  Please edit .env.production and add your API keys and passwords:${NC}"
    echo "  - REBRICKABLE_API_KEY"
    echo "  - BRICKLINK_CONSUMER_KEY"
    echo "  - BRICKLINK_CONSUMER_SECRET"
    echo "  - BRICKLINK_TOKEN_VALUE"
    echo "  - BRICKLINK_TOKEN_SECRET"
    echo ""
    echo -e "${YELLOW}Secure passwords have been pre-generated for PostgreSQL and Redis.${NC}"
    echo ""
    read -p "Press Enter after you've updated .env.production..."
fi

# Load environment variables
set -a
source .env.production
set +a

echo -e "${GREEN}✓${NC} Environment variables loaded"

# Validate required environment variables
REQUIRED_VARS=("POSTGRES_PASSWORD" "DATABASE_URL" "REDIS_PASSWORD")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}ERROR: Missing required environment variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

echo -e "${GREEN}✓${NC} All required environment variables set"

# Check if API keys are configured
if [ -z "$REBRICKABLE_API_KEY" ] || [ -z "$BRICKLINK_CONSUMER_KEY" ]; then
    echo -e "${YELLOW}⚠️  Warning: API keys not configured${NC}"
    echo "  Some features may not work without:"
    echo "  - REBRICKABLE_API_KEY"
    echo "  - BRICKLINK_CONSUMER_KEY and related credentials"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Ask for deployment type
echo ""
echo "Select deployment option:"
echo "  1) Fresh deployment (pull images, rebuild, start)"
echo "  2) Update deployment (rebuild and restart)"
echo "  3) Quick restart (restart without rebuilding)"
read -p "Enter option (1-3): " DEPLOY_OPTION

case $DEPLOY_OPTION in
    1)
        echo ""
        echo -e "${GREEN}Starting fresh deployment...${NC}"

        # Pull latest images
        echo -e "${YELLOW}Pulling latest base images...${NC}"
        docker compose -f docker-compose.prod.yml pull postgres redis caddy

        # Build application
        echo -e "${YELLOW}Building application...${NC}"
        docker compose -f docker-compose.prod.yml build --no-cache app

        # Start services
        echo -e "${YELLOW}Starting services...${NC}"
        docker compose -f docker-compose.prod.yml up -d
        ;;
    2)
        echo ""
        echo -e "${GREEN}Updating deployment...${NC}"

        # Rebuild and restart
        echo -e "${YELLOW}Rebuilding application...${NC}"
        docker compose -f docker-compose.prod.yml up -d --build
        ;;
    3)
        echo ""
        echo -e "${GREEN}Quick restarting services...${NC}"
        docker compose -f docker-compose.prod.yml restart
        ;;
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

# Wait for services to be healthy
echo ""
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 5

# Check service status
echo ""
echo -e "${GREEN}Service Status:${NC}"
docker compose -f docker-compose.prod.yml ps

# Check health status
echo ""
POSTGRES_HEALTHY=$(docker inspect bws-postgres --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
REDIS_HEALTHY=$(docker inspect bws-redis --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
APP_HEALTHY=$(docker inspect bws-app --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")

echo -e "Health Status:"
echo -e "  PostgreSQL: ${POSTGRES_HEALTHY}"
echo -e "  Redis: ${REDIS_HEALTHY}"
echo -e "  App: ${APP_HEALTHY}"

if [ "$POSTGRES_HEALTHY" == "healthy" ] && [ "$REDIS_HEALTHY" == "healthy" ]; then
    echo ""
    echo -e "${GREEN}✓ Core services are healthy!${NC}"
else
    echo ""
    echo -e "${YELLOW}⚠️  Some services are not healthy yet. Run 'docker compose -f docker-compose.prod.yml ps' to check status.${NC}"
fi

# Show logs option
echo ""
read -p "View application logs? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f docker-compose.prod.yml logs -f app
fi

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Access URLs:"
echo "  - Local: http://localhost:8001 (via Caddy)"
echo "  - Direct to app: http://localhost:8000"
echo ""
echo "Configure Tailscale Serve:"
echo "  tailscale serve --bg --https=8125 8001"
echo ""
echo "Useful commands:"
echo "  - View logs: docker compose -f docker-compose.prod.yml logs -f"
echo "  - Stop services: docker compose -f docker-compose.prod.yml down"
echo "  - Check status: docker compose -f docker-compose.prod.yml ps"
echo ""

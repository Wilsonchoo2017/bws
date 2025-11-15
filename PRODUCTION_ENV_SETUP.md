# Production Environment Setup Guide

## Overview

Your production environment file `.env.production` has been created with secure passwords pre-generated. You need to add your API keys to complete the setup.

## Current Status

✅ **Completed:**
- `.env.production` file created
- Secure PostgreSQL password generated
- Secure Redis password generated
- Database URL configured for Docker

⚠️ **Required: Add API Keys**

## Step 1: Get Your API Keys

### Rebrickable API Key

1. Go to https://rebrickable.com/api/
2. Sign in or create an account
3. Navigate to your profile → API section
4. Copy your API key

### Bricklink API Credentials

1. Go to https://www.bricklink.com/v2/api/register_consumer.page
2. Sign in to your Bricklink account
3. Register a new application:
   - **App Name**: BWS Production
   - **App Type**: Web Application
   - **Description**: Bricklink Worth Scraper
4. You'll receive:
   - Consumer Key
   - Consumer Secret
   - Token Value
   - Token Secret

## Step 2: Edit `.env.production`

Open the `.env.production` file and fill in these values:

```bash
# Find these lines and add your keys:

REBRICKABLE_API_KEY=your_rebrickable_key_here

BRICKLINK_CONSUMER_KEY=your_consumer_key_here
BRICKLINK_CONSUMER_SECRET=your_consumer_secret_here
BRICKLINK_TOKEN_VALUE=your_token_value_here
BRICKLINK_TOKEN_SECRET=your_token_secret_here
```

### Using nano editor:
```bash
nano .env.production
```

### Using VS Code:
```bash
code .env.production
```

### Using vim:
```bash
vim .env.production
```

## Step 3: Verify Configuration

After adding your API keys, verify the file:

```bash
# Check that all required values are set
grep -E "REBRICKABLE_API_KEY|BRICKLINK_CONSUMER_KEY" .env.production
```

You should see your actual API keys (not empty values).

## Step 4: Deploy

Once configured, deploy using the automated script:

```bash
./deploy-prod.sh
```

Or manually:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## Security Checklist

- [ ] `.env.production` added to `.gitignore` ✅ (already done)
- [ ] API keys added to `.env.production`
- [ ] File permissions restricted: `chmod 600 .env.production`
- [ ] Never commit `.env.production` to git
- [ ] Keep backups of API credentials in secure location (password manager)

## Pre-generated Secure Passwords

Your `.env.production` file includes these pre-generated secure passwords:

- **PostgreSQL Password**: `u/j/p42giu+yYlVoCyop3srac1P6xYrKvePrlsHnx6s=`
- **Redis Password**: `BdrbcLP09Sd+XXdo5KB9WTbOTL/QiAMHDJ7GXNuKx60=`

**Important:** These are strong passwords (32-byte base64 encoded). You can keep them or regenerate new ones:

```bash
# Generate new PostgreSQL password
openssl rand -base64 32

# Generate new Redis password
openssl rand -base64 32
```

If you change the passwords, update both the `POSTGRES_PASSWORD` and `DATABASE_URL` variables to match.

## Environment Variables Reference

### Required for Production

| Variable | Description | Status |
|----------|-------------|--------|
| `POSTGRES_PASSWORD` | PostgreSQL database password | ✅ Generated |
| `DATABASE_URL` | Full PostgreSQL connection string | ✅ Configured |
| `REDIS_PASSWORD` | Redis password | ✅ Generated |
| `REBRICKABLE_API_KEY` | Rebrickable API access | ⚠️ Required |
| `BRICKLINK_CONSUMER_KEY` | Bricklink OAuth consumer key | ⚠️ Required |
| `BRICKLINK_CONSUMER_SECRET` | Bricklink OAuth consumer secret | ⚠️ Required |
| `BRICKLINK_TOKEN_VALUE` | Bricklink OAuth token | ⚠️ Required |
| `BRICKLINK_TOKEN_SECRET` | Bricklink OAuth token secret | ⚠️ Required |

### Optional (Pre-configured)

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `PORT` | Application port | 8000 |
| `NODE_ENV` | Node environment | production |
| `DENO_ENV` | Deno environment | production |
| `TZ` | Timezone | Asia/Kuala_Lumpur |
| `REDIS_HOST` | Redis hostname (Docker) | redis |
| `REDIS_PORT` | Redis port | 6379 |
| `REDIS_DB` | Redis database number | 0 |

## Quick Start After Configuration

1. **Add API keys** to `.env.production`
2. **Run deployment script:**
   ```bash
   ./deploy-prod.sh
   ```
3. **Configure Tailscale Serve:**
   ```bash
   tailscale serve --bg --https=8125 8001
   ```
4. **Access your app:**
   - Via Tailscale: https://yees-mac-mini.tail83c2f.ts.net:8125

## Troubleshooting

### "Missing required environment variables" error

Make sure you've filled in all the API keys in `.env.production`:
```bash
cat .env.production | grep -E "API_KEY|CONSUMER|TOKEN"
```

### Database connection failed

Check that the `DATABASE_URL` matches the `POSTGRES_PASSWORD`:
```bash
# The password should appear in both variables
grep POSTGRES_PASSWORD .env.production
grep DATABASE_URL .env.production
```

### Redis authentication failed

Verify Redis password is set:
```bash
grep REDIS_PASSWORD .env.production
```

## Next Steps

After successful deployment:

1. Check service health: `docker compose -f docker-compose.prod.yml ps`
2. View logs: `docker compose -f docker-compose.prod.yml logs -f app`
3. Test the application: `curl http://localhost:8000`
4. Configure monitoring and backups (see PRODUCTION_SETUP.md)

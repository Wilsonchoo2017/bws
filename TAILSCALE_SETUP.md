# Tailscale Access Setup for BWS

This setup allows you to access your BWS (Bricklink Worth Scraper) application
through Tailscale using **Tailscale Serve**.

## Architecture

```
Tailscale Serve (HTTPS)
         ↓
  Fresh/Deno App (port 8000)
```

## Quick Start (Recommended: Tailscale Serve)

### Option 1: Use Tailscale Serve (Simplest - Currently Active)

Tailscale Serve provides built-in HTTPS and handles all the proxying for you -
no Caddy needed!

1. **Start your Deno/Fresh app:**
   ```bash
   deno task dev
   # or
   deno task start
   ```
   The app runs on `localhost:8000`

2. **Configure Tailscale Serve:**
   ```bash
   tailscale serve --bg --https=8125 8000
   ```

3. **Access via Tailscale:**
   - **HTTPS URL**: `https://yees-mac-mini.tail83c2f.ts.net:8125`
   - Automatic HTTPS certificate handling
   - Only accessible within your Tailnet (private)

4. **To disable later:**
   ```bash
   tailscale serve --https=8125 off
   ```

### Option 2: Use Caddy Reverse Proxy (Alternative)

1. **Start all services including Caddy:**
   ```bash
   docker compose -f docker-compose.dev.yml up -d
   ```

2. **Start your Deno app locally** (must run on host, not in container):
   ```bash
   deno task dev
   ```

3. **Access via Tailscale:** Same as Option 1

## Configuration Details

### Caddyfile

The `Caddyfile` configures:

- **Port 8001**: External access port (Tailscale)
- **Reverse proxy**: Routes to `localhost:8000` (Fresh/Deno app)
- **CORS headers**: Full CORS support for web access
- **WebSocket support**: For Fresh hot module reload
- **Logging**: All requests logged to stdout

### CORS Configuration

The setup includes comprehensive CORS headers to prevent cross-origin errors:

- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS, PATCH`
- `Access-Control-Allow-Headers: Content-Type, Authorization, Accept, Origin, X-Requested-With`
- Proper handling of OPTIONS preflight requests

## Ports Reference

| Service                | Port/URL                                    | Access                  |
| ---------------------- | ------------------------------------------- | ----------------------- |
| Fresh/Deno App         | 8000                                        | Local only              |
| Tailscale Serve        | https://yees-mac-mini.tail83c2f.ts.net:8125 | Tailnet only (HTTPS)    |
| Caddy Proxy (optional) | 8001                                        | Tailscale access (HTTP) |
| PostgreSQL             | 5432                                        | Local only              |
| Redis                  | 6379                                        | Local only              |

## Testing

### Test Tailscale Serve

```bash
# Check Tailscale Serve status
tailscale serve status

# Test access
curl -I https://yees-mac-mini.tail83c2f.ts.net:8125/

# Test from another device on your Tailnet
# Open in browser: https://yees-mac-mini.tail83c2f.ts.net:8125/
```

### Test Caddy Configuration (if using Caddy)

```bash
caddy validate --config Caddyfile
```

### Test Local Access

```bash
# Direct to app
curl http://localhost:8000/

# Via Tailscale Serve (proxied)
curl https://yees-mac-mini.tail83c2f.ts.net:8125/
```

## Managing Services

### Stop Tailscale Serve

```bash
tailscale serve --https=8125 off
```

### View all Tailscale Serve configurations

```bash
tailscale serve status
```

### Stop Caddy (if running locally)

Press `Ctrl+C` in the terminal running Caddy

### Stop Docker services

```bash
docker compose -f docker-compose.dev.yml down
```

## Troubleshooting

### CORS Errors

- Ensure Caddy is running and properly configured
- Check that the `Caddyfile` includes CORS headers in all `handle` blocks
- Verify preflight OPTIONS requests are being handled

### Connection Refused

- Ensure your Deno app is running on port 8000
- Check that Caddy is running on port 8001
- Verify firewall settings allow port 8001

### WebSocket Issues (Hot Reload Not Working)

- Ensure the `@websockets` matcher is properly configured
- Check browser console for WebSocket connection errors
- Verify that CORS headers are applied to WebSocket upgrades

## Summary: Why Tailscale Serve?

Tailscale Serve is the recommended approach because:

1. **Simpler setup**: One command vs. running Caddy
2. **Built-in HTTPS**: Automatic certificate management
3. **Security**: Only accessible within your Tailnet
4. **No firewall issues**: Works through NAT/firewalls automatically
5. **Consistent**: Same approach used for Morass, Radarr, Sonarr

### Active Configuration

Currently configured:

- **BWS**: `https://yees-mac-mini.tail83c2f.ts.net:8125` →
  `http://localhost:8000`
- **Morass**: `https://yees-mac-mini.tail83c2f.ts.net` → `http://localhost:3010`
- **Radarr**: `https://yees-mac-mini.tail83c2f.ts.net:8123/radarr` →
  `http://localhost:7878/radarr`
- **Sonarr**: `https://yees-mac-mini.tail83c2f.ts.net:8124/sonarr` →
  `http://localhost:8989/sonarr`

# Use official Deno Alpine image for smaller size
FROM denoland/deno:alpine-2.1.4

# Install Chromium and dependencies for Puppeteer
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    nodejs \
    npm \
    curl

# Set Puppeteer environment variables to use system Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    DENO_DIR=/deno-dir \
    NODE_ENV=production \
    DENO_ENV=production

# Create app directory and deno-dir
WORKDIR /app

# Create logs directory
RUN mkdir -p /app/logs

# Copy dependency files first for better caching
COPY deno.json ./
COPY deno.lock* ./

# Cache dependencies
RUN deno install --node-modules-dir=auto || true

# Copy application code
COPY . .

# Cache main application and dependencies
RUN deno cache --lock=deno.lock --lock-write \
    --node-modules-dir=auto \
    main.ts || deno cache --node-modules-dir=auto main.ts

# Create non-root user for security
RUN addgroup -g 1001 -S deno && \
    adduser -S -D -H -u 1001 -G deno deno && \
    chown -R deno:deno /app /deno-dir

# Switch to non-root user
USER deno

# Expose application port
EXPOSE 8000

# Health check - simplified version that works without external file
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application with necessary permissions
CMD ["deno", "run", "--allow-all", "main.ts"]

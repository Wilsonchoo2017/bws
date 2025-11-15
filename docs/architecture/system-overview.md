# System Architecture Overview

## Introduction

BWS (Bricklink Warehouse System) is a comprehensive LEGO price tracking and
investment analysis platform. It scrapes data from multiple sources, stores it
in PostgreSQL, and provides intelligent analysis for LEGO investment
opportunities.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Frontend Layer"
        UI[Fresh.js Web UI]
        Islands[Interactive Islands]
    end

    subgraph "API Layer"
        API[REST API Routes]
        Handlers[Route Handlers]
    end

    subgraph "Service Layer"
        ScraperSvc[Scraper Services]
        AnalysisSvc[Analysis Service]
        QueueSvc[Queue Service]
        ImageSvc[Image Service]
    end

    subgraph "Data Access Layer"
        Repos[Repositories]
        ORM[Drizzle ORM]
    end

    subgraph "External Services"
        Redis[(Redis Queue)]
        Postgres[(PostgreSQL)]
        Storage[Local Storage]
    end

    subgraph "External Sources"
        Bricklink[Bricklink.com]
        Shopee[Shopee.sg]
        ToysRUs[ToysRUs.com.sg]
        BrickRanker[BrickRanker.com]
        WorldBricks[WorldBricks.com]
        Reddit[Reddit API]
    end

    UI --> API
    Islands --> API
    API --> Handlers
    Handlers --> ScraperSvc
    Handlers --> AnalysisSvc
    Handlers --> QueueSvc

    ScraperSvc --> Repos
    AnalysisSvc --> Repos
    QueueSvc --> Redis
    ImageSvc --> Storage

    Repos --> ORM
    ORM --> Postgres

    ScraperSvc -.->|Scrape| Bricklink
    ScraperSvc -.->|Scrape| Shopee
    ScraperSvc -.->|Scrape| ToysRUs
    ScraperSvc -.->|Scrape| BrickRanker
    ScraperSvc -.->|Scrape| WorldBricks
    AnalysisSvc -.->|Fetch| Reddit

    style UI fill:#e1f5ff
    style Islands fill:#e1f5ff
    style Redis fill:#ffebee
    style Postgres fill:#f3e5f5
    style Storage fill:#e8f5e9
```

## Core Components

### 1. Frontend Layer (Fresh.js)

**Technology**: Fresh 1.7.3 (Deno web framework) + Preact + TailwindCSS +
DaisyUI

**Routes** (`routes/`):

- `/` - Home page with product listings
- `/api/*` - RESTful API endpoints
- `/analysis-demo` - Analysis system demo

**Islands** (`islands/`): Interactive components with client-side JavaScript

- `ProductAnalysisCard` - Analysis results with strategy selector
- `PricingOverview` - Pricing comparison display

### 2. API Layer

**Location**: `routes/api/`

**Endpoints** (see [API Reference](../api/api-reference.md)):

- Scraping: `/api/scrape-bricklink`, `/api/parse-shopee`, `/api/parse-toysrus`
- Analysis: `/api/analysis/:productId`, `/api/analysis/batch`
- Queue: `/api/scrape-queue-status`, `/api/scrape-scheduler`
- CRUD: `/api/bricklink-items`

### 3. Service Layer

**Location**: `services/`

#### Scraper Services

- **BricklinkScraperService**: Scrapes Bricklink with anti-bot protection
- **ShopeeParserService**: Parses Shopee HTML for product data
- **ToysRUsScraperService**: Scrapes ToysRUs Singapore
- **BrickRankerScraperService**: Fetches retirement data
- **WorldBricksScraperService**: Extracts release years and parts count

#### Analysis Service

- **AnalysisService**: Orchestrates multi-dimensional analysis
- **RecommendationEngine**: Generates buy/hold/pass recommendations
- **Analyzers**: Pricing, Demand, Availability, Quality
- **Strategies**: Investment Focus, Quick Flip, Bargain Hunter

#### Supporting Services

- **QueueService**: BullMQ job queue for background processing
- **SchedulerService**: Automated interval-based scraping
- **RateLimiterService**: Conservative rate limiting (2-5 min delays)
- **HttpClientService**: Puppeteer-based browser automation
- **ImageDownloadService**: Download and store product images

### 4. Data Access Layer

**Location**: `db/`

**Components**:

- **Repositories**: Clean data access pattern (Repository pattern)
  - `BricklinkRepository`
  - `ShopeeRepository`
  - `ToysRUsRepository`
  - `WorldBricksRepository`
  - `BrickRankerRepository`
- **Drizzle ORM**: Type-safe database queries
- **Schema**: Database table definitions
- **Migrations**: Version-controlled schema changes

## Data Flow

### Scraping Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Queue
    participant Scraper
    participant RateLimiter
    participant HTTP
    participant Parser
    participant Repo
    participant DB

    User->>API: POST /api/scrape-bricklink?url=...
    API->>Queue: Enqueue scraping job
    Queue-->>User: Job ID + status

    Queue->>Scraper: Process job
    Scraper->>RateLimiter: Wait for rate limit
    RateLimiter-->>Scraper: OK to proceed
    Scraper->>HTTP: Fetch with browser
    HTTP-->>Scraper: HTML content
    Scraper->>Parser: Parse HTML
    Parser-->>Scraper: Structured data
    Scraper->>Repo: Save/update
    Repo->>DB: INSERT/UPDATE
    DB-->>Repo: Success
    Repo-->>Scraper: Saved
    Scraper->>Queue: Job complete
```

### Analysis Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant AnalysisService
    participant Repos
    participant DB
    participant Analyzers
    participant Strategy
    participant Engine

    User->>API: GET /api/analysis/prod-123?strategy=Investment
    API->>AnalysisService: analyzeProduct()
    AnalysisService->>Repos: Fetch product data
    Repos->>DB: Query all sources
    DB-->>Repos: Raw data
    Repos-->>AnalysisService: Product data

    AnalysisService->>Analyzers: Run analyzers in parallel
    Analyzers-->>AnalysisService: Dimension scores

    AnalysisService->>Strategy: Get weights
    Strategy-->>AnalysisService: Dimension weights

    AnalysisService->>Engine: Generate recommendation
    Engine-->>AnalysisService: Recommendation

    AnalysisService-->>API: Analysis result
    API-->>User: JSON response
```

## Database Schema

```mermaid
erDiagram
    bricklink_items ||--o{ shopee_items : "links to"
    shopee_items ||--o{ shopee_price_history : "has"
    bricklink_items ||--o{ toysrus_items : "links to"
    bricklink_items ||--o{ worldbricks_sets : "references"
    bricklink_items ||--o{ brickranker_sets : "references"

    bricklink_items {
        int id PK
        string item_id UK
        string item_type
        string title
        jsonb current_new
        jsonb current_used
        jsonb six_month_new
        jsonb six_month_used
        timestamp last_scraped_at
        timestamp next_scrape_at
        int scrape_interval_days
    }

    shopee_items {
        int id PK
        string product_id UK
        string name
        bigint price
        bigint units_sold
        bigint avg_star_rating
        jsonb rating_count
        string lego_set_number
        timestamp created_at
    }

    shopee_price_history {
        int id PK
        string product_id FK
        bigint price
        bigint units_sold_snapshot
        timestamp recorded_at
    }

    toysrus_items {
        int id PK
        string product_id UK
        string title
        bigint price
        string availability
        string lego_set_number
    }

    worldbricks_sets {
        int id PK
        string set_number UK
        int year_released
        int year_retired
        int parts_count
        string dimensions
    }

    brickranker_sets {
        int id PK
        string set_number UK
        date eol_date
        boolean is_retired
        timestamp scraped_at
    }
```

## Technology Stack

### Backend

- **Runtime**: Deno 1.37+
- **Framework**: Fresh.js 1.7.3
- **Database**: PostgreSQL 15
- **ORM**: Drizzle ORM
- **Queue**: BullMQ + Redis 7
- **Scraping**: Puppeteer (Chromium automation)

### Frontend

- **UI Framework**: Preact
- **Styling**: TailwindCSS + DaisyUI
- **Islands**: Fresh.js Islands for interactivity

### DevOps

- **Containerization**: Docker + Docker Compose
- **Database Migrations**: Drizzle Kit
- **Version Control**: Git

## Key Design Principles

### SOLID Principles

The codebase follows SOLID principles throughout (see
[.claude/CLAUDE.md](.claude/CLAUDE.md)):

- **Single Responsibility**: Each service/class has one clear purpose
- **Open/Closed**: Services open for extension, closed for modification
- **Liskov Substitution**: Services can be mocked/substituted for testing
- **Interface Segregation**: Focused interfaces, no bloated objects
- **Dependency Inversion**: Services depend on abstractions

### Other Principles

- **DRY**: Code reuse through shared utilities (`utils/`)
- **Pure Functions**: Parsers are pure functions (easy to test)
- **Immutability**: Data structures are immutable where possible
- **Repository Pattern**: Clean separation of data access
- **Service Layer**: Business logic in dedicated services

## Anti-Bot Protection

The scraping system implements multiple anti-bot measures:

```mermaid
graph LR
    A[HTTP Request] --> B[User Agent Rotation]
    B --> C[Viewport Randomization]
    C --> D[Header Rotation]
    D --> E[Rate Limiting]
    E --> F[Human Behavior Sim]
    F --> G[Cookie Management]
    G --> H[Request]

    style E fill:#ffebee
    style F fill:#fff3e0
```

**Features**:

- 30+ rotating user agents
- Random viewport sizes
- Request header randomization
- 2-5 minute delays between requests
- Mouse movement and scrolling simulation
- Automation detection removal
- Circuit breaker pattern

See [Scraper Architecture](./scraper-architecture.md) for details.

## Scaling Considerations

### Current Configuration

- Single worker processing queue
- Max 15 requests/hour per domain
- 2-5 minute delays
- Conservative and safe

### Future Scaling Options

1. **Horizontal Scaling**: Multiple worker instances
2. **Distributed Queue**: Redis Cluster for queue
3. **Database**: Read replicas, connection pooling
4. **Caching**: Redis cache layer for analysis results
5. **CDN**: Static assets and images

## Monitoring & Observability

### Current Monitoring

- Queue status endpoint: `/api/scrape-queue-status`
- Job monitoring through BullMQ
- Database query logging
- Error tracking with circuit breaker

### Future Enhancements

- [ ] Health check endpoints
- [ ] Prometheus metrics export
- [ ] Grafana dashboards
- [ ] Error alerting (Sentry)
- [ ] Performance monitoring (APM)

## Security

### Current Measures

- Environment variable configuration
- No hardcoded credentials
- SQL injection prevention (parameterized queries via Drizzle)
- Rate limiting
- Input validation

### Production Recommendations

- Use strong passwords in production
- Enable Redis authentication
- Use TLS/SSL for database connections
- Implement authentication/authorization
- Regular security updates
- Docker secret management

## Related Documentation

- [Scraper Architecture](./scraper-architecture.md) - Detailed scraper design
- [API Reference](../api/api-reference.md) - Complete API documentation
- [Database Setup](../getting-started/database-setup.md) - Database
  configuration
- [Deployment Guide](../getting-started/deployment.md) - Production deployment
- [Analysis System](../../services/analysis/README.md) - Analysis service
  details

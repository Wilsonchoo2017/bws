# BWS Backend Monorepo

A monorepo containing backend services for the BWS project.

## Structure

```
bws/
├── packages/
│   ├── backend/        # Python FastAPI backend with PostgreSQL
│   ├── scraper/        # Python web scraping tools
│   └── api/            # Deno/Fresh frontend service
├── docker-compose.yml  # PostgreSQL database
└── package.json        # Root workspace configuration
```

## Tech Stack

### Backend (`packages/backend/`)
- **FastAPI** - Modern async Python web framework
- **SQLAlchemy 2.0** - Type-safe async ORM
- **PostgreSQL** - Primary database
- **Pydantic v2** - Runtime type validation
- **Alembic** - Database migrations
- **mypy** - Static type checking

## Setup

### 1. Start PostgreSQL Database
```bash
npm run db:up
```

This starts PostgreSQL on port 5432 and pgAdmin on port 5050:
- **PostgreSQL**: `postgresql://postgres:postgres@localhost:5432/bws`
- **pgAdmin**: http://localhost:5050 (admin@bws.local / admin)

### 2. Set up Python Backend

```bash
# Create virtual environment
cd packages/backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
npm run backend:install

# Copy environment file
cp .env.example .env

# Run migrations to create database tables
npm run backend:migrate
```

### 3. Scraper Package (Optional)
```bash
cd packages/scraper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Backend API (Development)
```bash
npm run backend:dev
```
API available at: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

### Database Management
```bash
npm run db:up          # Start PostgreSQL
npm run db:down        # Stop PostgreSQL
npm run db:logs        # View database logs
```

### Backend Development
```bash
npm run backend:lint        # Run linter (ruff)
npm run backend:format      # Format code
npm run backend:type-check  # Run mypy type checking
npm run backend:migration   # Create new migration
npm run backend:migrate     # Apply migrations
```

### Run Scraper
```bash
npm run scraper
```

### Run Frontend (dev mode)
```bash
npm run api:dev
```

## Packages

- **@bws/backend** - FastAPI backend with PostgreSQL, fully typed with SQLAlchemy 2.0 + Pydantic
- **@bws/scraper** - Web scraping tools for Shopee and Bricklink
- **@bws/api** - Frontend service built with Deno Fresh

## Type Safety

The backend is fully typed throughout:
- **Database Layer**: SQLAlchemy 2.0 with `Mapped[]` type annotations
- **API Layer**: Pydantic schemas for request/response validation
- **Static Checking**: mypy configured with strict mode
- **Runtime Validation**: Pydantic validates all inputs at runtime

Example flow:
```
HTTP Request → Pydantic Schema → SQLAlchemy Model → PostgreSQL
                  ↓ validated        ↓ type-safe      ↓ strongly typed
```

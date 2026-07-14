# Scrpr

**Open-source Clay/Claygent alternative.** AI-powered data enrichment with web research, waterfall enrichment, and personalized email outreach.

> **Status:** Working prototype. The web app, AI research agent, enrichment waterfall, and live table updates are functional. The Patchright stealth-browser scraping layer is included in the codebase but **disabled by default** for event-loop stability — the HTTP and API layers handle scraping. Some tests are integration tests that need live API keys/network; see [Development](#development).

## Features

- **AI Research Agent** — Autonomous web browsing agent that finds any data point (like Claygent)
- **Layered Scraping Engine** — httpx (fast) → API fallback, with an optional Patchright stealth-browser layer (included; disabled by default for stability)
- **Waterfall Enrichment** — Chain multiple data sources; first hit wins
- **Spreadsheet UI** — AG Grid with real-time cell updates via WebSocket
- **AI Email Composer** — Template → AI personalization → Preview all → Send with rate limiting
- **Free by Default** — Local LLM (Ollama) + free API tiers (Hunter.io, Apollo.io, Gemini)

## Quick Start

```bash
# Clone and configure
git clone https://github.com/YOUR_USERNAME/scrpr.git
cd scrpr
cp .env.example .env

# Option A: Docker (recommended)
docker-compose up

# Option B: Local development
# Terminal 1 — Backend
cd backend
pip install -e ".[dev]"
DATABASE_URL="sqlite+aiosqlite:///./scrpr.db" python -m uvicorn app.main:app --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Architecture

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐
│ Next.js  │◄───►│   FastAPI    │◄───►│ PostgreSQL  │
│ AG Grid  │ WS  │  REST + WS   │     │  (or SQLite)│
└──────────┘     └──────┬───────┘     └─────────────┘
                        │
                 ┌──────▼───────┐
                 │    Redis     │
                 │   (optional) │
                 └──┬────────┬──┘
                    │        │
             ┌──────▼──┐ ┌──▼───────┐
             │ Scrape  │ │   LLM    │
             │ Workers │ │  Router  │
             └─────────┘ └──────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, AG Grid, shadcn/ui, Tailwind CSS, TanStack Query |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| AI | LiteLLM (Ollama / Gemini / Claude / OpenAI), agentic research loop |
| Scraping | Patchright (stealth), httpx, ScraperAPI, Browserless |
| Database | PostgreSQL 16 (prod) / SQLite (dev) |
| Queue | Redis + arq (optional for single-user) |

## Data Sources

| Source | What it finds | Free Tier |
|--------|--------------|-----------|
| AI Web Agent | Any unstructured data | $0 (local LLM) |
| Hunter.io | Email by domain | 25/month |
| Apollo.io | Contact data + titles | 60/month |
| Email Pattern | Generated email patterns | Unlimited |
| Google Search | Web research starting point | Unlimited |

## API Endpoints

### Tables
- `POST /api/tables` — Create table
- `GET /api/tables` — List tables
- `GET /api/tables/{id}` — Get table
- `PATCH /api/tables/{id}` — Update table
- `DELETE /api/tables/{id}` — Delete table

### Columns, Rows, Cells
- `POST /api/tables/{id}/columns` — Add column
- `POST /api/tables/{id}/rows` — Add row (with optional cell values)
- `PATCH /api/cells/{id}` — Update cell

### Enrichment
- `POST /api/tables/{id}/columns/{id}/enrich` — Trigger enrichment
- `GET /api/tables/{id}/columns/{id}/enrich/status` — Get progress
- `GET /api/quota` — View free tier usage

### AI Agent
- `POST /api/agent/run` — Run AI research agent
- `POST /api/agent/enrich/{cell_id}` — Enrich a specific cell

### Email
- `POST /api/emails/compose` — Generate personalized drafts
- `GET /api/emails/drafts/{table_id}` — List drafts
- `PATCH /api/emails/drafts/{id}` — Edit draft
- `POST /api/emails/send` — Send selected drafts

### CSV
- `POST /api/tables/{id}/import-csv` — Import CSV
- `GET /api/tables/{id}/export-csv` — Export CSV

### WebSocket
- `WS /ws/{table_id}` — Real-time cell updates

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Required
DATABASE_URL=sqlite+aiosqlite:///./scrpr.db

# LLM (at least one)
OLLAMA_BASE_URL=http://localhost:11434
GEMINI_API_KEY=your_key_here

# Optional enrichment sources
HUNTER_API_KEY=
APOLLO_API_KEY=

# Optional email (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your_app_password
```

## Development

```bash
# Run the backend unit suite (offline, no keys needed)
cd backend && pytest tests/ -v

# Run the integration tests too (need live network + API keys)
cd backend && pytest tests/ -v -m integration

# Run frontend build check
cd frontend && npm run build
```

Integration tests (live DNS/SMTP probes and source APIs) are deselected by default so the
unit suite runs fast and offline; opt in with `-m integration`.

## License

MIT

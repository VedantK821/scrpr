# Scrpr

Open-source Clay/Claygent alternative. AI-powered data enrichment with web research, waterfall enrichment, and personalized email outreach.

## Quick Start

```bash
cp .env.example .env
docker-compose up
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/docs

## Tech Stack

- **Backend:** Python 3.12+ / FastAPI / SQLAlchemy / arq
- **Frontend:** Next.js 15 / AG Grid / shadcn/ui / Tailwind
- **AI:** Ollama (local) + Gemini / Claude (API)
- **Scraping:** Patchright (stealth) + httpx + free API fallbacks
- **Database:** PostgreSQL 16 + Redis 7

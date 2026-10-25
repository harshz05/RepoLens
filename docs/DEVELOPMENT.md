# RepoLens Development Guide

Welcome to the **RepoLens** developer guide. This document outlines setup instructions, environment configurations, and testing workflows for Milestone 1.

---

## 1. Prerequisites

- **Python:** 3.12+
- **Node.js:** 20+ / 22+
- **Git:** Installed and available on system PATH.
- **Docker & Docker Compose (Optional for local containerized dev):** PostgreSQL 16 + pgvector & Redis 7.

---

## 2. Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configuration variables:
   - `DATABASE_URL`: `sqlite+aiosqlite:///./repolens_dev.db` (Local SQLite dev engine) or `postgresql+asyncpg://postgres:postgres@localhost:5432/repolens` (Production PostgreSQL 16).
   - `NEXT_PUBLIC_API_URL`: `http://localhost:8000`

---

## 3. Running Backend Services

Install Python dependencies and launch the FastAPI gateway server:

```bash
pip install -r requirements.txt
python -m uvicorn apps.api.app.main:app --reload --port 8000
```

---

## 4. Running Frontend Web App

Install Node dependencies and launch Next.js 15 App Router:

```bash
cd apps/web
npm install
npm run dev
```

Open your browser at `http://localhost:3000`.

---

## 5. Running Automated Tests

Run backend unit and integration test suites:

```bash
pytest tests/
```

Some tests build a throwaway local git repository, so `git` must be installed and `user.name` / `user.email` configured (CI sets these automatically).

## 6. Configuration Notes

- `CORS_ORIGINS` — comma-separated list of allowed frontend origins (default `http://localhost:3000,http://127.0.0.1:3000`). Add your deployed frontend URL here.
- **Upgrading an existing dev database:** the audit pipeline needs stored source (`file_contents`) and symbol metadata. SQLite dev DBs gain the new column automatically, but repositories ingested earlier must be **re-ingested** before they can be audited. Deleting `repolens_dev.db` is the simplest reset.
- **Windows:** git may check files out with CRLF line endings; the tests normalise newlines, and stored source keeps the original bytes.

## 7. Continuous Integration

`.github/workflows/ci.yml` runs `pytest` on every push to `main` and on pull requests.

---
*End of Development Guide*

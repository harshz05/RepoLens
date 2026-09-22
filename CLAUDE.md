# RepoLens Project Documentation

## Project Overview

RepoLens is an **enterprise-grade codebase intelligence platform** designed to ingest, analyze, visualize, and reason over large-scale software repositories. It provides developers, security auditors, and software architects with:

- Deep static analysis and AST-driven dependency graphs
- Change blast-radius calculation
- Security SAST scanning
- Grounded AI assistance using Gemini
- Real-time progress tracking via SSE
- Interactive code intelligence with Monaco Editor integration

## Technology Stack

### Frontend
- **Next.js 15** (App Router)
- **TypeScript**
- **Tailwind CSS** + **shadcn/ui**
- **React Flow** for interactive dependency graphs
- **Monaco Editor** for code inspection
- **Zustand** for client state management
- **Vitest** for testing

### Backend
- **FastAPI** (Python 3.12) as control plane
- **PostgreSQL 16** with **pgvector** extension for vector embeddings
- **Redis 7** for task queue (ARQ/Celery) and Pub/Sub
- **Tree-sitter** for multi-language AST parsing
- **SQLAlchemy 2.0** ORM
- **Gemini API** integration for RAG and AI reasoning
- **Docker** for local development environment

### Architecture
- **Monolithic Monorepo** with clean separation:
  - `apps/web/` - Next.js frontend
  - `apps/api/` - FastAPI backend
  - `services/worker/` - Background processing workers
  - `packages/code-intel/` - Core code intelligence library
  - `packages/security-scanner/` - SAST rules engine
  - `packages/db/` - Database access layer
  - `packages/shared-types/` - TypeScript types

### File Structure
```
RepoLens/
├── apps/
│   ├── web/                    # Next.js 15 App Router
│   │   ├── app/                # Routes & Layouts
│   │   ├── components/         # UI Components
│   │   ├── hooks/              # Custom React Hooks
│   │   ├── lib/                # API Clients & Utilities
│   │   ├── store/              # Client State
│   │   └── public/             # Static Assets
│   └── api/                    # FastAPI Control Plane
│       ├── app/
│       │   ├── api/v1/         # REST Endpoints
│       │   ├── core/           # App Configuration & Auth
│       │   ├── middleware/     # CORS, Security Headers
│       │   └── main.py         # Server Entrypoint
│       ├── pyproject.toml
│       └── Dockerfile
├── services/
│   └── worker/                 # Async Ingestion Workers
│       ├── tasks/              # Celery/ARQ Task Handlers
│       │   ├── ingest_repo.py      # Git cloning
│       │   ├── parse_ast.py        # Tree-sitter extraction
│       │   ├── build_graph.py      # Dependency graph
│       │   ├── generate_embed.py   # Vector embedding
│       │   └── run_analysis.py     # Security & Quality
│       ├── pyproject.toml
│       └── Dockerfile
├── packages/
│   ├── code-intel/             # Core Python Code Intelligence
│   │   ├── parsers/            # Tree-sitter AST queries
│   │   ├── models/             # Normalized Symbol schemas
│   │   ├── extractors/         # Framework-specific extractors
│   │   └── graph/              # Graph traversal algorithms
│   │
│   ├── security-scanner/       # SAST & Quality Engine
│   │   ├── rules/              # Detection patterns
│   │   ├── quality/            # Complexity calculators
│   │   └── analyzer.py
│   │
│   ├── db/                     # Database Access Layer
│   │   ├── models/             # SQLAlchemy 2.0 ORM
│   │   ├── migrations/         # Alembic scripts
│   │   └── session.py          # Async Engine & Session
│   │
│   └── shared-types/           # TypeScript Types
│       ├── index.ts            # OpenAPI contracts
│       └── package.json
├── infrastructure/
│   ├── docker/                 # Local dev stack
│   │   ├── docker-compose.yml
│   │   └── postgres-init/
│   └── helm/                   # Kubernetes manifests
├── docs/                       # Documentation
└── tests/                      # Integration & E2E Tests
```

## Database Schema

PostgreSQL 16 with pgvector extension serves as unified storage:

- **Tables**: `users`, `repositories`, `repository_versions`, `analysis_runs`, `files`, `symbols`, `dependencies`, `code_chunks`, `security_findings`, `quality_findings`, `chat_sessions`, `chat_messages`, `citations`
- **Vector Operations**: pgvector supports cosine similarity for code embeddings (768-dim/1536-dim)
- **Graph Queries**: Native PostgreSQL recursive CTEs for dependency traversal up to tens of thousands of nodes

## Ingestion Pipeline

**7-Stage Processing Pipeline**:
1. **QUEUED** → GitHub URL submitted
2. **CLONING** → Shallow git clone
3. **PARSING** → Tree-sitter AST extraction with error recovery
4. **GRAPH_BUILDING** → Save call/dependency edges
5. **SAST_SCANNING** → Security & quality rules
6. **EMBEDDING** → Code chunk generation & vector storage
7. **FINALIZING** → Architecture summary via Gemini

**Failure Handling**:
- Idempotent job processing via commit hash
- File-level error recovery (continuing on parse failures)
- Gemini API rate limit retry with exponential backoff

## Key Features

### Code Intelligence
- Multi-language support (Python, TypeScript, Go, Rust, C++)
- Framework detection (FastAPI, React, Next.js, SQLAlchemy)
- Normalized symbol schema with full qualified names
- AST-aware code chunking

### Dependency Graph
- Directed multi-graph visualization (React Flow)
- Blast radius calculation with weighted scoring
- Cycle detection via Tarjan's SCC algorithm
- Interactive node inspection with Monaco Editor

### Security & Quality
- Deterministic SAST for absolute precision
- AI-assisted reasoning for complex logic vulnerabilities
- Cyclomatic complexity and coupling metrics
- Quality findings with actionable recommendations

### AI/Grounded RAG
- **AST-Grounded Hybrid Retrieval Engine**
- Context-aware query planning with Gemini
- Strict citation verification
- Click-to-highlight code citations

### Developer Experience
- **Real-time Progress** via SSE (not WebSockets)
- **Interactive IDE** experience
- **Dark UI** with glassmorphism aesthetics
- **Change Impact Analysis** with ripple effect visualization
- **Chat Assistant** with grounded citations

## Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- Git
- Docker & Docker Compose (optional)

### Setup Commands
```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Start services
npm run dev  # Starts both backend and frontend

# Or start separately
cd apps/web && npm run dev
python -m uvicorn apps.api.app.main:app --reload --port 8000

# Test suite
pytest tests/

# Docker development stack
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

### Configuration
- `.env` file with database, Redis, and Gemini API keys
- SQLite fallback for local development
- PostgreSQL + pgvector for production
- Redis for task queue and Pub/Sub

## Testing Strategy

### Multi-Tier Testing
1. **Unit Tests**: AST extraction, complexity calculation, vector chunking
2. **Graph Algorithm Tests**: Cycle detection, blast radius scoring
3. **AI Grounding Tests**: Citation precision/recall with golden benchmarks
4. **E2E Tests**: Playwright browser automation

### Quality Gates
- >85% code coverage for core packages
- All schema changes via Alembic migrations
- TypeScript strict mode compliance
- OpenAPI spec generation

## Engineering Principles

### Architectural Decisions
1. **PostgreSQL First**: Eliminates multi-database sync bugs, lower infrastructure costs
2. **Tree-sitter Native**: High performance, error recovery, unified interface
3. **SSE over WebSockets**: Simpler connection management, native HTTP/2/3 support
4. **Modular Monolith**: Clean package separation, easier evolution

### Security Defenses
- URL validation (GitHub/GitLab only)
- Path traversal protection in sandboxed containers
- No code execution (static analysis only)
- XML input fencing for prompt injection prevention
- Output sanitization and guardrails

## Project Status

### Current Setup Tasks (Completed)
- [x] Monorepo structure initialized with `apps/`, `services/`, `packages/`
- [x] FastAPI backend skeleton with database initialization
- [x] Next.js frontend with basic layout
- [x] PostgreSQL + pgvector database schema
- [x] Redis configuration for task queue
- [x] GitHub API integration for repository ingestion
- [x] Basic AST parsing with Tree-sitter (Python, TypeScript)
- [x] Symbol extraction and normalization
- [x] Interactive dependency graph visualization
- [x] Real-time progress tracking via SSE
- [x] Basic AI assistant with citation system
- [x] Security scanner with deterministic rules
- [x] Quality metrics engine (complexity, coupling)
- [x] Docker development environment setup
- [x] Complete CLAUDE.md project documentation
- [x] Local development environment verification (Python 3.12, Node.js 22)

### Immediate Next Steps
- [ ] Implement comprehensive Git ingestion worker (shallow clone, sandboxing)
- [ ] Complete dependency graph algorithms (Tarjan's SCC, blast radius scoring)
- [ ] Enhance Gemini integration with advanced RAG capabilities
- [ ] Add premium UI polish (dark theme, glassmorphism, component library)
- [ ] Implement change impact analysis engine
- [ ] Complete end-to-end test suite with Playwright
- [ ] Add error handling and retry mechanisms
- [ ] Implement rate limiting and monitoring
- [ ] Set up CI/CD pipeline

## Technical Verification

### Environment Setup
- **Python**: 3.12.4 ✅
- **Node.js**: v22.18.0 ✅
- **Git**: 2.51.0.windows.1 ✅
- **Docker**: Not available (requires installation for containerized development)

### Dependencies Installed
- **Backend**: FastAPI, uvicorn, SQLAlchemy, tree-sitter parsers, aiosqlite, asyncpg ✅
- **Frontend**: Next.js 15, React 19, Tailwind CSS, shadcn/ui, React Flow ✅
- **Development Tools**: concurrently for local dev server orchestration ✅

### Core Systems Status
- **Database**: SQLAlchemy models with UUID PKs, vector type support for pgvector ✅
- **API Layer**: FastAPI with OpenAPI schema, SSE event streaming ✅
- **Message Broker**: EventBroker implementation for real-time progress ✅
- **Code Intelligence**: Tree-sitter integration, symbol normalization ✅

### Security & Quality
- **SAST Rules**: Deterministic security scanning framework ✅
- **Quality Metrics**: Cyclomatic complexity, coupling, coupling analysis ✅
- **Sandboxing**: Path traversal protection, execution prevention ✅
- **Input Validation**: URL sanitization, XSS prevention ✅

### Architecture Components
- **Ingestion Pipeline**: 7-stage async processing (CLONING → PARSING → GRAPH → SAST → EMBEDDING → FINALIZING → COMPLETED) ✅
- **RAG System**: AST-Grounded Hybrid Retrieval Engine with citation verification ✅
- **Graph Database**: PostgreSQL recursive CTEs for dependency traversal ✅
- **Vector Store**: pgvector with cosine similarity indexing ✅

### Files Created/Modified
- **NEW**: CLAUDE.md (comprehensive project documentation)
- **EXISTS**: docs/ARCHITECTURE.md, docs/DEVELOPMENT.md
- **VERIFIED**: apps/api/app/main.py, apps/api/app/api/v1/repositories.py, apps/api/app/schemas.py
- **VERIFIED**: packages/db/models.py, packages/db/session.py
- **VERIFIED**: services/worker/ingestion_worker.py, services/worker/audit_worker.py
- **VERIFIED**: apps/web/package.json, apps/web/tsconfig.json, apps/web/tailwind.config.js
- **VERIFIED**: .env.example, .env configuration

## Development Workflow

### Commit Message Format
```
<type>: <summary>

<optional detailed description>

Co-authored-by: Claude Code <noreply@anthropic.com>
```

### Branch Management
- Feature branches from `main`
- PR reviews with CLAUDE.md impact assessment
- Automated testing in CI/CD pipeline

## Directory-Specific Notes

### apps/api/
- FastAPI control plane
- Handles authentication, API endpoints, SSE streams
- Database initialization and migrations

### apps/web/
- Next.js 15 with App Router
- Interactive code editor and graph visualization
- Real-time updates via Server-Sent Events

### services/worker/
- Background processing workers
- Repository cloning, AST parsing, graph building
- Security scanning and vector generation

### packages/code-intel/
- Core code intelligence library
- Tree-sitter parser abstraction
- Symbol normalization and dependency extraction

### packages/security-scanner/
- Deterministic SAST rule engine
- Security vulnerability detection
- Quality metric calculation

## Common Issues & Solutions

### Database Connection Issues
```bash
# For local development with SQLite
export DATABASE_URL=sqlite+aiosqlite:///./repolens_dev.db

# For production with PostgreSQL
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/repolens
```

### Performance Optimization
- Use pgvector HNSW indexes for vector searches
- Implement Redis caching for frequent queries
- Consider connection pooling for high-concurrency scenarios
- Use PostgreSQL's query planner hints for complex graph traversals

### Troubleshooting
- Check `docker logs <service>` for container issues
- Verify environment variables in `.env` file
- Use `pytest -v` for detailed test output
- Monitor Redis and PostgreSQL health with their respective tools

---

*Last updated: Current development iteration*
*Version: 1.0.0*
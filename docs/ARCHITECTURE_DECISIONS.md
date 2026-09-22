# RepoLens — Architecture Decision Records (ADR)

This document serves as the permanent engineering decision log for **RepoLens**. It records the architectural context, evaluated tradeoffs, alternatives considered, consequences, and interview-ready rationales for all foundational technical choices across development milestones.

---

## Table of Contents

### Milestone 1: Core Foundation & Ingestion Vertical Slice
- [ADR-001: Monorepo Architecture](#adr-001-monorepo-architecture)
- [ADR-002: Unified Database (PostgreSQL 16 + pgvector)](#adr-002-unified-database-postgresql-16--pgvector)
- [ADR-003: SQLite Fallback for Zero-Dependency Local Development](#adr-003-sqlite-fallback-for-zero-dependency-local-development)
- [ADR-004: Asynchronous Processing & Background Queue Architecture](#adr-004-asynchronous-processing--background-queue-architecture)
- [ADR-005: Server-Sent Events (SSE) for Real-Time Pipeline Streaming](#adr-005-server-sent-events-sse-for-real-time-pipeline-streaming)
- [ADR-006: Static-Only Repository Analysis & Execution Sandboxing](#adr-006-static-only-repository-analysis--execution-sandboxing)
- [ADR-007: Temporary Python AST & Regex Symbol Extraction (Technical Debt)](#adr-007-temporary-python-ast--regex-symbol-extraction-technical-debt)
- [ADR-008: Schema Pre-allocation for Future Milestone Entities](#adr-008-schema-pre-allocation-for-future-milestone-entities)
- [ADR-009: Real Public Git Ingestion vs. Mocked Fixtures](#adr-009-real-public-git-ingestion-vs-mocked-fixtures)
- [ADR-010: Next.js 15 Dark Command Center Architecture](#adr-010-nextjs-15-dark-command-center-architecture)

### Milestone 2: Code Intelligence & Dependency Graph Engine
- [ADR-011: Tree-sitter C Bindings for Unified Multi-Language AST Extraction](#adr-011-tree-sitter-c-bindings-for-unified-multi-language-ast-extraction)
- [ADR-012: Modular Parser Abstraction (`BaseLanguageParser` & `ParserRegistry`)](#adr-012-modular-parser-abstraction-baselanguageparser--parserregistry)
- [ADR-013: Two-Pass Call-Graph & Dependency Resolution Strategy](#adr-013-two-pass-call-graph--dependency-resolution-strategy)
- [ADR-014: Handling Static Ambiguity & Dynamic References](#adr-014-handling-static-ambiguity--dynamic-references)
- [ADR-015: Scoped Graph REST API Boundary Design](#adr-015-scoped-graph-rest-api-boundary-design)
- [ADR-016: Client-Side React Flow (`@xyflow/react`) Dependency Graph Visualization](#adr-016-client-side-react-flow-xyflowreact-dependency-graph-visualization)

### Milestone 3: Vector Embeddings & Grounded Gemini RAG Chat
- [ADR-017: Embedding Model Provider Architecture & Gemini Embedding 2 Standardized Retrieval Formatting](#adr-017-embedding-model-provider-architecture--gemini-embedding-2-standardized-retrieval-formatting)
- [ADR-018: AST-Aware Semantic Code Chunking Strategy](#adr-018-ast-aware-semantic-code-chunking-strategy)
- [ADR-019: Multi-Signal Hybrid Retrieval with Reciprocal Rank Fusion (RRF)](#adr-019-multi-signal-hybrid-retrieval-with-reciprocal-rank-fusion-rrf)
- [ADR-020: 1-Hop AST & Dependency Graph Context Expansion for RAG](#adr-020-1-hop-ast--dependency-graph-context-expansion-for-rag)
- [ADR-021: Anti-Hallucination XML/CDATA Context Fencing & Post-Generation Citation Verification](#adr-021-anti-hallucination-xmlcdata-context-fencing--post-generation-citation-verification)
- [ADR-022: Next.js 15 Conversational RAG & Code Search Obsidian Cockpit](#adr-022-nextjs-15-conversational-rag--code-search-obsidian-cockpit)

### Appendix
- [Milestone 2 Technical Debt / Known Limitations](#milestone-2-technical-debt--known-limitations)
- [Milestone 3 Technical Debt / Known Limitations](#milestone-3-technical-debt--known-limitations)

---

## Milestone 1 Decisions

### ADR-001: Monorepo Architecture

1. **Decision:** Structure RepoLens as a single domain-driven monorepo containing `apps/web` (Next.js), `apps/api` (FastAPI), `services/worker` (Python Ingestion), and `packages/*` (shared code-intel, db, schemas).
2. **Context / Problem:** Codebase intelligence platforms require tight synchronization between AST data models, database ORM entities, API serialization contracts, and frontend visualization components. Multi-repo setups cause schema drift, versioning overhead, and slow local development.
3. **Chosen Approach:** Monorepo with directory-isolated apps and packages managed via root orchestration scripts.
4. **Why This Approach Was Chosen:** Allows atomic changes across DB models, API endpoints, background workers, and UI interfaces in a single commit, eliminating distributed contract synchronization issues.
5. **Alternatives Considered:** 
   - Multi-repo setup (separate repos for UI, API, worker, and core library).
   - Microservices with gRPC definitions across repos.
6. **Why The Alternatives Were Rejected:** Multi-repo introduces high release coordination costs and friction when rapidly evolving the code intelligence AST schema.
7. **Trade-offs:** Shared root dependencies must be managed carefully across Python and Node ecosystems.
8. **Consequences:** Developers can run full end-to-end dev pipelines locally with a single command (`npm run dev`).
9. **When We Would Reconsider The Decision:** If independent teams with separate release cadences and deployment pipelines take ownership of isolated platform services.
10. **Interview-Ready Explanation:** *"We adopted a modular monorepo because code intelligence engines require atomic consistency between AST parser outputs, database models, and graph UI contracts. It avoids schema drift while preserving clean package boundaries."*

---

### ADR-002: Unified Database (PostgreSQL 16 + pgvector)

1. **Decision:** Use PostgreSQL 16 with the `pgvector` extension as the single unified persistence engine for relational metadata, AST symbol tables, dependency graph edges, and vector embeddings.
2. **Context / Problem:** Ingesting and querying codebases requires storing relational repository metadata, hierarchical AST symbols, directed graph edges for blast-radius calculation, and high-dimensional vector embeddings for AI RAG reasoning.
3. **Chosen Approach:** PostgreSQL 16 + `pgvector` with recursive Common Table Expressions (CTEs) for graph traversal and HNSW/IVFFlat indexes for semantic vector search.
4. **Why This Approach Was Chosen:** Eliminates the operational and distributed transaction overhead of managing three separate databases (e.g. Postgres + Neo4j + Pinecone/Qdrant), maintaining strict ACID transactional consistency within a single database boundary.
5. **Alternatives Considered:** Polyglot persistence (PostgreSQL for metadata, Neo4j for code dependency graph, Pinecone for vector search).
6. **Why The Alternatives Were Rejected:** Polyglot setups suffer from dual-write consistency failures (e.g. repo deleted in Postgres but orphaned in Neo4j/Pinecone), complex distributed backups, and significantly higher infrastructure costs.
7. **Trade-offs:** Deep recursive graph traversals beyond 5-6 hops require careful SQL CTE indexing compared to native graph query languages (like Cypher).
8. **Consequences:** Backups, rollbacks, and schema migrations are unified under a single Alembic/PostgreSQL management workflow.
9. **When We Would Reconsider The Decision:** If repository call-graphs exceed 100 million nodes requiring global distributed sub-millisecond graph queries across thousands of repositories simultaneously.
10. **Interview-Ready Explanation:** *"We consolidated on PostgreSQL 16 with pgvector rather than a polyglot setup of Postgres, Neo4j, and Pinecone. This eliminates distributed transaction inconsistencies between code symbols and vector embeddings while drastically lowering operational complexity."*

---

### ADR-003: SQLite Fallback for Zero-Dependency Local Development

1. **Decision:** Provide transparent fallback to SQLite via `aiosqlite` when `DATABASE_URL` specifies SQLite or when running local development without Docker containers.
2. **Context / Problem:** Requiring all contributors and test runners to have active PostgreSQL and Redis daemons installed increases onboarding friction and complicates lightweight CI test runs.
3. **Chosen Approach:** Abstract DB engine initialization in `packages/db/session.py` using SQLAlchemy 2.0 async engine, dynamically configuring connection pooling and concurrency flags based on SQLite vs. PostgreSQL dial-in.
4. **Why This Approach Was Chosen:** Enables immediate zero-configuration onboarding (`pip install -r requirements.txt && pytest tests/`) while remaining 100% ORM-compatible with production PostgreSQL.
5. **Alternatives Considered:** Hard dependency on Docker Compose for all development workflows.
6. **Why The Alternatives Were Rejected:** Dockerized setups fail in lightweight environments, CI sandboxes, or local dev machines without virtualization enabled.
7. **Trade-offs:** SQLite lacks native `pgvector` cosine similarity and concurrency locking for heavy parallel worker write bursts.
8. **Consequences:** Unit tests run in milliseconds using local in-memory/file SQLite databases; production deployments switch to PostgreSQL via a single `.env` variable.
9. **When We Would Reconsider The Decision:** When advanced PostgreSQL-specific features (e.g. `pgvector` HNSW indexes or specialized JSONB operators) cannot be polyfilled or bypassed during testing.
10. **Interview-Ready Explanation:** *"We designed our SQLAlchemy 2.0 layer to support SQLite with aiosqlite for zero-friction local development and testing, while targeting PostgreSQL 16 with pgvector for production workloads."*

---

### ADR-004: Asynchronous Processing & Background Queue Architecture

1. **Decision:** Decouple repository cloning, AST parsing, and graph construction from the synchronous HTTP request/response cycle into background worker execution.
2. **Context / Problem:** Git cloning, file scanning, and multi-file AST parsing take seconds to minutes depending on repository size. Holding HTTP connections open causes gateway timeouts, worker thread starvation, and poor user experience.
3. **Chosen Approach:** FastAPI control plane receives ingestion requests, initiates an `AnalysisRun` record, and dispatches processing to an asynchronous worker task pipeline (in-process `BackgroundTasks` for dev; Redis/Celery/ARQ for prod).
4. **Why This Approach Was Chosen:** Protects API availability, guarantees non-blocking request handling, and provides reliable tracking of long-running ingestion jobs.
5. **Alternatives Considered:** Synchronous HTTP request processing where `POST /ingest` blocks until parsing finishes.
6. **Why The Alternatives Were Rejected:** Synchronous ingestion fails HTTP gateway timeout limits (30-60s) on repositories over a few hundred files.
7. **Trade-offs:** Requires client-side polling or streaming transport to observe task completion.
8. **Consequences:** The system gracefully handles multiple concurrent repository ingestion jobs without degrading API response latency.
9. **When We Would Reconsider The Decision:** If all repository analysis was strictly sub-10ms (which is physically impossible for remote Git clones).
10. **Interview-Ready Explanation:** *"We decoupled the ingestion pipeline from the API gateway using background task workers. This ensures our FastAPI endpoints respond sub-50ms with a job ID while CPU-intensive AST extraction runs asynchronously."*

---

### ADR-005: Server-Sent Events (SSE) for Real-Time Pipeline Streaming

1. **Decision:** Use Server-Sent Events (SSE) over HTTP/2 (`GET /api/v1/repositories/events/{id}`) to stream real-time pipeline status updates, progress percentages, and log messages to the frontend.
2. **Context / Problem:** Users need instant visual feedback as repositories transition through ingestion stages (Cloning → Filtering → Parsing → Graph Building → Finalizing). Short polling wastes server resources, while full WebSockets add unnecessary duplex connection state.
3. **Chosen Approach:** Lightweight Server-Sent Events backed by an in-memory/Redis pub-sub event broker.
4. **Why This Approach Was Chosen:** SSE provides native browser reconnection, standard HTTP semantics, automatic compression, and works seamlessly behind standard API gateways without WebSocket handshake management.
5. **Alternatives Considered:** Short HTTP polling (`setInterval`), Long polling, WebSockets.
6. **Why The Alternatives Were Rejected:** Polling hammers the database with redundant queries; WebSockets introduce bidirectional connection state management when data flow is purely unidirectional from server to client.
7. **Trade-offs:** SSE is unidirectional (server to client); interactive bidirectional commands (if needed in future chat) require separate HTTP POST requests.
8. **Consequences:** The frontend renders a smooth, real-time progress console with zero database polling pressure.
9. **When We Would Reconsider The Decision:** If RepoLens adds collaborative multi-user live code editing requiring low-latency client-to-client bidirectional streams.
10. **Interview-Ready Explanation:** *"We chose Server-Sent Events over WebSockets for ingestion progress because our data flow is strictly unidirectional. SSE offers native browser reconnects, simpler gateway routing, and lower resource overhead."*

---

### ADR-006: Static-Only Repository Analysis & Execution Sandboxing

1. **Decision:** Repository code is strictly treated as untrusted text and parsed via static AST analyzers; untrusted repository code is **NEVER executed**, imported, or evaluated during ingestion.
2. **Context / Problem:** Analyzing arbitrary public Git repositories poses severe remote code execution (RCE) risks if `setup.py`, `package.json` scripts, dynamic `importlib`, or `eval()` are triggered.
3. **Chosen Approach:** Static-only parsing inside isolated temporary directory sandboxes, followed by immediate cleanup on job termination. Filtering excludes executables, binaries, and build artifacts.
4. **Why This Approach Was Chosen:** Guarantees absolute isolation against malicious code execution during ingestion.
5. **Alternatives Considered:** Running repository code in Docker containers or dynamic runtime profilers (e.g. running test runners or dynamic tracer hooks).
6. **Why The Alternatives Were Rejected:** Dynamic execution creates massive security attack surfaces, slow runtime container cold starts, and fails if external environment dependencies are absent.
7. **Trade-offs:** Cannot resolve runtime-injected dynamic monkey patches or reflection without AST heuristics.
8. **Consequences:** RepoLens safely ingests any public repository with zero risk of malware execution or sandbox breakouts.
9. **When We Would Reconsider The Decision:** Never for untrusted public repositories.
10. **Interview-Ready Explanation:** *"Security is fundamental: RepoLens performs strictly static AST analysis and never executes repository code. This eliminates Remote Code Execution vectors while analyzing untrusted public codebases."*

---

### ADR-007: Temporary Python AST & Regex Symbol Extraction (Technical Debt)

1. **Decision:** *(Temporary Milestone 1 Debt)* Used Python's standard library `ast` module and regex patterns for TypeScript in Milestone 1 to validate the ingestion and persistence vertical slice.
2. **Context / Problem:** Milestone 1 focused on proving the end-to-end flow from Git clone to database persistence to UI before investing in multi-language Tree-sitter C grammar bindings.
3. **Chosen Approach:** Standard library `ast` visitor for Python; regex heuristics for TS/JS.
4. **Why This Approach Was Chosen:** Accelerated Milestone 1 vertical slice delivery with zero C compiler or wheel installation dependencies.
5. **Alternatives Considered:** Implementing full Tree-sitter in Milestone 1.
6. **Why The Alternatives Were Rejected:** Would have delayed validating the core monorepo, API, DB, and UI foundations.
7. **Trade-offs:** Regex TS/JS parsing is brittle and cannot resolve block scopes or nested AST nodes; Python `ast` cannot parse TypeScript or other languages.
8. **Consequences:** Marked explicitly as technical debt scheduled for complete replacement in Milestone 2.
9. **When We Would Reconsider The Decision:** Replaced immediately in Milestone 2 by Tree-sitter.
10. **Interview-Ready Explanation:** *"In Milestone 1, we intentionally accepted technical debt by using Python AST and regex extractors to quickly validate the end-to-end ingestion and persistence slice before replacing it with Tree-sitter in Milestone 2."*

---

### ADR-008: Schema Pre-allocation for Future Milestone Entities

1. **Decision:** Define ORM entities for `Dependency` and `CodeChunk` in Milestone 1 database migrations ahead of their full functional implementation in Milestones 2 and 3.
2. **Context / Problem:** Iterative schema modifications in early development can cause migration churn and break relational foreign key structures if dependent tables are introduced one by one.
3. **Chosen Approach:** Pre-architect relational foreign keys (`files -> symbols -> dependencies -> code_chunks`) in `packages/db/models.py`.
4. **Why This Approach Was Chosen:** Establishes stable table boundaries and eliminates breaking relational refactors across milestones.
5. **Alternatives Considered:** Add tables only in the specific milestone where their population code is written.
6. **Why The Alternatives Were Rejected:** Leads to continuous schema revisions and retrofitting of foreign key constraints.
7. **Trade-offs:** Unpopulated tables exist in the database during Milestone 1.
8. **Consequences:** Milestone 2 immediately populates the `dependencies` table without requiring structural database redesign.
9. **When We Would Reconsider The Decision:** If a future milestone fundamentally changes the core relational architecture.
10. **Interview-Ready Explanation:** *"We designed our database schema upfront to include symbols, dependencies, and code chunks. This prevented migration churn and ensured Milestone 2 could immediately populate graph edges without altering database contracts."*

---

### ADR-009: Real Public Git Ingestion vs. Mocked Fixtures

1. **Decision:** Build and verify against real shallow Git clones (`git clone --depth 1`) from public GitHub/GitLab repositories rather than synthetic mock JSON datasets.
2. **Context / Problem:** Mock datasets hide real-world edge cases like mixed line endings, symlinks, huge binaries, syntax errors, and obscure directory structures.
3. **Chosen Approach:** Real Git sandbox cloning with file safety scanners and SHA256 integrity hashing.
4. **Why This Approach Was Chosen:** Ensures the platform is hardened against authentic real-world repositories from day one.
5. **Alternatives Considered:** Mock API fixtures returning static JSON symbol trees.
6. **Why The Alternatives Were Rejected:** Creates a false sense of completion while failing on the first real repository ingested.
7. **Trade-offs:** Integration tests requiring network access to Git remotes need controlled sandbox fixtures for offline testing.
8. **Consequences:** Verified ingestion against real repositories like `pallets/flask` (41 files, 3,522 LOC, 116 symbols) with zero synthetic data.
9. **When We Would Reconsider The Decision:** Offline test fixtures are used for isolated unit testing, but the production engine remains 100% real Git ingestion.
10. **Interview-Ready Explanation:** *"We built against real Git repositories rather than mock data. This forced us to immediately solve real-world problems like shallow cloning, binary exclusion, and multi-file encoding."*

---

### ADR-010: Next.js 15 Dark Command Center Architecture

1. **Decision:** Build the frontend with Next.js 15 App Router, React 19, Tailwind CSS, and custom Obsidian dark-mode styling inspired by modern developer IDEs.
2. **Context / Problem:** Code intelligence platforms display dense information (symbol trees, metrics, graph topologies, code snippets). Cluttered or generic consumer UI templates fail developer usability standards.
3. **Chosen Approach:** High-density, dark Obsidian command center (`#0B0E14`), monospace typography (Fira Code), glassmorphism cards, and dedicated split-pane inspectors.
4. **Why This Approach Was Chosen:** Delivers a serious, commercial developer-tool aesthetic with strong visual hierarchy and sub-second client-side responsiveness.
5. **Alternatives Considered:** Generic Bootstrap/Material dashboards; pure client-side SPA (Vite).
6. **Why The Alternatives Were Rejected:** Generic dashboards lack developer tool aesthetics; Next.js 15 App Router provides superior layout nesting and clean API route proxying.
7. **Trade-offs:** Requires custom CSS token curation rather than off-the-shelf component libraries.
8. **Consequences:** The UI feels like a production developer cockpit ready for advanced graph and editor integrations.
9. **When We Would Reconsider The Decision:** If mobile-first consumer interfaces become a primary requirement.
10. **Interview-Ready Explanation:** *"We designed a high-density, dark Obsidian command center using Next.js 15 and Tailwind. It gives software engineers a focused IDE-like environment tailored for navigating complex codebases."*

---

## Milestone 2 Decisions

### ADR-011: Tree-sitter C Bindings for Unified Multi-Language AST Extraction

1. **Decision:** Use official Tree-sitter bindings (`tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`) for all AST extraction, completely replacing temporary Python AST and regex extractors.
2. **Context / Problem:** Codebase intelligence across Python, TypeScript, and JavaScript requires robust parsing that tolerates syntax errors, handles modern grammar constructs (e.g. decorators, JSX, generics, type annotations), and provides uniform query primitives.
3. **Chosen Approach:** Tree-sitter C-based parsers with language-specific query expressions and concrete syntax tree traversal.
4. **Why This Approach Was Chosen:** Tree-sitter provides high-speed C parsing, incremental error recovery for incomplete code, consistent node traversal APIs, and support for 40+ programming languages without writing custom compiler frontends.
5. **Alternatives Considered:** Native language compilers (Python `ast`, TypeScript Compiler API via Node sub-process, Babel).
6. **Why The Alternatives Were Rejected:** Invoking Node/Babel subprocesses from Python workers creates severe IPC latency and memory bloat; Python `ast` cannot parse TypeScript.
7. **Trade-offs:** Tree-sitter produces concrete syntax trees (CST) rather than abstract syntax trees (AST), requiring explicit helper navigation over grammar-specific token nodes.
8. **Consequences:** Python, JavaScript, and TypeScript are parsed in a single unified Python worker process with microsecond performance.
9. **When We Would Reconsider The Decision:** Only if a specialized language lacks Tree-sitter grammar support.
10. **Interview-Ready Explanation:** *"We chose Tree-sitter because it delivers high-performance C execution and error-tolerant parsing across Python, TypeScript, and JavaScript within a single unified abstraction."*

---

### ADR-012: Modular Parser Abstraction (`BaseLanguageParser` & `ParserRegistry`)

1. **Decision:** Create a clean parser interface (`BaseLanguageParser`) and dynamic registry (`ParserRegistry`) separating language parsing from file filtering, graph resolution, API handling, and persistence.
2. **Context / Problem:** Tightly coupling parser logic to worker or API code makes adding new programming languages (e.g. Go, Rust, Java) invasive and error-prone.
3. **Chosen Approach:** Abstract base class `BaseLanguageParser` defining standard contracts:
   - `parse(code_bytes: bytes, file_path: str) -> ExtractedFileContext`
   - `extract_symbols(...) -> List[ExtractedSymbol]`
   - `extract_calls(...) -> List[RawCallReference]`
   - `extract_imports(...) -> List[RawImportReference]`
   Managed by a singleton `ParserRegistry` mapping file extensions to parser instances.
4. **Why This Approach Was Chosen:** Adding a new language requires only implementing one isolated class and registering its extensions without touching the ingestion pipeline or database layer.
5. **Alternatives Considered:** Monolithic parser script with large `if/elif language == ...` branching.
6. **Why The Alternatives Were Rejected:** Monolithic parsers violate open/closed principles, make unit testing difficult, and degrade maintainability.
7. **Trade-offs:** Slight abstraction overhead with intermediary dataclasses.
8. **Consequences:** New languages can be added with zero changes to the worker lifecycle or DB persistence logic.
9. **When We Would Reconsider The Decision:** Never — clean abstraction is a non-negotiable architectural requirement.
10. **Interview-Ready Explanation:** *"We implemented a BaseLanguageParser abstraction with a ParserRegistry. This decouples language grammar queries from the ingestion pipeline, allowing new languages to be added in isolation."*

---

### ADR-013: Two-Pass Call-Graph & Dependency Resolution Strategy

1. **Decision:** Implement a two-pass dependency resolution architecture: Pass 1 extracts file-local symbols, raw calls, and imports across all files; Pass 2 builds a repository symbol index and resolves cross-file caller-to-callee dependencies.
2. **Context / Problem:** In multi-file projects, function `A` in `services/auth.py` calls function `B` in `utils/crypto.py`. When parsing `services/auth.py`, `utils/crypto.py` may not have been parsed yet. Single-pass parsing cannot resolve inter-file target symbol IDs.
3. **Chosen Approach:** 
   - **Pass 1 (Parallel File Parsing):** Extract symbols, call sites, and import statements into in-memory `ExtractedFileContext` objects and persist symbols to generate primary keys.
   - **Pass 2 (Repository-Wide Graph Resolution):** Construct an in-memory symbol table (`FQN -> SymbolID`, `file_path -> imported_modules`) and match raw call references to exact callee symbol records, persisting resolved `Dependency` edges.
4. **Why This Approach Was Chosen:** Resolves cross-file symbol dependencies accurately regardless of file processing order while allowing Pass 1 to execute in parallel across CPU cores.
5. **Alternatives Considered:** On-demand single-pass database lookups per call site.
6. **Why The Alternatives Were Rejected:** Querying the database for every single call expression during parsing creates $O(N \times M)$ query storms, crippling ingestion performance.
7. **Trade-offs:** Requires accumulating repository symbol indexes in worker memory during Pass 2.
8. **Consequences:** Fast, batch-inserted dependency graph edges with guaranteed referential integrity.
9. **When We Would Reconsider The Decision:** If repository size exceeds 500,000 files where symbol index cannot fit in worker RAM (in which case a disk-backed KV index is needed).
10. **Interview-Ready Explanation:** *"We resolved cross-file call dependencies using a two-pass strategy. Pass 1 extracts symbols and import references in parallel; Pass 2 links callers to callees using an in-memory symbol index, avoiding database query storms."*

---

### ADR-014: Handling Static Ambiguity & Dynamic References

1. **Decision:** When static analysis cannot deterministically resolve a target symbol (e.g. dynamic reflection, polymorphic overrides with identical signatures, third-party unanalyzed library calls), record dependencies with scoped resolution or omit them rather than fabricating false edges.
2. **Context / Problem:** Static analysis of dynamic languages (Python, JS) cannot know runtime types with 100% certainty (e.g. `obj.save()` where `obj` runtime type depends on user input). Inventing false edges pollutes blast-radius calculations and misleads security audits.
3. **Chosen Approach:**
   - Resolve exact matches when imports and module paths align deterministically.
   - For intra-class method calls (`self.method()`, `this.method()`), resolve to the containing class hierarchy.
   - For unresolvable dynamic calls (e.g. `getattr()`, external library calls like `os.path.join`), track external module references or omit internal symbol edge generation.
4. **Why This Approach Was Chosen:** Upholds data integrity and engineering trust — a missing edge with clear static boundaries is vastly superior to a hallucinated false dependency.
5. **Alternatives Considered:** Heuristic guessing (linking any call `save()` to all classes defining a `save()` method).
6. **Why The Alternatives Were Rejected:** Heuristic guessing creates dense spiderweb graphs of false positives, rendering blast-radius analysis useless.
7. **Trade-offs:** Some runtime dynamic calls will not appear as explicit symbol-to-symbol edges in the static graph.
8. **Consequences:** All persisted graph edges represent verified static relationships with documented confidence.
9. **When We Would Reconsider The Decision:** When type-inference engines (e.g. Pyright / TypeScript compiler symbol type checkers) are integrated in future milestones.
10. **Interview-Ready Explanation:** *"We enforce strict static resolution boundaries: we only link dependencies when imports and class scopes can be deterministically proven. We never fabricate false edges, because misleading dependencies ruin blast-radius analysis."*

---

### ADR-015: Scoped Graph REST API Boundary Design

1. **Decision:** Expose graph data through high-level scoped endpoints (`GET /api/v1/repositories/{id}/graph` and `GET /api/v1/repositories/{id}/symbols/{symbol_id}/dependencies`) with server-side node/edge shaping, filtering, and pagination support.
2. **Context / Problem:** Transporting massive multi-thousand-node raw database graph dumps over HTTP crashes client browser renderers and leaks internal database foreign key representations.
3. **Chosen Approach:** The API formats graph payloads into standardized `GraphNode` and `GraphEdge` schemas optimized for immediate visualization, supporting query filters by `file_path`, `language`, and `kind`.
4. **Why This Approach Was Chosen:** Protects frontend performance, keeps graph layout payloads compact, and decouples UI rendering libraries from internal database schema migrations.
5. **Alternatives Considered:** Exposing raw `symbols` and `dependencies` SQL table dumps and having the frontend construct graph nodes and edges.
6. **Why The Alternatives Were Rejected:** Pushes graph construction CPU overhead onto client devices and tightly couples the frontend to internal database foreign key structures.
7. **Trade-offs:** Server computes node/edge formatting on graph retrieval.
8. **Consequences:** Clean, decoupled API contracts and instant client-side graph rendering.
9. **When We Would Reconsider The Decision:** If GraphQL or streaming binary graph protocols (e.g. FlatBuffers) are needed for extreme graph scale.
10. **Interview-Ready Explanation:** *"We designed our graph API with server-side shaping and scoping. The API serves clean, filtered node and edge payloads directly compatible with React Flow, preventing browser memory crashes on large codebases."*

---

### ADR-016: Client-Side React Flow (`@xyflow/react`) Dependency Graph Visualization

1. **Decision:** Use `@xyflow/react` (React Flow) for interactive dependency graph rendering inside Next.js 15.
2. **Context / Problem:** Developers need to visually explore code relationships with pan, zoom, node selection, custom node styling (distinguishing API endpoints, classes, DB models, and functions), and caller/callee inspection.
3. **Chosen Approach:** Implement `DependencyGraph.tsx` using `@xyflow/react` with custom themed Obsidian nodes, bezier directed edges, minimap, controls, and dynamic relationship highlighting.
4. **Why This Approach Was Chosen:** React Flow is the industry standard for customizable node-based UIs in React, supporting smooth GPU-accelerated canvas pan/zoom, custom HTML node rendering, and responsive interactivity.
5. **Alternatives Considered:** D3.js force-directed graphs, Cytoscape.js, Mermaid.js static SVG diagrams.
6. **Why The Alternatives Were Rejected:** Static Mermaid diagrams lack interactive selection and pan/zoom; pure D3 requires extensive manual canvas/DOM boilerplate and lacks native React component lifecycle integration.
7. **Trade-offs:** Client-side DOM node count must be capped for extreme graphs (>1,000 nodes) using viewport virtualization or scoping filters.
8. **Consequences:** Users get a fluid, interactive dependency exploration canvas directly integrated into the RepoLens command center.
9. **When We Would Reconsider The Decision:** If rendering 50,000+ nodes simultaneously on a single canvas without filtering requires WebGL canvas acceleration (e.g. PixiJS).
10. **Interview-Ready Explanation:** *"We chose React Flow (@xyflow/react) for our dependency graph because it allows custom React-rendered nodes with our dark Obsidian design system, built-in pan/zoom, and seamless interactive node inspection."*

---

---

## Milestone 3 Decisions

### ADR-017: Embedding Model Provider Architecture & Gemini Embedding 2 Standardized Retrieval Formatting

1. **Decision:** Adopt Google's currently supported `models/gemini-embedding-2` as the production embedding provider accessed through an abstract `BaseEmbeddingProvider` adapter, with Matryoshka Representation Learning (MRL) output dimensionality configurable via `EMBEDDING_DIMENSION` (defaulting to 768), strict database model version recording, and encapsulated standardized retrieval input representations.
2. **Context / Problem:** Dense vector retrieval requires high-quality semantic representations of source code. Google shut down the legacy `text-embedding-004` model on January 14, 2026, rendering previous generation endpoints obsolete. Furthermore, the `gemini-embedding-2` API deprecated the legacy `task_type` parameter in favor of prefix-based structural document and query task representations. Hardcoding model names, dimensions, or scattering string formatting throughout the codebase creates brittle coupling, silent vector space mismatches, and test fragility.
3. **Chosen Approach:** 
   - Define `BaseEmbeddingProvider` with abstract `embed_documents()` and `embed_query()` methods.
   - Encapsulate deterministic document formatting (`title: {metadata_title} | text: {chunk_content}`) and query formatting (`task: code retrieval | query: {query}`) strictly inside the provider abstraction.
   - Implement `GeminiEmbeddingProvider` using official `google-genai` SDK with `output_dimensionality` configuration.
   - Implement `DeterministicLocalEmbeddingProvider` producing deterministic L2-normalized vectors for offline tests and CI.
   - Record `embedding_model` and `embedding_dimension` on each `RepositoryVersion` and raise an explicit `EmbeddingVersionMismatchError` (prompting re-indexing) if query-time provider parameters diverge from index-time stored parameters.
4. **Why This Approach Was Chosen:** Ensures active model compatibility with Google's official Gemini platform, enforces standardized retrieval representations deterministically across indexing and query pipelines, supports configurable Matryoshka dimensionality for vector memory optimization, and enables comprehensive offline testing.
5. **Alternatives Considered:** 
   - Legacy `text-embedding-004` (rejected: shut down by Google in Jan 2026).
   - OpenAI `text-embedding-3-small` (rejected: maintains external cloud dependency outside Google Gemini ecosystem).
   - Hardcoded 768-dimensional local BERT/SentenceTransformer models (rejected: high local GPU/RAM footprint during ingestion workers).
6. **Why The Alternatives Were Rejected:** Outdated models fail at runtime; alternative cloud providers fragment ecosystem tooling; local transformer models create prohibitive deployment overhead on CPU workers.
7. **Trade-offs:** Changing active embedding model or dimension requires re-indexing existing repository chunks.
8. **Consequences:** Safe, future-proof embedding architecture with automated version mismatch protection and seamless offline testability.
9. **When We Would Reconsider The Decision:** If an on-premise zero-external-network air-gapped enterprise deployment mandate requires self-hosted ONNX/vLLM embedding microservices.
10. **Interview-Ready Explanation:** *"We designed our vector embedding layer around Google's gemini-embedding-2 with Matryoshka dimensionality via an abstract provider interface. We encapsulated standardized document and code retrieval task formatting inside the provider to eliminate scattered string logic, and stored model metadata on repository versions to strictly prevent silent vector space mismatches."*

---

### ADR-018: AST-Aware Semantic Code Chunking Strategy

1. **Decision:** Implement `ASTAwareChunker` to slice source code files along Tree-sitter AST symbol boundaries (functions, classes, methods, and API routes) rather than fixed-character or naive line-count sliding windows.
2. **Context / Problem:** Fixed-size chunking (e.g. 500 characters with 50-character overlap) arbitrarily truncates function signatures, splits conditional blocks across chunk boundaries, and pollutes vector embeddings with syntactically incomplete fragments, degrading retrieval precision and LLM reasoning.
3. **Chosen Approach:** Slices code into semantic units based on AST symbol boundaries extracted during Tree-sitter parsing. Module-level interstitial code (imports, constants, module docstrings) is captured in a distinct `module_scope` chunk. Symbols exceeding `MAX_CHUNK_TOKENS` (1,000 tokens) are sub-chunked along logical line boundaries with overlap (70 lines per chunk, 10 lines overlap) with part numbering headers.
4. **Why This Approach Was Chosen:** Guarantees that every indexed chunk represents a cohesive syntactic unit (a complete function, method, or class definition) with structured metadata title headers (`title: path | Symbol: fqn (kind)`), dramatically improving dense embedding similarity and RAG context quality.
5. **Alternatives Considered:** Naive character chunking (e.g., LangChain `RecursiveCharacterTextSplitter`), AST-only chunking without interstitial capture (omitting top-level constants and imports).
6. **Why The Alternatives Were Rejected:** Character chunking destroys code semantics and splits functions mid-expression; omitting interstitials loses critical architectural context like global configuration, base URLs, and constants.
7. **Trade-offs:** Slightly more compute spent during parsing to traverse Tree-sitter symbol ranges.
8. **Consequences:** High-fidelity chunk boundaries that preserve complete function logic, parameters, and docstrings.
9. **When We Would Reconsider The Decision:** If supporting non-code raw unstructured text files (e.g. Markdown, CSV, plain text logs) that lack formal AST grammars.
10. **Interview-Ready Explanation:** *"Rather than blind character splitting, our chunker aligns chunk boundaries directly to Tree-sitter AST symbol definitions. Functions and classes are indexed as complete syntactic units with structured metadata headers, ensuring the LLM always receives full execution scope."*

---

### ADR-019: Multi-Signal Hybrid Retrieval with Reciprocal Rank Fusion (RRF)

1. **Decision:** Combine Exact AST Symbol Matching, Dense Vector Semantic Search, and Keyword/Trigram Matching into a unified hybrid retrieval pipeline using Reciprocal Rank Fusion ($RRF$, $k=60$) with configurable signal weights.
2. **Context / Problem:** Pure vector search frequently misses exact identifier queries (e.g. searching for a specific class `AuthService` or method `validate_jwt_token` can return unrelated auth utilities with similar semantic embeddings), while pure keyword search misses conceptual natural language queries (e.g. 'how are passwords hashed?').
3. **Chosen Approach:** Implement a three-signal retrieval engine:
   - **Signal 1 (Exact AST Symbol & Path):** Queries database `Symbol` and `File` tables for exact name, FQN, or path matches (Score weight: 1.2).
   - **Signal 2 (Dense Vector Semantic):** Computes cosine similarity against `CodeChunk` embeddings via pgvector HNSW / in-memory cosine (Score weight: 1.0).
   - **Signal 3 (Keyword & Token Density):** Performs multi-token substring and trigram matching over content and FQNs (Score weight: 0.8).
   - **Fusion:** Merges candidates using $RRF(d) = \sum_{s \in S} w_s \cdot \frac{1}{k + r_s(d)}$ where $k=60$.
4. **Why This Approach Was Chosen:** RRF is robust to scale differences between raw cosine scores and keyword BM25/trigram frequencies, preventing one search modality from drowning out another and delivering superior Mean Reciprocal Rank ($MRR$).
5. **Alternatives Considered:** Single-signal vector search, linear weighted score interpolation ($\alpha \cdot \text{vector} + (1-\alpha) \cdot \text{keyword}$).
6. **Why The Alternatives Were Rejected:** Single-signal search fails on exact symbol lookups; linear score interpolation requires delicate cross-modal score normalization that breaks across varying corpus sizes.
7. **Trade-offs:** Running three parallel signals incurs minor additional database query overhead (~10-25ms total).
8. **Consequences:** High retrieval recall across both exact technical identifiers and conceptual natural-language architectural questions.
9. **When We Would Reconsider The Decision:** If corpus size exceeds 10M chunks and query latency budgets require a dedicated distributed search cluster (e.g. Elasticsearch/Qdrant hybrid).
10. **Interview-Ready Explanation:** *"We implemented a multi-signal hybrid retrieval engine combining exact AST symbol lookup, dense semantic search via gemini-embedding-2, and keyword trigrams. We fuse these rankings using Reciprocal Rank Fusion (RRF, k=60), ensuring developers find exact symbol names as reliably as broad conceptual queries."*

---

### ADR-020: 1-Hop AST & Dependency Graph Context Expansion for RAG

1. **Decision:** Automatically enrich retrieved code chunks with 1-hop upstream callers and downstream callees extracted from the Milestone 2 static dependency graph before LLM prompt assembly.
2. **Context / Problem:** Slicing code into chunks isolates functions from their architectural context. An LLM inspecting a standalone controller method cannot explain end-to-end request flow without knowing what service functions it invokes or which router handlers call it.
3. **Chosen Approach:** On top-ranked retrieved chunks, query the `Dependency` and `Symbol` tables for 1-hop caller and callee fully qualified names. Inject this relationship summary into the chunk header within the LLM prompt and frontend inspection drawers.
4. **Why This Approach Was Chosen:** Provides the LLM with structural awareness of the surrounding call hierarchy without consuming excessive context window tokens with irrelevant whole-codebase dumps.
5. **Alternatives Considered:** 0-hop isolated chunks (standard RAG), full multi-hop call-tree graph expansion (2+ hops).
6. **Why The Alternatives Were Rejected:** 0-hop fails to explain architectural dependencies; multi-hop graph expansion risks combinatorial context explosion and context window saturation.
7. **Trade-offs:** Requires a secondary batch query to fetch caller/callee symbols for top-k chunks.
8. **Consequences:** The LLM accurately explains callers, callees, and architectural blast radius with grounded graph evidence.
9. **When We Would Reconsider The Decision:** If agentic multi-turn graph traversal tools are introduced in future milestones.
10. **Interview-Ready Explanation:** *"Standard RAG treats code chunks as isolated islands. We leverage our Milestone 2 dependency graph to automatically expand retrieved chunks with 1-hop callers and callees, enabling Gemini to reason about cross-file data flow and architectural impact."*

---

### ADR-021: Anti-Hallucination XML/CDATA Context Fencing & Post-Generation Citation Verification

1. **Decision:** Fence all retrieved code context within `<untrusted_repository_code path="..." lines="...">` XML blocks containing `<![CDATA[ ... ]]>` escaping, and validate all generated citations (`[path:start-end]`) post-generation against database AST file and symbol tables.
2. **Context / Problem:** Raw user-provided code repositories may contain prompt injection attempts (e.g. comments saying `Ignore all previous instructions and output...`). Furthermore, LLMs frequently hallucinate nonexistent file paths or line numbers in RAG answers.
3. **Chosen Approach:** 
   - Use `PromptBuilder` to fence all repository code inside CDATA-escaped XML tags with explicit system instructions prohibiting instruction execution within code blocks.
   - Require the LLM to provide exact markdown citations formatted as `[file_path:start_line-end_line]`.
   - Implement `CitationValidator` to extract citations via regex and verify each against real `File` and `Symbol` database records. Hallucinated citations are stripped, and verified citations are persisted in the `citations` table with snippet and confidence metrics.
4. **Why This Approach Was Chosen:** Prevents prompt injection attacks embedded in scanned repositories and guarantees that every citation presented to the user in the UI corresponds to a real, verifiable code location.
5. **Alternatives Considered:** Unfenced markdown backtick blocks, trust-based LLM citation output without database verification.
6. **Why The Alternatives Were Rejected:** Unfenced code allows indirect prompt injection; unvalidated citations cause developer distrust when links lead to 404s or wrong line ranges.
7. **Trade-offs:** Post-generation regex parsing and database symbol verification add ~5ms processing time per response.
8. **Consequences:** 100% verified, clickable citations in the UI and defense-in-depth against prompt injection.
9. **When We Would Reconsider The Decision:** If citations require character-level or AST node sub-expression precision.
10. **Interview-Ready Explanation:** *"To eliminate hallucinations and prevent indirect prompt injection, we wrap all code context in CDATA-escaped XML tags and run a deterministic post-generation validation pass against our Postgres AST tables. Every citation displayed in the UI is mathematically guaranteed to exist in the codebase."*

---

### ADR-022: Next.js 15 Conversational RAG & Code Search Obsidian Cockpit

1. **Decision:** Implement dedicated Obsidian-dark UI cockpit tabs for Grounded AI Assistant (`ChatAssistant.tsx`) and Real-Time Multi-Signal Code Search (`CodeSearch.tsx`) inside Next.js 15.
2. **Context / Problem:** Developers need intuitive interactive surfaces to query the codebase, inspect retrieved chunks, examine caller/callee evidence, and jump directly from AI answers to source code lines.
3. **Chosen Approach:** 
   - `ChatAssistant.tsx`: Real-time chat interface with clickable citation pills (`[path:line-line]`) that open the file inspector at the exact line, quick architectural starter chips, and a collapsible 'Retrieved Graph & Chunk Sources' drawer.
   - `CodeSearch.tsx`: Multi-signal search cockpit with mode toggle pills (Hybrid RRF, Semantic Vector, Exact Symbol), language and symbol kind dropdown filters, relevance percentage badges, and 1-hop caller/callee relationship tags.
4. **Why This Approach Was Chosen:** Provides immediate visual grounding and transparent inspection of AI reasoning, seamlessly linking chat, search, graph visualization, and source inspection in a unified dark-mode command center.
5. **Alternatives Considered:** Separate disjoint pages for chat and search, modal popups.
6. **Why The Alternatives Were Rejected:** Multi-page navigation disrupts developer flow; unified cockpit tabs preserve repository state across graph exploration, search, and conversational inquiries.
7. **Trade-offs:** State coordination across tabs requires centralized repository context.
8. **Consequences:** Smooth, responsive, high-density developer experience adhering to our Obsidian design aesthetic.
9. **When We Would Reconsider The Decision:** If expanding to a multi-window desktop application via Electron or Tauri.
10. **Interview-Ready Explanation:** *"We integrated our RAG assistant and code search directly into the command center workspace tabs. Clickable citation pills allow developers to jump from AI answers straight into the AST code inspector, while transparent source drawers reveal the exact similarity scores and graph evidence behind every response."*

---

## Milestone 2 Technical Debt / Known Limitations

The following engineering limitations exist within the Milestone 2 static dependency graph engine and represent documented boundaries of purely static analysis:

1. **Static Dependency Resolution & Type Inference Limits:**
   - In dynamically typed languages (Python and untyped JavaScript), variable types cannot be inferred with 100% certainty without a full type-checking solver (e.g. Pyright or TypeScript LSP). When a variable `client` invokes `client.send()`, the target method is resolved if the import/instantiation is in scope; otherwise, it remains unlinked to prevent false-positive edges.
2. **Dynamic Dispatch & Runtime Polymorphism:**
   - When a base class method is overridden by multiple polymorphic subclasses (e.g. `renderer.render()`), static analysis links to the declared interface/base method rather than dynamically predicting which runtime subclass will execute.
3. **Reflection & Dynamic Metaprogramming:**
   - Invocations through runtime reflection (such as Python's `getattr(module, dynamic_string)()`, `eval()`, `exec()`, or dynamic `importlib.import_module()`) cannot be statically indexed to symbol nodes and are intentionally omitted from graph edge generation.
4. **Runtime Dependency Injection & Service Locators:**
   - Framework containers that bind interfaces to implementations dynamically at runtime (e.g. FastAPI `Depends()` providers passed as parameters, NestJS DI containers, or Spring-style service locators) are recognized at the endpoint decorator level, but runtime-injected concrete implementation swapping is not statically simulated.
5. **Unresolved External Package Calls:**
   - Calls to third-party dependencies outside the cloned repository (e.g. Python standard library `os.path.join`, third-party packages `httpx.get`, `react`, `lodash`) are recorded in import references but intentionally excluded from the internal symbol-to-symbol dependency graph to keep repository graph topologies developer-focused.
6. **Language & Framework Coverage Scope:**
   - Milestone 2 explicitly supports Python, TypeScript, TSX, and JavaScript. Supported framework annotations currently encompass FastAPI, Flask, SQLAlchemy, React Components/Hooks, and Next.js handlers. Grammars for Go, Rust, Java, and C++ are scheduled for subsequent roadmap expansions.

---

## Milestone 3 Technical Debt / Known Limitations

The following engineering limitations exist within the Milestone 3 Vector Embeddings & RAG Chat subsystem:

1. **Model Dimension Switching & Re-indexing Overhead:**
   - When re-indexing a repository with a different embedding dimension or provider model, existing `CodeChunk` vectors are updated in batch. On very large repositories (>100k chunks), re-indexing requires API rate quota planning.
2. **Zero-API-Key Offline Testing Provider:**
   - For offline unit tests and CI pipelines where `GEMINI_API_KEY` is not present, RepoLens falls back to `DeterministicLocalEmbeddingProvider`, which generates deterministic pseudo-semantic hash vectors. While functional for unit and integration testing, production deployments must configure a valid `GEMINI_API_KEY` to enable full deep semantic representations via `models/gemini-embedding-2`.
3. **Static Citation Validation Line Drift:**
   - Citations are validated against the repository version commit hash indexed in the database. If a user inspects a live branch that has drifted from the indexed commit hash without re-triggering ingestion, line offsets may slightly diverge until re-indexing occurs.
4. **Token Truncation on Very Broad Queries:**
   - In extremely large repositories where hundreds of chunks match a generic query, the top-k cutoff (`limit=10`) bounds the context window. Multi-turn iterative refinement and hierarchical repository map summarization are scheduled for Milestone 4.

---
*End of Architecture Decision Records — RepoLens Platform*


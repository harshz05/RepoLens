import asyncio
import json
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_

from packages.db.session import get_async_session, AsyncSessionLocal
from packages.db.models import (
    Repository,
    RepositoryVersion,
    AnalysisRun,
    File,
    Symbol,
    Dependency,
    CodeChunk,
    ChatSession,
    ChatMessage,
    Citation,
    AuditRun,
    SecurityFinding,
    QualityFinding,
)
from services.worker.ingestion_worker import (
    validate_github_url,
    parse_repo_owner_name,
    run_ingestion_pipeline,
    reindex_repository_version,
    EventBroker,
)
from services.worker.audit_worker import run_audit_pipeline
from packages.code_intel.retrieval.hybrid_engine import HybridRetrievalEngine
from packages.code_intel.rag.service import CodebaseRAGService
from packages.code_intel.embeddings.provider import get_embedding_provider
from apps.api.app.schemas import (
    IngestRepositoryRequest,
    IngestRepositoryResponse,
    RepositorySummarySchema,
    AnalysisRunSchema,
    SymbolSchema,
    GraphNodeSchema,
    GraphEdgeSchema,
    RepositoryGraphResponse,
    SymbolDependencyDetailResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItemSchema,
    GraphContextSchema,
    ChatRequest,
    ChatResponse,
    CitationSchema,
    ChatMessageSchema,
    ChatSessionSchema,
    ReindexResponse,
    AuditTriggerRequest,
    AuditRunResponse,
    SecurityFindingSchema,
    QualityFindingSchema,
    AuditSummarySchema,
)

router = APIRouter(prefix="/repositories", tags=["Repositories"])

@router.post("/ingest", response_model=IngestRepositoryResponse, status_code=status.HTTP_201_CREATED)
async def ingest_repository(
    payload: IngestRepositoryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ingest a public GitHub repository asynchronously.
    Validates URL, initializes DB records, and launches ingestion worker background task.
    """
    if not validate_github_url(payload.github_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository URL. Must be a valid public GitHub or GitLab URL (e.g. https://github.com/owner/repo)"
        )

    owner, name = parse_repo_owner_name(payload.github_url)

    # Check or create Repository
    stmt = select(Repository).where(Repository.owner == owner, Repository.name == name)
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()

    if not repo:
        repo = Repository(
            github_url=payload.github_url,
            owner=owner,
            name=name,
            default_branch=payload.branch,
        )
        db.add(repo)
        await db.flush()

    # Create RepositoryVersion
    repo_version = RepositoryVersion(
        repository_id=repo.id,
        commit_hash="HEAD",
        branch=payload.branch,
        status="IN_PROGRESS",
    )
    db.add(repo_version)
    await db.flush()

    # Create AnalysisRun
    analysis_run = AnalysisRun(
        repository_version_id=repo_version.id,
        status="QUEUED",
        current_step="QUEUED",
        progress_percentage=0.0,
        step_details="Analysis run queued...",
    )
    db.add(analysis_run)
    await db.commit()

    # Helper function for background task with standalone session
    async def worker_task(run_id: str):
        async with AsyncSessionLocal() as bg_session:
            await run_ingestion_pipeline(run_id, bg_session)

    background_tasks.add_task(worker_task, analysis_run.id)

    return IngestRepositoryResponse(
        repository_id=repo.id,
        repository_version_id=repo_version.id,
        analysis_run_id=analysis_run.id,
        owner=owner,
        name=name,
        status="QUEUED",
        message="Repository ingestion started successfully."
    )

@router.get("", response_model=List[RepositorySummarySchema])
async def list_repositories(db: AsyncSession = Depends(get_async_session)):
    """List all ingested repositories and their latest statistics."""
    stmt = select(Repository).order_by(desc(Repository.created_at))
    res = await db.execute(stmt)
    repos = res.scalars().all()

    summaries = []
    for repo in repos:
        # Fetch latest version
        ver_stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repo.id)
            .order_by(desc(RepositoryVersion.processed_at))
        )
        ver_res = await db.execute(ver_stmt)
        latest_ver = ver_res.scalars().first()

        latest_status = "PENDING"
        total_files = 0
        total_loc = 0
        total_symbols = 0
        total_dependencies = 0
        total_chunks = 0
        emb_model = None
        emb_dim = None
        lang_breakdown: Dict[str, int] = {}

        if latest_ver:
            latest_status = latest_ver.status
            emb_model = latest_ver.embedding_model
            emb_dim = latest_ver.embedding_dimension

            # Files & LOC
            file_stmt = select(File).where(File.repository_version_id == latest_ver.id)
            file_res = await db.execute(file_stmt)
            files = file_res.scalars().all()

            total_files = len(files)
            total_loc = sum(f.line_count for f in files)

            for f in files:
                lang_breakdown[f.language] = lang_breakdown.get(f.language, 0) + 1

            # Symbol count, Dependency count, Chunk count
            if files:
                file_ids = [f.id for f in files]
                sym_stmt = select(func.count(Symbol.id)).where(Symbol.file_id.in_(file_ids))
                sym_res = await db.execute(sym_stmt)
                total_symbols = sym_res.scalar() or 0

                dep_stmt = select(func.count(Dependency.id)).where(Dependency.file_id.in_(file_ids))
                dep_res = await db.execute(dep_stmt)
                total_dependencies = dep_res.scalar() or 0

                chunk_stmt = select(func.count(CodeChunk.id)).where(CodeChunk.file_id.in_(file_ids))
                chunk_res = await db.execute(chunk_stmt)
                total_chunks = chunk_res.scalar() or 0

        summaries.append(
            RepositorySummarySchema(
                id=repo.id,
                github_url=repo.github_url,
                owner=repo.owner,
                name=repo.name,
                default_branch=repo.default_branch,
                created_at=repo.created_at,
                latest_status=latest_status,
                total_files=total_files,
                total_loc=total_loc,
                total_symbols=total_symbols,
                total_dependencies=total_dependencies,
                total_chunks=total_chunks,
                embedding_model=emb_model,
                embedding_dimension=emb_dim,
                language_breakdown=lang_breakdown,
            )
        )

    return summaries

@router.get("/{id}")
async def get_repository_detail(id: str, db: AsyncSession = Depends(get_async_session)):
    """Get detailed file tree, symbols, dependencies count, and latest analysis status for a repository."""
    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()

    files_list = []
    total_symbols = 0
    total_dependencies = 0
    total_chunks = 0
    analysis_run_data = None

    if latest_ver:
        # Latest analysis run
        run_stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.repository_version_id == latest_ver.id)
            .order_by(desc(AnalysisRun.started_at))
        )
        run_res = await db.execute(run_stmt)
        analysis_run = run_res.scalars().first()
        if analysis_run:
            analysis_run_data = AnalysisRunSchema(
                id=analysis_run.id,
                status=analysis_run.status,
                current_step=analysis_run.current_step,
                progress_percentage=analysis_run.progress_percentage,
                step_details=analysis_run.step_details,
                error_log=analysis_run.error_log,
                started_at=analysis_run.started_at,
                completed_at=analysis_run.completed_at,
            )

        # Files, Symbols, Dependencies, Chunks
        file_stmt = select(File).where(File.repository_version_id == latest_ver.id)
        file_res = await db.execute(file_stmt)
        files = file_res.scalars().all()

        file_ids = [f.id for f in files]
        if file_ids:
            dep_count_stmt = select(func.count(Dependency.id)).where(Dependency.file_id.in_(file_ids))
            dep_res = await db.execute(dep_count_stmt)
            total_dependencies = dep_res.scalar() or 0

            chunk_count_stmt = select(func.count(CodeChunk.id)).where(CodeChunk.file_id.in_(file_ids))
            chunk_res = await db.execute(chunk_count_stmt)
            total_chunks = chunk_res.scalar() or 0

        for f in files:
            sym_stmt = select(Symbol).where(Symbol.file_id == f.id)
            sym_res = await db.execute(sym_stmt)
            symbols = sym_res.scalars().all()
            total_symbols += len(symbols)

            files_list.append({
                "id": f.id,
                "path": f.path,
                "language": f.language,
                "line_count": f.line_count,
                "byte_size": f.byte_size,
                "symbol_count": len(symbols),
                "symbols": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "fully_qualified_name": s.fully_qualified_name,
                        "kind": s.kind,
                        "start_line": s.start_line,
                        "end_line": s.end_line,
                        "signature": s.signature,
                        "docstring": s.docstring,
                    }
                    for s in symbols
                ]
            })

    return {
        "id": repo.id,
        "github_url": repo.github_url,
        "owner": repo.owner,
        "name": repo.name,
        "default_branch": repo.default_branch,
        "created_at": repo.created_at,
        "total_files": len(files_list),
        "total_loc": sum(f["line_count"] for f in files_list),
        "total_symbols": total_symbols,
        "total_dependencies": total_dependencies,
        "total_chunks": total_chunks,
        "embedding_model": latest_ver.embedding_model if latest_ver else None,
        "embedding_dimension": latest_ver.embedding_dimension if latest_ver else None,
        "latest_analysis_run": analysis_run_data,
        "files": files_list,
    }

@router.get("/{id}/graph", response_model=RepositoryGraphResponse)
async def get_repository_graph(
    id: str,
    file_path: Optional[str] = Query(None, description="Filter graph nodes/edges to specific file"),
    kind: Optional[str] = Query(None, description="Filter symbols by kind (e.g. function, class, api_endpoint)"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get full or scoped dependency graph for a repository.
    Returns nodes (symbols) and directed edges (dependencies) formatted for React Flow.
    """
    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()

    if not latest_ver:
        return RepositoryGraphResponse(
            repository_id=repo.id,
            version_id="",
            total_nodes=0,
            total_edges=0,
            nodes=[],
            edges=[],
            files_count=0,
            languages={},
        )

    # Fetch files
    files_stmt = select(File).where(File.repository_version_id == latest_ver.id)
    if file_path:
        files_stmt = files_stmt.where(File.path == file_path)
    files_res = await db.execute(files_stmt)
    files = files_res.scalars().all()
    file_map = {f.id: f for f in files}
    file_ids = list(file_map.keys())

    languages: Dict[str, int] = {}
    for f in files:
        languages[f.language] = languages.get(f.language, 0) + 1

    if not file_ids:
        return RepositoryGraphResponse(
            repository_id=repo.id,
            version_id=latest_ver.id,
            total_nodes=0,
            total_edges=0,
            nodes=[],
            edges=[],
            files_count=0,
            languages=languages,
        )

    # Fetch symbols
    sym_stmt = select(Symbol).where(Symbol.file_id.in_(file_ids))
    if kind:
        sym_stmt = sym_stmt.where(Symbol.kind == kind)
    sym_res = await db.execute(sym_stmt)
    symbols = sym_res.scalars().all()
    symbol_ids = {s.id for s in symbols}

    nodes: List[GraphNodeSchema] = []
    for s in symbols:
        file_obj = file_map.get(s.file_id)
        f_path = file_obj.path if file_obj else ""
        nodes.append(
            GraphNodeSchema(
                id=s.id,
                label=s.name,
                fqn=s.fully_qualified_name,
                kind=s.kind,
                file_path=f_path,
                line_range=[s.start_line, s.end_line],
                signature=s.signature,
                docstring=s.docstring,
            )
        )

    # Fetch dependencies
    dep_stmt = select(Dependency).where(
        or_(
            Dependency.caller_symbol_id.in_(symbol_ids),
            Dependency.callee_symbol_id.in_(symbol_ids),
        )
    )
    dep_res = await db.execute(dep_stmt)
    deps = dep_res.scalars().all()

    edges: List[GraphEdgeSchema] = []
    for dep in deps:
        if dep.caller_symbol_id in symbol_ids and dep.callee_symbol_id in symbol_ids:
            file_obj = file_map.get(dep.file_id)
            edges.append(
                GraphEdgeSchema(
                    id=f"edge-{dep.id}",
                    source=dep.caller_symbol_id,
                    target=dep.callee_symbol_id,
                    type=dep.dependency_type,
                    label=dep.dependency_type,
                    line_number=dep.line_number,
                    file_path=file_obj.path if file_obj else None,
                )
            )

    return RepositoryGraphResponse(
        repository_id=repo.id,
        version_id=latest_ver.id,
        total_nodes=len(nodes),
        total_edges=len(edges),
        nodes=nodes,
        edges=edges,
        files_count=len(files),
        languages=languages,
    )

@router.get("/{id}/symbols/{symbol_id}/dependencies", response_model=SymbolDependencyDetailResponse)
async def get_symbol_dependencies(
    id: str,
    symbol_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get upstream callers and downstream callees for a specific symbol.
    """
    sym_stmt = select(Symbol).where(Symbol.id == symbol_id)
    sym_res = await db.execute(sym_stmt)
    symbol = sym_res.scalar_one_or_none()
    if not symbol:
        raise HTTPException(status_code=404, detail="Symbol not found")

    file_stmt = select(File).where(File.id == symbol.file_id)
    file_res = await db.execute(file_stmt)
    file_obj = file_res.scalar_one_or_none()
    file_path = file_obj.path if file_obj else ""

    # Outgoing dependencies (symbol is caller)
    out_stmt = select(Dependency).where(Dependency.caller_symbol_id == symbol_id)
    out_res = await db.execute(out_stmt)
    out_deps = out_res.scalars().all()

    callee_ids = [d.callee_symbol_id for d in out_deps]
    callees = []
    if callee_ids:
        callee_stmt = select(Symbol).where(Symbol.id.in_(callee_ids))
        callee_res = await db.execute(callee_stmt)
        callees = callee_res.scalars().all()

    # Incoming dependencies (symbol is callee)
    in_stmt = select(Dependency).where(Dependency.callee_symbol_id == symbol_id)
    in_res = await db.execute(in_stmt)
    in_deps = in_res.scalars().all()

    caller_ids = [d.caller_symbol_id for d in in_deps]
    callers = []
    if caller_ids:
        caller_stmt = select(Symbol).where(Symbol.id.in_(caller_ids))
        caller_res = await db.execute(caller_stmt)
        callers = caller_res.scalars().all()

    incoming_edges = [
        GraphEdgeSchema(
            id=f"edge-{d.id}",
            source=d.caller_symbol_id,
            target=d.callee_symbol_id,
            type=d.dependency_type,
            label=d.dependency_type,
            line_number=d.line_number,
        )
        for d in in_deps
    ]

    outgoing_edges = [
        GraphEdgeSchema(
            id=f"edge-{d.id}",
            source=d.caller_symbol_id,
            target=d.callee_symbol_id,
            type=d.dependency_type,
            label=d.dependency_type,
            line_number=d.line_number,
        )
        for d in out_deps
    ]

    return SymbolDependencyDetailResponse(
        symbol=SymbolSchema(
            id=symbol.id,
            name=symbol.name,
            fully_qualified_name=symbol.fully_qualified_name,
            kind=symbol.kind,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            signature=symbol.signature,
            docstring=symbol.docstring,
            file_path=file_path,
        ),
        file_path=file_path,
        callers=[
            SymbolSchema(
                id=s.id,
                name=s.name,
                fully_qualified_name=s.fully_qualified_name,
                kind=s.kind,
                start_line=s.start_line,
                end_line=s.end_line,
                signature=s.signature,
                docstring=s.docstring,
            )
            for s in callers
        ],
        callees=[
            SymbolSchema(
                id=s.id,
                name=s.name,
                fully_qualified_name=s.fully_qualified_name,
                kind=s.kind,
                start_line=s.start_line,
                end_line=s.end_line,
                signature=s.signature,
                docstring=s.docstring,
            )
            for s in callees
        ],
        incoming_edges=incoming_edges,
        outgoing_edges=outgoing_edges,
    )

# --- Milestone 3 Endpoints: Search, Chat, Sessions, Reindex ---

@router.post("/{id}/search", response_model=SearchResponse)
async def search_repository(
    id: str,
    payload: SearchRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Execute multi-signal hybrid, semantic vector, or exact symbol search across indexed code chunks.
    """
    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()
    if not latest_ver:
        return SearchResponse(query=payload.query, total_results=0, results=[])

    try:
        retrieval_res = await HybridRetrievalEngine.retrieve(
            session=db,
            repository_version_id=latest_ver.id,
            query=payload.query,
            mode=payload.mode,
            limit=payload.limit,
            file_filter=payload.file_path,
            language_filter=payload.language,
            kind_filter=payload.kind,
            expand_graph_context=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result_items = []
    for c in retrieval_res.chunks:
        g_ctx = None
        if c.graph_context:
            g_ctx = GraphContextSchema(
                symbol_fqn=c.graph_context.symbol_fqn,
                kind=c.graph_context.kind,
                callers=c.graph_context.callers,
                callees=c.graph_context.callees,
            )
        result_items.append(
            SearchResultItemSchema(
                chunk_id=c.chunk_id,
                file_path=c.file_path,
                symbol_fqn=c.symbol_fqn,
                kind=c.symbol_kind,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                score=c.score,
                match_type=c.match_type,
                graph_context=g_ctx,
                embedding_model=c.embedding_model,
            )
        )

    return SearchResponse(
        query=payload.query,
        total_results=len(result_items),
        results=result_items,
    )

@router.post("/{id}/chat", response_model=ChatResponse)
async def chat_with_repository(
    id: str,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Execute grounded conversational inquiry with verified code citations and graph evidence.
    """
    try:
        chat_data = await CodebaseRAGService.chat(
            session=db,
            repository_id=id,
            message=payload.message,
            chat_session_id=payload.session_id,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(
        session_id=chat_data["session_id"],
        message_id=chat_data["message_id"],
        response=chat_data["response"],
        citations=[
            CitationSchema(
                file_path=c["file_path"],
                start_line=c["start_line"],
                end_line=c["end_line"],
                symbol_name=c.get("symbol_name"),
                snippet=c["snippet"],
                confidence_score=c["confidence_score"],
            )
            for c in chat_data["citations"]
        ],
        retrieved_chunks=[
            SearchResultItemSchema(
                chunk_id=rc["chunk_id"],
                file_path=rc["file_path"],
                symbol_fqn=rc.get("symbol_fqn"),
                kind=rc.get("kind"),
                start_line=rc["start_line"],
                end_line=rc["end_line"],
                content=rc["content"],
                score=rc["score"],
                match_type=rc["match_type"],
                graph_context=GraphContextSchema(
                    symbol_fqn=rc["graph_context"]["symbol_fqn"],
                    kind=rc["graph_context"]["kind"],
                    callers=rc["graph_context"]["callers"],
                    callees=rc["graph_context"]["callees"],
                ) if rc.get("graph_context") else None,
            )
            for rc in chat_data["retrieved_chunks"]
        ],
    )

@router.get("/{id}/chat/sessions", response_model=List[ChatSessionSchema])
async def list_chat_sessions(
    id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all chat sessions and message history for a repository.
    """
    stmt = (
        select(ChatSession)
        .where(ChatSession.repository_id == id)
        .order_by(desc(ChatSession.updated_at))
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    result = []
    for s in sessions:
        msg_stmt = (
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == s.id)
            .order_by(ChatMessage.created_at)
        )
        msg_res = await db.execute(msg_stmt)
        messages = msg_res.scalars().all()

        msg_list = []
        for m in messages:
            cit_stmt = select(Citation).where(Citation.message_id == m.id)
            cit_res = await db.execute(cit_stmt)
            cits = cit_res.scalars().all()

            msg_list.append(
                ChatMessageSchema(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                    citations=[
                        CitationSchema(
                            file_path=c.file_path,
                            start_line=c.start_line,
                            end_line=c.end_line,
                            symbol_name=None,
                            snippet=c.text_snippet,
                            confidence_score=c.confidence_score,
                        )
                        for c in cits
                    ],
                )
            )

        result.append(
            ChatSessionSchema(
                id=s.id,
                repository_id=s.repository_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                messages=msg_list,
            )
        )

    return result

@router.get("/{id}/chat/sessions/{session_id}", response_model=ChatSessionSchema)
async def get_chat_session_detail(
    id: str,
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed chat session history with citations.
    """
    stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.repository_id == id)
    res = await db.execute(stmt)
    sess = res.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Chat session not found")

    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == sess.id)
        .order_by(ChatMessage.created_at)
    )
    msg_res = await db.execute(msg_stmt)
    messages = msg_res.scalars().all()

    msg_list = []
    for m in messages:
        cit_stmt = select(Citation).where(Citation.message_id == m.id)
        cit_res = await db.execute(cit_stmt)
        cits = cit_res.scalars().all()

        msg_list.append(
            ChatMessageSchema(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                citations=[
                    CitationSchema(
                        file_path=c.file_path,
                        start_line=c.start_line,
                        end_line=c.end_line,
                        symbol_name=None,
                        snippet=c.text_snippet,
                        confidence_score=c.confidence_score,
                    )
                    for c in cits
                ],
            )
        )

    return ChatSessionSchema(
        id=sess.id,
        repository_id=sess.repository_id,
        title=sess.title,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
        messages=msg_list,
    )

@router.post("/{id}/reindex", response_model=ReindexResponse)
async def reindex_repository(
    id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Trigger re-embedding and re-indexing of all code chunks with active embedding model and dimension.
    """
    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()
    if not latest_ver:
        raise HTTPException(status_code=400, detail="No analyzed version found to reindex")

    provider = get_embedding_provider()
    count = await reindex_repository_version(latest_ver.id, db)

    return ReindexResponse(
        repository_id=repo.id,
        version_id=latest_ver.id,
        reindexed_chunks=count,
        embedding_model=provider.model_name,
        embedding_dimension=provider.dimension,
        message=f"Successfully reindexed {count} chunks using {provider.model_name} (dim {provider.dimension})",
    )

@router.get("/events/{analysis_run_id}")
async def stream_analysis_events(analysis_run_id: str):
    """SSE endpoint streaming live progress events for an analysis run."""
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def listener(data: dict):
            queue.put_nowait(data)

        EventBroker.subscribe(analysis_run_id, listener)
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("step") in ("COMPLETED", "FAILED"):
                    break
        finally:
            EventBroker.unsubscribe(analysis_run_id, listener)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Milestone 4 Endpoints: Security & Code Quality Audit ---

@router.post("/{id}/audit", response_model=AuditRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_repository_audit(
    id: str,
    payload: Optional[AuditTriggerRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Trigger an asynchronous security and code-quality audit against the latest repository version.
    """
    enable_ai = payload.enable_ai_review if payload else True

    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()
    if not latest_ver:
        raise HTTPException(status_code=400, detail="No analyzed repository version found to audit")

    # Create AuditRun
    audit_run = AuditRun(
        repository_version_id=latest_ver.id,
        status="QUEUED",
        current_step="QUEUED",
        progress_percentage=0.0,
        step_details="Audit queued...",
    )
    db.add(audit_run)
    await db.commit()

    async def audit_task(run_id: str, ai_flag: bool):
        async with AsyncSessionLocal() as bg_session:
            await run_audit_pipeline(run_id, bg_session, enable_ai_review=ai_flag)

    background_tasks.add_task(audit_task, audit_run.id, enable_ai)

    return AuditRunResponse(
        audit_run_id=audit_run.id,
        repository_id=repo.id,
        version_id=latest_ver.id,
        status="QUEUED",
        message="Repository security and quality audit dispatched successfully.",
    )

@router.get("/{id}/audit/latest", response_model=AuditSummarySchema)
async def get_latest_audit(
    id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Fetch the latest completed or running audit summary and 5-dimension health scores.
    """
    stmt = select(Repository).where(Repository.id == id)
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    ver_stmt = (
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(desc(RepositoryVersion.processed_at))
    )
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalars().first()
    if not latest_ver:
        raise HTTPException(status_code=404, detail="No analyzed repository version found")

    audit_stmt = (
        select(AuditRun)
        .where(AuditRun.repository_version_id == latest_ver.id)
        .order_by(desc(AuditRun.started_at))
    )
    audit_res = await db.execute(audit_stmt)
    audit = audit_res.scalars().first()
    if not audit:
        raise HTTPException(status_code=404, detail="No audit runs found for this repository")

    # Count findings
    sec_count_stmt = select(func.count(SecurityFinding.id)).where(SecurityFinding.audit_run_id == audit.id)
    sec_res = await db.execute(sec_count_stmt)
    total_sec = sec_res.scalar() or 0

    qual_count_stmt = select(func.count(QualityFinding.id)).where(QualityFinding.audit_run_id == audit.id)
    qual_res = await db.execute(qual_count_stmt)
    total_qual = qual_res.scalar() or 0

    dim_summary = {}
    if audit.summary_metrics_json:
        try:
            dim_summary = json.loads(audit.summary_metrics_json)
        except Exception:
            dim_summary = {}

    return AuditSummarySchema(
        id=audit.id,
        repository_id=repo.id,
        version_id=latest_ver.id,
        status=audit.status,
        current_step=audit.current_step,
        progress_percentage=audit.progress_percentage,
        step_details=audit.step_details,
        error_log=audit.error_log,
        health_score=audit.health_score,
        security_score=audit.security_score,
        maintainability_score=audit.maintainability_score,
        complexity_score=audit.complexity_score,
        coupling_score=audit.coupling_score,
        architecture_score=audit.architecture_score,
        dimensions_summary=dim_summary,
        total_security_findings=total_sec,
        total_quality_findings=total_qual,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
    )

@router.get("/{id}/audit/{audit_id}", response_model=AuditSummarySchema)
async def get_audit_detail(
    id: str,
    audit_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Fetch specific audit run details by audit_id.
    """
    stmt = select(AuditRun).where(AuditRun.id == audit_id)
    res = await db.execute(stmt)
    audit = res.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit run not found")

    sec_count_stmt = select(func.count(SecurityFinding.id)).where(SecurityFinding.audit_run_id == audit.id)
    sec_res = await db.execute(sec_count_stmt)
    total_sec = sec_res.scalar() or 0

    qual_count_stmt = select(func.count(QualityFinding.id)).where(QualityFinding.audit_run_id == audit.id)
    qual_res = await db.execute(qual_count_stmt)
    total_qual = qual_res.scalar() or 0

    dim_summary = {}
    if audit.summary_metrics_json:
        try:
            dim_summary = json.loads(audit.summary_metrics_json)
        except Exception:
            dim_summary = {}

    return AuditSummarySchema(
        id=audit.id,
        repository_id=id,
        version_id=audit.repository_version_id,
        status=audit.status,
        current_step=audit.current_step,
        progress_percentage=audit.progress_percentage,
        step_details=audit.step_details,
        error_log=audit.error_log,
        health_score=audit.health_score,
        security_score=audit.security_score,
        maintainability_score=audit.maintainability_score,
        complexity_score=audit.complexity_score,
        coupling_score=audit.coupling_score,
        architecture_score=audit.architecture_score,
        dimensions_summary=dim_summary,
        total_security_findings=total_sec,
        total_quality_findings=total_qual,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
    )

@router.get("/{id}/security/findings", response_model=List[SecurityFindingSchema])
async def list_security_findings(
    id: str,
    audit_id: Optional[str] = Query(None, description="Filter by specific audit run ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)"),
    category: Optional[str] = Query(None, description="Filter by category (Secrets, SQL Injection, etc.)"),
    detection_source: Optional[str] = Query(None, description="Filter by detection source"),
    confidence_min: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    file_path: Optional[str] = Query(None, description="Filter by file path"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List security findings for a repository with filtering and pagination.
    """
    target_audit_id = audit_id
    if not target_audit_id:
        # Resolve latest completed audit
        ver_stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == id)
            .order_by(desc(RepositoryVersion.processed_at))
        )
        ver_res = await db.execute(ver_stmt)
        latest_ver = ver_res.scalars().first()
        if not latest_ver:
            return []

        audit_stmt = (
            select(AuditRun)
            .where(AuditRun.repository_version_id == latest_ver.id)
            .order_by(desc(AuditRun.started_at))
        )
        audit_res = await db.execute(audit_stmt)
        latest_audit = audit_res.scalars().first()
        if not latest_audit:
            return []
        target_audit_id = latest_audit.id

    query = select(SecurityFinding).where(SecurityFinding.audit_run_id == target_audit_id)

    if severity:
        query = query.where(SecurityFinding.severity == severity.upper())
    if category:
        query = query.where(SecurityFinding.category == category)
    if detection_source:
        query = query.where(SecurityFinding.detection_source == detection_source.upper())
    if confidence_min is not None:
        query = query.where(SecurityFinding.confidence >= confidence_min)

    query = query.order_by(
        # Order by severity priority
        desc(SecurityFinding.severity == "CRITICAL"),
        desc(SecurityFinding.severity == "HIGH"),
        desc(SecurityFinding.severity == "MEDIUM"),
        desc(SecurityFinding.confidence),
        SecurityFinding.created_at,
    ).offset(offset).limit(limit)

    res = await db.execute(query)
    findings = res.scalars().all()

    results = []
    for f in findings:
        f_path = f.file.path if f.file else ""
        if file_path and file_path not in f_path:
            continue

        sym_name = f.symbol.name if f.symbol else None

        results.append(
            SecurityFindingSchema(
                id=f.id,
                rule_id=f.rule_id,
                category=f.category,
                severity=f.severity,
                confidence=f.confidence,
                detection_source=f.detection_source,
                file_path=f_path,
                start_line=f.start_line,
                end_line=f.end_line,
                title=f.title,
                description=f.description,
                evidence=f.evidence,
                remediation=f.remediation,
                symbol_name=sym_name,
                graph_reachability_path=f.graph_reachability_path,
                is_ai_assisted=f.is_ai_assisted,
                created_at=f.created_at,
            )
        )

    return results

@router.get("/{id}/quality/findings", response_model=List[QualityFindingSchema])
async def list_quality_findings(
    id: str,
    audit_id: Optional[str] = Query(None, description="Filter by specific audit run ID"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    file_path: Optional[str] = Query(None, description="Filter by file path"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List code quality findings for a repository with filtering and pagination.
    """
    target_audit_id = audit_id
    if not target_audit_id:
        ver_stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == id)
            .order_by(desc(RepositoryVersion.processed_at))
        )
        ver_res = await db.execute(ver_stmt)
        latest_ver = ver_res.scalars().first()
        if not latest_ver:
            return []

        audit_stmt = (
            select(AuditRun)
            .where(AuditRun.repository_version_id == latest_ver.id)
            .order_by(desc(AuditRun.started_at))
        )
        audit_res = await db.execute(audit_stmt)
        latest_audit = audit_res.scalars().first()
        if not latest_audit:
            return []
        target_audit_id = latest_audit.id

    query = select(QualityFinding).where(QualityFinding.audit_run_id == target_audit_id)

    if metric_name:
        query = query.where(QualityFinding.metric_name == metric_name)
    if severity:
        query = query.where(QualityFinding.severity == severity.upper())

    query = query.order_by(
        desc(QualityFinding.severity == "CRITICAL"),
        desc(QualityFinding.severity == "HIGH"),
        desc(QualityFinding.severity == "MEDIUM"),
        desc(QualityFinding.value),
    ).offset(offset).limit(limit)

    res = await db.execute(query)
    findings = res.scalars().all()

    results = []
    for f in findings:
        f_path = f.file.path if f.file else ""
        if file_path and file_path not in f_path:
            continue

        sym_name = f.symbol.name if f.symbol else None

        results.append(
            QualityFindingSchema(
                id=f.id,
                rule_id=f.rule_id,
                metric_name=f.metric_name,
                title=f.title,
                description=f.description,
                severity=f.severity,
                confidence=f.confidence,
                detection_source=f.detection_source,
                value=f.value,
                threshold=f.threshold,
                file_path=f_path,
                start_line=f.start_line,
                end_line=f.end_line,
                recommendation=f.recommendation,
                symbol_name=sym_name,
                is_ai_assisted=f.is_ai_assisted,
                created_at=f.created_at,
            )
        )

    return results

@router.get("/audit/events/{audit_run_id}")
async def stream_audit_events(audit_run_id: str):
    """SSE endpoint streaming live progress events for an audit run."""
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def listener(data: dict):
            queue.put_nowait(data)

        EventBroker.subscribe(audit_run_id, listener)
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("step") in ("COMPLETED", "FAILED"):
                    break
        finally:
            EventBroker.unsubscribe(audit_run_id, listener)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


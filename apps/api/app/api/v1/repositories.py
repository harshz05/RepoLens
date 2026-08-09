import asyncio
import json
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from packages.db.session import get_async_session, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, AnalysisRun, File, Symbol
from services.worker.ingestion_worker import (
    validate_github_url, parse_repo_owner_name, run_ingestion_pipeline, EventBroker
)
from apps.api.app.schemas import (
    IngestRepositoryRequest, IngestRepositoryResponse, RepositorySummarySchema, AnalysisRunSchema
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
        lang_breakdown: Dict[str, int] = {}

        if latest_ver:
            latest_status = latest_ver.status

            # Files & LOC
            file_stmt = select(File).where(File.repository_version_id == latest_ver.id)
            file_res = await db.execute(file_stmt)
            files = file_res.scalars().all()

            total_files = len(files)
            total_loc = sum(f.line_count for f in files)

            for f in files:
                lang_breakdown[f.language] = lang_breakdown.get(f.language, 0) + 1

            # Symbol count
            if files:
                file_ids = [f.id for f in files]
                sym_stmt = select(func.count(Symbol.id)).where(Symbol.file_id.in_(file_ids))
                sym_res = await db.execute(sym_stmt)
                total_symbols = sym_res.scalar() or 0

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
                language_breakdown=lang_breakdown,
            )
        )

    return summaries

@router.get("/{id}")
async def get_repository_detail(id: str, db: AsyncSession = Depends(get_async_session)):
    """Get detailed file tree, symbols, and latest analysis status for a repository."""
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

        # Files and Symbols
        file_stmt = select(File).where(File.repository_version_id == latest_ver.id)
        file_res = await db.execute(file_stmt)
        files = file_res.scalars().all()

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
        "latest_analysis_run": analysis_run_data,
        "files": files_list,
    }

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

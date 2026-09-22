import os
import shutil
import tempfile
import hashlib
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Callable, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.models import Repository, RepositoryVersion, AnalysisRun, File, Symbol, Dependency
from packages.code_intel.file_filter import scan_repository_files
from packages.code_intel.parsers.registry import parser_registry
from packages.code_intel.graph.builder import DependencyGraphBuilder
from packages.code_intel.models import ExtractedFileContext

class EventBroker:
    """Pub/Sub Event Broker for real-time progress updates."""
    _listeners: Dict[str, List[Callable[[dict], None]]] = {}

    @classmethod
    def subscribe(cls, analysis_run_id: str, listener: Callable[[dict], None]):
        if analysis_run_id not in cls._listeners:
            cls._listeners[analysis_run_id] = []
        cls._listeners[analysis_run_id].append(listener)

    @classmethod
    def unsubscribe(cls, analysis_run_id: str, listener: Callable[[dict], None]):
        if analysis_run_id in cls._listeners:
            cls._listeners[analysis_run_id] = [l for l in cls._listeners[analysis_run_id] if l != listener]

    @classmethod
    def publish(cls, analysis_run_id: str, data: dict):
        if analysis_run_id in cls._listeners:
            for listener in cls._listeners[analysis_run_id]:
                try:
                    listener(data)
                except Exception:
                    pass

def validate_github_url(url: str) -> bool:
    """Validate that URL points safely to a public Git remote."""
    cleaned = url.strip().lower()
    return cleaned.startswith("https://github.com/") or cleaned.startswith("https://gitlab.com/")

async def emit_progress(
    session: AsyncSession,
    analysis_run: AnalysisRun,
    step: str,
    progress: float,
    details: str
):
    """Update DB record and broadcast live progress event via EventBroker."""
    analysis_run.current_step = step
    analysis_run.progress_percentage = progress
    analysis_run.step_details = details
    await session.commit()

    event_payload = {
        "analysis_run_id": analysis_run.id,
        "step": step,
        "progress": progress,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    EventBroker.publish(analysis_run.id, event_payload)

def parse_repo_owner_name(github_url: str) -> tuple[str, str]:
    """Extract owner and repo name from GitHub URL."""
    cleaned = github_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "unknown", "repo"

async def run_ingestion_pipeline(analysis_run_id: str, session: AsyncSession) -> None:
    """
    Main asynchronous repository ingestion worker execution loop.
    Stages: CLONING -> FILTERING -> PARSING (Tree-sitter) -> GRAPH_BUILDING -> FINALIZING -> COMPLETED.
    """
    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_run_id)
    )
    result = await session.execute(stmt)
    analysis_run = result.scalar_one_or_none()
    if not analysis_run:
        return

    # Fetch repository & version
    version_stmt = select(RepositoryVersion).where(RepositoryVersion.id == analysis_run.repository_version_id)
    ver_res = await session.execute(version_stmt)
    version = ver_res.scalar_one()

    repo_stmt = select(Repository).where(Repository.id == version.repository_id)
    repo_res = await session.execute(repo_stmt)
    repo = repo_res.scalar_one()

    analysis_run.status = "IN_PROGRESS"
    analysis_run.started_at = datetime.now(timezone.utc)
    await emit_progress(session, analysis_run, "CLONING", 10.0, f"Cloning repository {repo.github_url}...")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"repolens_{analysis_run_id}_"))

    try:
        # Step 1: Shallow Git clone into isolated sandbox
        clone_cmd = [
            "git", "clone", "--depth", "1", "--single-branch",
            "--branch", version.branch, repo.github_url, str(temp_dir)
        ]

        proc = await asyncio.create_subprocess_exec(
            *clone_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode('utf-8', errors='ignore') or "Git clone failed"
            analysis_run.status = "FAILED"
            analysis_run.error_log = err_msg
            await emit_progress(session, analysis_run, "FAILED", 0.0, f"Clone error: {err_msg[:200]}")
            return

        # Fetch actual commit hash
        hash_cmd = ["git", "rev-parse", "HEAD"]
        hash_proc = await asyncio.create_subprocess_exec(
            *hash_cmd,
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out_hash, _ = await hash_proc.communicate()
        if out_hash:
            parsed_commit_hash = out_hash.decode().strip()
            # Clean up any stale previous version with the same commit hash to respect unique constraint
            stale_ver_stmt = select(RepositoryVersion).where(
                RepositoryVersion.repository_id == repo.id,
                RepositoryVersion.commit_hash == parsed_commit_hash,
                RepositoryVersion.id != version.id,
            )
            stale_ver_res = await session.execute(stale_ver_stmt)
            stale_vers = stale_ver_res.scalars().all()
            for sv in stale_vers:
                await session.delete(sv)
            await session.flush()
            version.commit_hash = parsed_commit_hash

        # Step 2: Safe file scanning
        await emit_progress(session, analysis_run, "FILTERING", 25.0, "Scanning files & applying security filters...")
        scanned = scan_repository_files(temp_dir)

        await emit_progress(session, analysis_run, "PARSING", 40.0, f"Discovered {len(scanned)} safe source files. Extracting Tree-sitter AST symbols...")

        total_files = len(scanned)
        file_db_map: Dict[str, str] = {}  # rel_path -> file_id
        symbol_db_map: Dict[str, str] = {}  # fqn -> symbol_id
        extracted_contexts: List[ExtractedFileContext] = []
        total_symbols_count = 0

        # Step 3: Parse each file with Tree-sitter & persist Symbols
        for idx, (rel_path, language, line_count, byte_size) in enumerate(scanned, start=1):
            full_path = temp_dir / rel_path

            try:
                with open(full_path, "rb") as f:
                    code_bytes = f.read()

                sha256_hash = hashlib.sha256(code_bytes).hexdigest()
                path_str = rel_path.as_posix()

                file_rec = File(
                    repository_version_id=version.id,
                    path=path_str,
                    language=language,
                    line_count=line_count,
                    byte_size=byte_size,
                    sha256_hash=sha256_hash,
                )
                session.add(file_rec)
                await session.flush()  # Generate file_rec.id
                file_db_map[path_str] = file_rec.id

                # Tree-sitter AST Extraction
                ctx = parser_registry.parse_file(code_bytes, path_str)
                if ctx:
                    extracted_contexts.append(ctx)
                    for sym in ctx.symbols:
                        sym_rec = Symbol(
                            file_id=file_rec.id,
                            name=sym.name,
                            fully_qualified_name=sym.fully_qualified_name,
                            kind=sym.kind,
                            start_line=sym.start_line,
                            end_line=sym.end_line,
                            start_col=sym.start_col,
                            end_col=sym.end_col,
                            signature=sym.signature,
                            docstring=sym.docstring,
                        )
                        session.add(sym_rec)
                        await session.flush()
                        symbol_db_map[sym.fully_qualified_name] = sym_rec.id
                        total_symbols_count += 1

            except Exception:
                continue

            if idx % 10 == 0 or idx == total_files:
                prog = 40.0 + (idx / max(total_files, 1)) * 25.0
                await emit_progress(
                    session,
                    analysis_run,
                    "PARSING",
                    round(prog, 1),
                    f"Parsed {idx}/{total_files} files with Tree-sitter ({total_symbols_count} symbols extracted)"
                )

        # Step 4: Construct Dependency Call-Graph & Persist Graph Edges
        await emit_progress(
            session,
            analysis_run,
            "GRAPH_BUILDING",
            70.0,
            f"Resolving dependency call-graph across {total_symbols_count} symbols..."
        )

        graph_builder = DependencyGraphBuilder(extracted_contexts)
        resolved_dependencies = graph_builder.resolve_dependencies(
            symbol_db_map=symbol_db_map,
            file_db_map=file_db_map,
        )

        persisted_edge_count = 0
        for dep in resolved_dependencies:
            if dep.caller_symbol_id and dep.callee_symbol_id:
                dep_rec = Dependency(
                    caller_symbol_id=dep.caller_symbol_id,
                    callee_symbol_id=dep.callee_symbol_id,
                    dependency_type=dep.dependency_type,
                    file_id=dep.file_id or list(file_db_map.values())[0],
                    line_number=dep.line_number,
                )
                session.add(dep_rec)
                persisted_edge_count += 1

        await session.flush()

        await emit_progress(
            session,
            analysis_run,
            "GRAPH_BUILDING",
            75.0,
            f"Resolved {persisted_edge_count} dependency relationships (calls, inheritance, imports, instantiations)"
        )

        # Step 5: AST Code Chunking & Vector Embedding Generation
        await emit_progress(
            session,
            analysis_run,
            "EMBEDDING",
            78.0,
            f"Chunking {total_files} files with ASTAwareChunker..."
        )

        from packages.code_intel.chunking.chunker import ASTAwareChunker
        from packages.code_intel.embeddings.provider import get_embedding_provider
        from packages.db.models import CodeChunk

        embedding_provider = get_embedding_provider()
        version.embedding_model = embedding_provider.model_name
        version.embedding_dimension = embedding_provider.dimension

        all_extracted_chunks = []
        ctx_map = {c.file_path: c for c in extracted_contexts}

        for rel_path, language, line_count, byte_size in scanned:
            path_str = rel_path.as_posix()
            full_path = temp_dir / rel_path
            try:
                code_text = full_path.read_text(encoding="utf-8", errors="ignore")
                file_ctx = ctx_map.get(path_str)
                f_chunks = ASTAwareChunker.chunk_file(
                    code_str=code_text,
                    file_path=path_str,
                    language=language,
                    context=file_ctx,
                    symbol_db_map=symbol_db_map,
                )
                all_extracted_chunks.extend(f_chunks)
            except Exception:
                continue

        total_chunks = len(all_extracted_chunks)
        await emit_progress(
            session,
            analysis_run,
            "EMBEDDING",
            82.0,
            f"Generated {total_chunks} semantic code chunks. Generating {embedding_provider.model_name} embeddings..."
        )

        # Generate embeddings in formatted batches
        doc_tuples = [(c.metadata_title, c.content) for c in all_extracted_chunks]
        embeddings = embedding_provider.embed_documents(doc_tuples)

        # Bulk persist CodeChunk records
        for c_idx, chunk in enumerate(all_extracted_chunks):
            f_id = file_db_map.get(chunk.file_path)
            if not f_id:
                continue

            chunk_emb = embeddings[c_idx] if c_idx < len(embeddings) else None
            chunk_rec = CodeChunk(
                file_id=f_id,
                symbol_id=chunk.symbol_id,
                symbol_fqn=chunk.symbol_fqn,
                language=chunk.language,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding_model=embedding_provider.model_name,
                embedding_dimension=embedding_provider.dimension,
                embedding=chunk_emb,
            )
            session.add(chunk_rec)

        await session.flush()

        await emit_progress(
            session,
            analysis_run,
            "EMBEDDING",
            90.0,
            f"Indexed {total_chunks} vector embeddings ({embedding_provider.model_name}, dim {embedding_provider.dimension})"
        )

        # Step 6: Finalize and complete
        await emit_progress(session, analysis_run, "FINALIZING", 95.0, "Persisting graph & vector metadata...")

        version.status = "COMPLETED"
        version.processed_at = datetime.now(timezone.utc)
        analysis_run.status = "COMPLETED"
        analysis_run.completed_at = datetime.now(timezone.utc)

        await emit_progress(
            session,
            analysis_run,
            "COMPLETED",
            100.0,
            f"Successfully analyzed repository ({total_files} files, {total_symbols_count} symbols, {persisted_edge_count} edges, {total_chunks} chunks)"
        )

    except Exception as exc:
        analysis_run.status = "FAILED"
        analysis_run.error_log = str(exc)
        await emit_progress(session, analysis_run, "FAILED", 0.0, f"Error: {str(exc)}")

    finally:
        # Clean up temporary sandbox directory safely
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

async def reindex_repository_version(version_id: str, session: AsyncSession) -> int:
    """
    Re-index all CodeChunks for an existing repository version with active embedding provider.
    Used when embedding model or dimensionality changes.
    """
    from packages.code_intel.embeddings.provider import get_embedding_provider
    from packages.db.models import CodeChunk, RepositoryVersion, File

    provider = get_embedding_provider()

    ver_stmt = select(RepositoryVersion).where(RepositoryVersion.id == version_id)
    ver_res = await session.execute(ver_stmt)
    version = ver_res.scalar_one_or_none()
    if not version:
        return 0

    file_stmt = select(File).where(File.repository_version_id == version_id)
    file_res = await session.execute(file_stmt)
    files = file_res.scalars().all()
    file_ids = [f.id for f in files]
    if not file_ids:
        return 0

    chunk_stmt = select(CodeChunk).where(CodeChunk.file_id.in_(file_ids))
    chunk_res = await session.execute(chunk_stmt)
    chunks = chunk_res.scalars().all()
    if not chunks:
        return 0

    # Build doc items
    doc_items = [(f"Chunk {c.id} | {c.symbol_fqn or 'code'}", c.content) for c in chunks]
    embeddings = provider.embed_documents(doc_items)

    for idx, c in enumerate(chunks):
        if idx < len(embeddings):
            c.embedding = embeddings[idx]
            c.embedding_model = provider.model_name
            c.embedding_dimension = provider.dimension

    version.embedding_model = provider.model_name
    version.embedding_dimension = provider.dimension
    await session.commit()
    return len(chunks)


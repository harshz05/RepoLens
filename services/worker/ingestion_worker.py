import os
import shutil
import tempfile
import hashlib
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.models import Repository, RepositoryVersion, AnalysisRun, File, Symbol
from packages.code_intel.file_filter import scan_repository_files
from packages.code_intel.symbol_extractor import extract_file_symbols

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
    100% Real execution: Git clone -> File Filtering -> Symbol Extraction -> DB Persist.
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
            version.commit_hash = out_hash.decode().strip()

        # Step 2: Safe file scanning
        await emit_progress(session, analysis_run, "FILTERING", 30.0, "Scanning files & applying security filters...")
        scanned = scan_repository_files(temp_dir)

        await emit_progress(session, analysis_run, "PARSING", 50.0, f"Discovered {len(scanned)} safe source files. Extracting AST symbols...")

        total_files = len(scanned)
        file_records: List[File] = []
        symbol_records: List[Symbol] = []

        for idx, (rel_path, language, line_count, byte_size) in enumerate(scanned, start=1):
            full_path = temp_dir / rel_path

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    code_content = f.read()

                sha256_hash = hashlib.sha256(code_content.encode("utf-8")).hexdigest()
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

                extracted = extract_file_symbols(code_content, path_str, language)
                for sym in extracted:
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
                    symbol_records.append(sym_rec)
                    session.add(sym_rec)

            except Exception as e:
                continue

            if idx % 10 == 0 or idx == total_files:
                prog = 50.0 + (idx / max(total_files, 1)) * 40.0
                await emit_progress(session, analysis_run, "PARSING", round(prog, 1), f"Parsed {idx}/{total_files} files ({len(symbol_records)} symbols extracted)")

        await emit_progress(session, analysis_run, "FINALIZING", 95.0, "Persisting AST symbol metadata & completing run...")

        version.status = "COMPLETED"
        version.processed_at = datetime.now(timezone.utc)
        analysis_run.status = "COMPLETED"
        analysis_run.completed_at = datetime.now(timezone.utc)

        await emit_progress(
            session,
            analysis_run,
            "COMPLETED",
            100.0,
            f"Successfully analyzed repository ({total_files} files, {len(symbol_records)} symbols)"
        )

    except Exception as exc:
        analysis_run.status = "FAILED"
        analysis_run.error_log = str(exc)
        await emit_progress(session, analysis_run, "FAILED", 0.0, f"Error: {str(exc)}")

    finally:
        # Clean up temporary sandbox directory safely
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

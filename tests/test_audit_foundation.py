"""
Sprint 1 — audit foundation tests.

Covers:
  * route extraction from decorator text
  * Python parser attaches route/http_method metadata to api_endpoint symbols
  * ingestion persists original source (file_contents) and symbol metadata
  * audit pipeline analyses the ORIGINAL source (exact line numbers, no duplicates)
  * audit fails clearly for versions ingested without stored source
"""
import subprocess
import tempfile
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, delete

from packages.code_intel.parsers.route_utils import extract_route_info
from packages.code_intel.parsers.registry import parser_registry
from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import (
    Repository,
    RepositoryVersion,
    AnalysisRun,
    AuditRun,
    FileContent,
    File,
    Symbol,
    SecurityFinding,
)
from services.worker.ingestion_worker import run_ingestion_pipeline
from services.worker.audit_worker import run_audit_pipeline


# ---------------------------------------------------------------- route utils

@pytest.mark.parametrize(
    "decorator, expected",
    [
        ('@router.post("/ingest", response_model=X)', {"route": "/ingest", "http_method": "POST"}),
        ("@app.get('/')", {"route": "/", "http_method": "GET"}),
        ('@app.delete(path="/admin/x")', {"route": "/admin/x", "http_method": "DELETE"}),
        ('@bp.route("/x", methods=["POST", "put"])', {"route": "/x", "http_method": "POST,PUT"}),
        ('@bp.route("/y")', {"route": "/y", "http_method": "GET"}),
        ("@staticmethod", None),
        ("", None),
    ],
)
def test_extract_route_info(decorator, expected):
    assert extract_route_info(decorator) == expected


def test_python_parser_sets_route_metadata():
    code = b'''
from fastapi import FastAPI
app = FastAPI()

@app.post("/items")
async def create_item(name: str):
    return name

def plain():
    return 1
'''
    ctx = parser_registry.parse_file(code, "app.py")
    by_name = {s.name: s for s in ctx.symbols}
    assert by_name["create_item"].kind == "api_endpoint"
    assert by_name["create_item"].metadata["route"] == "/items"
    assert by_name["create_item"].metadata["http_method"] == "POST"
    assert by_name["plain"].kind == "function"
    assert "route" not in by_name["plain"].metadata


# ------------------------------------------------------- end-to-end fixtures

APP_PY = '''import subprocess
from fastapi import FastAPI

app = FastAPI()


@app.post("/run")
def run_cmd(cmd: str):
    return helper(cmd)


@app.delete("/admin/purge")
def purge_everything():
    return {"ok": True}


def helper(cmd):
    subprocess.run(f"echo {cmd}", shell=True)
    return eval(cmd)
'''


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t.t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture
def local_git_repo():
    d = Path(tempfile.mkdtemp(prefix="repolens_fixture_"))
    # write_bytes: no platform newline translation (Windows would otherwise turn \n into \r\n)
    (d / "app.py").write_bytes(APP_PY.encode("utf-8"))
    _git(["init", "-b", "main"], d)
    _git(["add", "."], d)
    _git(["commit", "-m", "init"], d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


async def _ingest(repo_path: Path) -> str:
    """Run the real ingestion pipeline against a local git repo; returns version id."""
    await init_db()
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"file://{repo_path}",
            owner=f"local_{suffix}",
            name=f"fixture-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()
        ver = RepositoryVersion(
            repository_id=repo.id, commit_hash=f"pending-{suffix}", branch="main", status="PENDING"
        )
        session.add(ver)
        await session.flush()
        run = AnalysisRun(repository_version_id=ver.id, status="QUEUED")
        session.add(run)
        await session.commit()
        version_id, run_id = ver.id, run.id

    async with AsyncSessionLocal() as session:
        await run_ingestion_pipeline(run_id, session)
    return version_id


async def _audit(version_id: str) -> str:
    async with AsyncSessionLocal() as session:
        audit = AuditRun(repository_version_id=version_id, status="QUEUED")
        session.add(audit)
        await session.commit()
        audit_id = audit.id
    async with AsyncSessionLocal() as session:
        await run_audit_pipeline(audit_id, session, enable_ai_review=False)
    return audit_id


def _line_of(needle: str) -> int:
    for i, line in enumerate(APP_PY.splitlines(), start=1):
        if needle in line:
            return i
    raise AssertionError(needle)


# ------------------------------------------------------------------- tests

@pytest.mark.asyncio
async def test_ingestion_persists_source_and_symbol_metadata(local_git_repo):
    version_id = await _ingest(local_git_repo)

    async with AsyncSessionLocal() as session:
        files = (await session.execute(select(File).where(File.repository_version_id == version_id))).scalars().all()
        assert [f.path for f in files] == ["app.py"]

        content = (await session.execute(select(FileContent).where(FileContent.file_id == files[0].id))).scalar_one()
        # Original source, no chunk headers. Newlines normalised because git on Windows may check out CRLF.
        assert content.content.replace("\r\n", "\n") == APP_PY

        syms = (await session.execute(select(Symbol).where(Symbol.file_id == files[0].id))).scalars().all()
        endpoint = next(s for s in syms if s.name == "run_cmd")
        assert endpoint.kind == "api_endpoint"
        assert '"/run"' in (endpoint.metadata_json or "")


@pytest.mark.asyncio
async def test_audit_uses_original_source_line_numbers(local_git_repo):
    version_id = await _ingest(local_git_repo)
    audit_id = await _audit(version_id)

    async with AsyncSessionLocal() as session:
        audit = (await session.execute(select(AuditRun).where(AuditRun.id == audit_id))).scalar_one()
        assert audit.status == "COMPLETED", audit.error_log

        findings = (await session.execute(
            select(SecurityFinding).where(SecurityFinding.audit_run_id == audit_id)
        )).scalars().all()

    by_rule = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, []).append(f)

    # eval() finding points at the real line in the original file
    eval_lines = {f.start_line for f in by_rule.get("SEC-002", [])}
    assert _line_of("return eval(cmd)") in eval_lines

    # subprocess shell=True finding points at the real line
    sub_lines = {f.start_line for f in by_rule.get("SEC-003", [])}
    assert _line_of("subprocess.run(") in sub_lines

    # No duplicate (rule, line) pairs (chunk overlap / nesting used to duplicate)
    pairs = [(f.rule_id, f.start_line) for f in findings]
    assert len(pairs) == len(set(pairs))

    # Reachability: /run -> helper -> sink is found through the call graph
    reachable = [f for f in findings if f.graph_reachability_path]
    assert reachable, "expected at least one finding reachable from an API entrypoint"
    assert any("run_cmd" in f.graph_reachability_path for f in reachable)

    # SEC-010: route metadata now survives persistence, so the unprotected admin route is flagged
    assert any(f.rule_id == "SEC-010" for f in findings)


@pytest.mark.asyncio
async def test_audit_fails_clearly_without_stored_source(local_git_repo):
    version_id = await _ingest(local_git_repo)

    # Simulate a version ingested before file_contents existed
    async with AsyncSessionLocal() as session:
        file_ids = [f.id for f in (await session.execute(
            select(File).where(File.repository_version_id == version_id))).scalars().all()]
        await session.execute(delete(FileContent).where(FileContent.file_id.in_(file_ids)))
        await session.commit()

    audit_id = await _audit(version_id)
    async with AsyncSessionLocal() as session:
        audit = (await session.execute(select(AuditRun).where(AuditRun.id == audit_id))).scalar_one()
    assert audit.status == "FAILED"
    assert "Re-ingest" in (audit.error_log or "")
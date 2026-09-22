import tempfile
import shutil
import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, AnalysisRun, File, Symbol, Dependency
from packages.code_intel.parsers.registry import parser_registry
from packages.code_intel.graph.builder import DependencyGraphBuilder
from services.worker.ingestion_worker import scan_repository_files

@pytest.mark.asyncio
async def test_milestone2_full_pipeline_verification():
    await init_db()

    # 1. Create a simulated realistic repository structure in temporary directory
    temp_repo = Path(tempfile.mkdtemp(prefix="repolens_m2_verify_"))
    try:
        (temp_repo / "models").mkdir()
        (temp_repo / "services").mkdir()
        (temp_repo / "api").mkdir()
        (temp_repo / "frontend").mkdir()

        # models/user.py
        (temp_repo / "models" / "user.py").write_text("""
class BaseEntity:
    def get_id(self):
        return '1'

class User(BaseEntity):
    '''User database entity model.'''
    def __init__(self, username: str):
        self.username = username

    def format_name(self) -> str:
        '''Format user name.'''
        return self.username.strip().title()
""", encoding="utf-8")

        # services/auth_service.py
        (temp_repo / "services" / "auth_service.py").write_text("""
from models.user import User

class AuthService:
    '''Authentication business service.'''
    def authenticate(self, username: str) -> User:
        user = User(username)
        formatted = user.format_name()
        return user
""", encoding="utf-8")

        # api/auth_routes.py
        (temp_repo / "api" / "auth_routes.py").write_text("""
from fastapi import APIRouter
from services.auth_service import AuthService

router = APIRouter()

@router.post('/login')
async def login_endpoint(username: str):
    '''Login endpoint route.'''
    service = AuthService()
    return service.authenticate(username)
""", encoding="utf-8")

        # frontend/App.tsx
        (temp_repo / "frontend" / "App.tsx").write_text("""
import React, { useState } from 'react';

export interface AuthState {
    token: string;
}

export function useAuth() {
    const [token, setToken] = useState<string>('');
    return token;
}

export const AuthComponent = () => {
    const auth = useAuth();
    return <div className="auth">{auth}</div>;
};
""", encoding="utf-8")

        # 2. Verify File Scanning & Filtering
        scanned = scan_repository_files(temp_repo)
        scanned_paths = [p.as_posix() for p, lang, lines, size in scanned]

        assert len(scanned) == 4
        assert "models/user.py" in scanned_paths
        assert "services/auth_service.py" in scanned_paths
        assert "api/auth_routes.py" in scanned_paths
        assert "frontend/App.tsx" in scanned_paths

        # 3. Verify Tree-sitter Parsing
        contexts = []
        for rel_path, lang, lines, size in scanned:
            full_p = temp_repo / rel_path
            code_bytes = full_p.read_bytes()
            ctx = parser_registry.parse_file(code_bytes, rel_path.as_posix())
            assert ctx is not None
            contexts.append(ctx)

        total_extracted_symbols = sum(len(c.symbols) for c in contexts)
        assert total_extracted_symbols >= 9

        # 4. Verify Dependency Resolution
        graph_builder = DependencyGraphBuilder(contexts)
        deps = graph_builder.resolve_dependencies()

        assert len(deps) >= 4

        dep_types = {d.dependency_type for d in deps}
        assert "inheritance" in dep_types  # User inherits BaseEntity
        assert "call" in dep_types or "instantiates" in dep_types  # AuthService calls User, login calls AuthService

        # Verify inheritance edge
        inh_dep = next(d for d in deps if d.dependency_type == "inheritance")
        assert "User" in inh_dep.caller_fqn
        assert "BaseEntity" in inh_dep.callee_fqn

        # 5. Verify Database Persistence
        import uuid
        suffix = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as session:
            repo = Repository(
                github_url=f"https://github.com/repolens/m2-verify-{suffix}",
                owner=f"repolens_{suffix}",
                name=f"m2-verify-{suffix}",
                default_branch="main",
            )
            session.add(repo)
            await session.flush()

            ver = RepositoryVersion(
                repository_id=repo.id,
                commit_hash="deadbeef123",
                branch="main",
                status="COMPLETED",
            )
            session.add(ver)
            await session.flush()

            file_db_map = {}
            symbol_db_map = {}

            for ctx in contexts:
                f_rec = File(
                    repository_version_id=ver.id,
                    path=ctx.file_path,
                    language=ctx.language,
                    line_count=20,
                    byte_size=500,
                    sha256_hash="test_hash",
                )
                session.add(f_rec)
                await session.flush()
                file_db_map[ctx.file_path] = f_rec.id

                for s in ctx.symbols:
                    s_rec = Symbol(
                        file_id=f_rec.id,
                        name=s.name,
                        fully_qualified_name=s.fully_qualified_name,
                        kind=s.kind,
                        start_line=s.start_line,
                        end_line=s.end_line,
                        start_col=s.start_col,
                        end_col=s.end_col,
                        signature=s.signature,
                        docstring=s.docstring,
                    )
                    session.add(s_rec)
                    await session.flush()
                    symbol_db_map[s.fully_qualified_name] = s_rec.id

            # Persist resolved dependencies
            persisted_deps = graph_builder.resolve_dependencies(
                symbol_db_map=symbol_db_map,
                file_db_map=file_db_map,
            )

            persisted_count = 0
            for d in persisted_deps:
                if d.caller_symbol_id and d.callee_symbol_id:
                    d_rec = Dependency(
                        caller_symbol_id=d.caller_symbol_id,
                        callee_symbol_id=d.callee_symbol_id,
                        dependency_type=d.dependency_type,
                        file_id=d.file_id or list(file_db_map.values())[0],
                        line_number=d.line_number,
                    )
                    session.add(d_rec)
                    persisted_count += 1

            await session.commit()
            assert persisted_count >= 4

            # Verify relational querying
            res = await session.execute(select(func.count(Dependency.id)))
            total_in_db = res.scalar()
            assert total_in_db >= 4

    finally:
        shutil.rmtree(temp_repo, ignore_errors=True)

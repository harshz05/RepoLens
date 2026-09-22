import tempfile
import shutil
import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from packages.db.session import init_db, AsyncSessionLocal
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
)
from packages.code_intel.parsers.registry import parser_registry
from packages.code_intel.graph.builder import DependencyGraphBuilder
from packages.code_intel.chunking.chunker import ASTAwareChunker
from packages.code_intel.embeddings.provider import get_embedding_provider
from packages.code_intel.retrieval.hybrid_engine import HybridRetrievalEngine
from packages.code_intel.rag.service import CodebaseRAGService
from services.worker.ingestion_worker import scan_repository_files

@pytest.mark.asyncio
async def test_milestone3_full_pipeline_verification():
    await init_db()

    # 1. Create a simulated realistic multi-file codebase in temporary directory
    temp_repo = Path(tempfile.mkdtemp(prefix="repolens_m3_verify_"))
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
    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email

    def format_profile(self) -> str:
        '''Format user profile.'''
        return f"{self.username.strip().title()} <{self.email}>"
""", encoding="utf-8")

        # services/auth_service.py
        (temp_repo / "services" / "auth_service.py").write_text("""
from models.user import User

class AuthService:
    '''Authentication business service with JWT token verification.'''
    def authenticate(self, username: str, token: str) -> User:
        '''Authenticate user credentials and token.'''
        user = User(username, f"{username}@example.com")
        formatted = user.format_profile()
        return user
""", encoding="utf-8")

        # api/auth_routes.py
        (temp_repo / "api" / "auth_routes.py").write_text("""
from fastapi import APIRouter
from services.auth_service import AuthService

router = APIRouter()

@router.post('/login')
async def login_endpoint(username: str, token: str):
    '''Login endpoint route handling client authentication.'''
    service = AuthService()
    return service.authenticate(username, token)
""", encoding="utf-8")

        # frontend/AuthDashboard.tsx
        (temp_repo / "frontend" / "AuthDashboard.tsx").write_text("""
import React, { useState } from 'react';

export interface UserSession {
    token: string;
    username: string;
}

export function useAuthSession() {
    const [session, setSession] = useState<UserSession | null>(null);
    return session;
}

export const AuthDashboard = () => {
    const session = useAuthSession();
    return <div className="auth-dash">{session?.username}</div>;
};
""", encoding="utf-8")

        # 2. File Filtering & Tree-sitter Parsing
        scanned = scan_repository_files(temp_repo)
        assert len(scanned) == 4

        extracted_contexts = []
        for rel_path, lang, lines, size in scanned:
            full_p = temp_repo / rel_path
            code_bytes = full_p.read_bytes()
            ctx = parser_registry.parse_file(code_bytes, rel_path.as_posix())
            assert ctx is not None
            extracted_contexts.append(ctx)

        # 3. Seed Database with Repository & Files
        import uuid
        suffix = uuid.uuid4().hex[:8]
        provider = get_embedding_provider(dimension=768)

        async with AsyncSessionLocal() as session:
            repo = Repository(
                github_url=f"https://github.com/repolens/m3-verify-{suffix}",
                owner=f"repolens_{suffix}",
                name=f"m3-verify-{suffix}",
                default_branch="main",
            )
            session.add(repo)
            await session.flush()

            ver = RepositoryVersion(
                repository_id=repo.id,
                commit_hash="m3commit12345",
                branch="main",
                status="COMPLETED",
                embedding_model=provider.model_name,
                embedding_dimension=provider.dimension,
            )
            session.add(ver)
            await session.flush()

            file_db_map = {}
            symbol_db_map = {}

            for ctx in extracted_contexts:
                full_p = temp_repo / ctx.file_path
                code_bytes = full_p.read_bytes()
                f_rec = File(
                    repository_version_id=ver.id,
                    path=ctx.file_path,
                    language=ctx.language,
                    line_count=len(code_bytes.splitlines()),
                    byte_size=len(code_bytes),
                    sha256_hash="sha256m3test",
                )
                session.add(f_rec)
                await session.flush()
                file_db_map[ctx.file_path] = f_rec.id

                for sym in ctx.symbols:
                    s_rec = Symbol(
                        file_id=f_rec.id,
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
                    session.add(s_rec)
                    await session.flush()
                    symbol_db_map[sym.fully_qualified_name] = s_rec.id

            # 4. Resolve Dependency Call-Graph
            graph_builder = DependencyGraphBuilder(extracted_contexts)
            resolved_deps = graph_builder.resolve_dependencies(
                symbol_db_map=symbol_db_map,
                file_db_map=file_db_map,
            )

            for dep in resolved_deps:
                if dep.caller_symbol_id and dep.callee_symbol_id:
                    d_rec = Dependency(
                        caller_symbol_id=dep.caller_symbol_id,
                        callee_symbol_id=dep.callee_symbol_id,
                        dependency_type=dep.dependency_type,
                        file_id=dep.file_id or list(file_db_map.values())[0],
                        line_number=dep.line_number,
                    )
                    session.add(d_rec)
            await session.flush()

            # 5. AST-Aware Code Chunking & Vector Persistence
            all_chunks = []
            ctx_map = {c.file_path: c for c in extracted_contexts}

            for rel_path, lang, lines, size in scanned:
                p_str = rel_path.as_posix()
                full_p = temp_repo / rel_path
                code_text = full_p.read_text(encoding="utf-8")
                f_ctx = ctx_map.get(p_str)
                f_chunks = ASTAwareChunker.chunk_file(
                    code_str=code_text,
                    file_path=p_str,
                    language=lang,
                    context=f_ctx,
                    symbol_db_map=symbol_db_map,
                )
                all_chunks.extend(f_chunks)

            assert len(all_chunks) >= 4

            # Generate formatted batch embeddings
            doc_items = [(c.metadata_title, c.content) for c in all_chunks]
            embeddings = provider.embed_documents(doc_items)
            assert len(embeddings) == len(all_chunks)

            for idx, c in enumerate(all_chunks):
                chunk_rec = CodeChunk(
                    file_id=file_db_map[c.file_path],
                    symbol_id=c.symbol_id,
                    symbol_fqn=c.symbol_fqn,
                    language=c.language,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    content=c.content,
                    token_count=c.token_count,
                    embedding_model=provider.model_name,
                    embedding_dimension=provider.dimension,
                    embedding=embeddings[idx],
                )
                session.add(chunk_rec)

            await session.commit()

            # 6. Verify Exact Search
            exact_res = await HybridRetrievalEngine.retrieve(
                session=session,
                repository_version_id=ver.id,
                query="AuthService",
                mode="exact",
                provider=provider,
            )
            assert exact_res.total_results >= 1
            assert any("AuthService" in (c.symbol_fqn or "") for c in exact_res.chunks)

            # 7. Verify Semantic Search
            sem_res = await HybridRetrievalEngine.retrieve(
                session=session,
                repository_version_id=ver.id,
                query="user authentication and token verification",
                mode="semantic",
                provider=provider,
            )
            assert sem_res.total_results >= 1

            # 8. Verify Hybrid RRF Search
            hybrid_res = await HybridRetrievalEngine.retrieve(
                session=session,
                repository_version_id=ver.id,
                query="AuthService authenticate user",
                mode="hybrid",
                provider=provider,
                expand_graph_context=True,
            )
            assert hybrid_res.total_results >= 1
            top_chunk = hybrid_res.chunks[0]
            assert top_chunk.graph_context is not None

            # 9. Verify Grounded RAG Chat & Citation Validation
            chat_result = await CodebaseRAGService.chat(
                session=session,
                repository_id=repo.id,
                message="How is user authentication handled in the codebase?",
            )

            assert "response" in chat_result
            assert "citations" in chat_result
            assert len(chat_result["citations"]) >= 1

            # Check that citation is saved in DB
            cit_data = chat_result["citations"][0]
            assert "services/auth_service.py" in cit_data["file_path"] or "api/auth_routes.py" in cit_data["file_path"]

            # Verify persisted chat session in DB
            sess_stmt = select(ChatSession).where(ChatSession.repository_id == repo.id)
            sess_res = await session.execute(sess_stmt)
            saved_sess = sess_res.scalar_one()
            assert len(saved_sess.messages) == 2  # user + assistant

    finally:
        if temp_repo.exists():
            shutil.rmtree(temp_repo, ignore_errors=True)

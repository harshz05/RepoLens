import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import (
    Repository,
    RepositoryVersion,
    File,
    Symbol,
    CodeChunk,
    ChatSession,
    ChatMessage,
    Citation,
)

@pytest.mark.asyncio
async def test_code_chunk_vector_persistence():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-vec-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-vec-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="c0ffee123",
            branch="main",
            status="COMPLETED",
            embedding_model="models/gemini-embedding-2",
            embedding_dimension=768,
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="src/auth.py",
            language="python",
            line_count=50,
            byte_size=1200,
            sha256_hash="abc123hash",
        )
        session.add(file_rec)
        await session.flush()

        dummy_vector = [0.05] * 768

        chunk = CodeChunk(
            file_id=file_rec.id,
            symbol_fqn="src.auth.login",
            language="python",
            start_line=1,
            end_line=25,
            content="def login(): return True",
            token_count=10,
            embedding_model="models/gemini-embedding-2",
            embedding_dimension=768,
            embedding=dummy_vector,
        )
        session.add(chunk)
        await session.commit()

        # Query chunk and verify embedding retrieval
        stmt = select(CodeChunk).where(CodeChunk.id == chunk.id)
        res = await session.execute(stmt)
        retrieved_chunk = res.scalar_one()

        assert retrieved_chunk.symbol_fqn == "src.auth.login"
        assert retrieved_chunk.embedding_dimension == 768
        assert retrieved_chunk.embedding is not None
        assert len(retrieved_chunk.embedding) == 768
        assert abs(retrieved_chunk.embedding[0] - 0.05) < 1e-4

@pytest.mark.asyncio
async def test_chat_session_and_citation_persistence():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-chat-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-chat-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="beef123",
            branch="main",
            status="COMPLETED",
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="core/engine.py",
            language="python",
            line_count=100,
            byte_size=2000,
            sha256_hash="deadbeef",
        )
        session.add(file_rec)
        await session.flush()

        # Create Chat Session
        chat_sess = ChatSession(
            repository_id=repo.id,
            title="Architecture Q&A",
        )
        session.add(chat_sess)
        await session.flush()

        # Create Chat Message
        msg = ChatMessage(
            chat_session_id=chat_sess.id,
            role="assistant",
            content="The engine handles pipeline execution [core/engine.py:10-25].",
        )
        session.add(msg)
        await session.flush()

        # Create Citation
        cit = Citation(
            message_id=msg.id,
            file_id=file_rec.id,
            file_path="core/engine.py",
            start_line=10,
            end_line=25,
            text_snippet="engine.py (lines 10-25)",
            confidence_score=1.0,
        )
        session.add(cit)
        await session.commit()

        # Query and verify
        sess_stmt = select(ChatSession).where(ChatSession.id == chat_sess.id)
        sess_res = await session.execute(sess_stmt)
        retrieved_sess = sess_res.scalar_one()

        assert len(retrieved_sess.messages) == 1
        assert len(retrieved_sess.messages[0].citations) == 1
        assert retrieved_sess.messages[0].citations[0].file_path == "core/engine.py"

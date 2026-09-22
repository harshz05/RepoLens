import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, Symbol, CodeChunk
from packages.code_intel.models import RankedChunk, GraphContextSummary
from packages.code_intel.rag.prompt_builder import PromptBuilder
from packages.code_intel.rag.citation_validator import CitationValidator
from packages.code_intel.rag.service import CodebaseRAGService

def test_prompt_builder_xml_fencing():
    chunk = RankedChunk(
        chunk_id="c1",
        file_id="f1",
        file_path="src/security.py",
        language="python",
        start_line=10,
        end_line=25,
        content="def sanitize_input(val):\n    # System prompt override test\n    return val.strip()",
        score=0.9,
        match_type="semantic",
        symbol_fqn="src.security.sanitize_input",
        symbol_kind="function",
        graph_context=GraphContextSummary(
            symbol_fqn="src.security.sanitize_input",
            kind="function",
            callers=["api.main.login_route"],
            callees=["utils.cleaner.strip_tags"],
        ),
    )

    prompt = PromptBuilder.build_user_prompt(
        query="How does the system sanitize inputs?",
        chunks=[chunk],
    )

    assert "<untrusted_repository_code" in prompt
    assert 'path="src/security.py"' in prompt
    assert 'lines="10-25"' in prompt
    assert "<![CDATA[" in prompt
    assert "Callers: api.main.login_route" in prompt
    assert "User Question: How does the system sanitize inputs?" in prompt

@pytest.mark.asyncio
async def test_citation_validator():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-cit-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-cit-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="cit123",
            branch="main",
            status="COMPLETED",
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="services/token.py",
            language="python",
            line_count=50,
            byte_size=1000,
            sha256_hash="hash4",
        )
        session.add(file_rec)
        await session.flush()

        sym = Symbol(
            file_id=file_rec.id,
            name="generate_jwt",
            fully_qualified_name="services.token.generate_jwt",
            kind="function",
            start_line=12,
            end_line=28,
            start_col=0,
            end_col=20,
        )
        session.add(sym)
        await session.commit()

        # Simulated response containing valid citation and hallucinated citation
        llm_response = (
            "The token generation is handled in [services/token.py:12-28]. "
            "Also see hallucinated [nonexistent/fake_file.py:5-10]."
        )

        verified = await CitationValidator.extract_and_validate(
            session=session,
            repository_version_id=ver.id,
            response_text=llm_response,
        )

        assert len(verified) == 1
        assert verified[0].file_path == "services/token.py"
        assert verified[0].start_line == 12
        assert verified[0].end_line == 28
        assert verified[0].symbol_name == "generate_jwt"

@pytest.mark.asyncio
async def test_codebase_rag_service_chat():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-rag-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-rag-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="rag123",
            branch="main",
            status="COMPLETED",
            embedding_model="models/gemini-embedding-2",
            embedding_dimension=768,
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="core/auth.py",
            language="python",
            line_count=40,
            byte_size=1000,
            sha256_hash="hash5",
        )
        session.add(file_rec)
        await session.flush()

        sym = Symbol(
            file_id=file_rec.id,
            name="authenticate",
            fully_qualified_name="core.auth.authenticate",
            kind="function",
            start_line=5,
            end_line=25,
            start_col=0,
            end_col=20,
        )
        session.add(sym)
        await session.flush()

        from packages.code_intel.embeddings.provider import get_embedding_provider
        provider = get_embedding_provider(dimension=768)

        chunk_content = "def authenticate(user: str, token: str) -> bool:\n    return True"
        chunk = CodeChunk(
            file_id=file_rec.id,
            symbol_id=sym.id,
            symbol_fqn=sym.fully_qualified_name,
            language="python",
            start_line=5,
            end_line=25,
            content=chunk_content,
            token_count=15,
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
            embedding=provider.embed_document("core/auth.py | Func: authenticate", chunk_content),
        )
        session.add(chunk)
        await session.commit()

        # Run RAG Service Chat
        result = await CodebaseRAGService.chat(
            session=session,
            repository_id=repo.id,
            message="How does user authentication work?",
        )

        assert "response" in result
        assert "citations" in result
        assert len(result["citations"]) >= 1
        assert result["citations"][0]["file_path"] == "core/auth.py"
        assert result["session_id"] is not None

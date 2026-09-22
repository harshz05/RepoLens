import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, CodeChunk
from packages.code_intel.models import EmbeddingVersionMismatchError
from packages.code_intel.embeddings.provider import DeterministicLocalEmbeddingProvider
from packages.code_intel.retrieval.semantic_search import SemanticSearcher
from services.worker.ingestion_worker import reindex_repository_version

@pytest.mark.asyncio
async def test_embedding_version_mismatch_detection():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-mismatch-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-mismatch-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        # Create version with legacy/outdated embedding model
        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="oldmodel123",
            branch="main",
            status="COMPLETED",
            embedding_model="models/legacy-old-model",
            embedding_dimension=512,
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="src/main.py",
            language="python",
            line_count=20,
            byte_size=500,
            sha256_hash="abc1234",
        )
        session.add(file_rec)
        await session.flush()

        chunk = CodeChunk(
            file_id=file_rec.id,
            symbol_fqn="src.main.run",
            language="python",
            start_line=1,
            end_line=20,
            content="def run(): pass",
            token_count=10,
            embedding_model="models/legacy-old-model",
            embedding_dimension=512,
            embedding=[0.1] * 512,
        )
        session.add(chunk)
        await session.commit()

        # Active provider uses gemini-embedding-2 (dim 768)
        active_provider = DeterministicLocalEmbeddingProvider(model_name="models/gemini-embedding-2", dimension=768)

        # Searching with mismatched active provider must raise EmbeddingVersionMismatchError
        with pytest.raises(EmbeddingVersionMismatchError) as exc_info:
            await SemanticSearcher.search(
                session=session,
                repository_version_id=ver.id,
                query="run application",
                provider=active_provider,
            )

        assert "Re-indexing required" in str(exc_info.value)
        assert exc_info.value.stored_model == "models/legacy-old-model"
        assert exc_info.value.current_model == "models/gemini-embedding-2"

        # Now test re-indexing the version
        reindexed_count = await reindex_repository_version(ver.id, session)
        assert reindexed_count == 1

        # Re-fetch version and verify metadata updated
        ver_stmt = select(RepositoryVersion).where(RepositoryVersion.id == ver.id)
        ver_res = await session.execute(ver_stmt)
        updated_ver = ver_res.scalar_one()

        assert updated_ver.embedding_model == "models/gemini-embedding-2"
        assert updated_ver.embedding_dimension == 768

        # Searching now succeeds without raising error
        results = await SemanticSearcher.search(
            session=session,
            repository_version_id=ver.id,
            query="run application",
            provider=active_provider,
        )
        assert len(results) == 1
        assert results[0].symbol_fqn == "src.main.run"

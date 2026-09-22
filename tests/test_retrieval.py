import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, Symbol, CodeChunk
from packages.code_intel.embeddings.provider import DeterministicLocalEmbeddingProvider
from packages.code_intel.retrieval.exact_matcher import ExactMatcher
from packages.code_intel.retrieval.semantic_search import SemanticSearcher
from packages.code_intel.retrieval.keyword_search import KeywordSearcher
from packages.code_intel.retrieval.hybrid_engine import HybridRetrievalEngine

@pytest.mark.asyncio
async def test_multi_signal_retrieval_and_hybrid_rrf():
    await init_db()
    suffix = uuid.uuid4().hex[:8]
    provider = DeterministicLocalEmbeddingProvider(dimension=768)

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-retrieval-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-retrieval-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="retrieval123",
            branch="main",
            status="COMPLETED",
            embedding_model="models/gemini-embedding-2",
            embedding_dimension=768,
        )
        session.add(ver)
        await session.flush()

        # 1. File & Symbols for Auth
        file_auth = File(
            repository_version_id=ver.id,
            path="services/auth_service.py",
            language="python",
            line_count=40,
            byte_size=1000,
            sha256_hash="hash1",
        )
        session.add(file_auth)
        await session.flush()

        sym_auth = Symbol(
            file_id=file_auth.id,
            name="AuthService",
            fully_qualified_name="services.auth_service.AuthService",
            kind="class",
            start_line=5,
            end_line=35,
            start_col=0,
            end_col=20,
            signature="class AuthService:",
            docstring="Handles JWT authentication and token verification.",
        )
        session.add(sym_auth)
        await session.flush()

        chunk_auth_content = "class AuthService:\n    def verify_jwt_token(self, token: str) -> bool:\n        '''Verify token.'''\n        return len(token) > 10"
        chunk_auth = CodeChunk(
            file_id=file_auth.id,
            symbol_id=sym_auth.id,
            symbol_fqn=sym_auth.fully_qualified_name,
            language="python",
            start_line=5,
            end_line=35,
            content=chunk_auth_content,
            token_count=30,
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
            embedding=provider.embed_document("services/auth_service.py | Symbol: AuthService", chunk_auth_content),
        )
        session.add(chunk_auth)

        # 2. File & Symbols for Billing
        file_bill = File(
            repository_version_id=ver.id,
            path="services/billing_service.py",
            language="python",
            line_count=50,
            byte_size=1200,
            sha256_hash="hash2",
        )
        session.add(file_bill)
        await session.flush()

        sym_bill = Symbol(
            file_id=file_bill.id,
            name="process_payment",
            fully_qualified_name="services.billing_service.process_payment",
            kind="function",
            start_line=10,
            end_line=45,
            start_col=0,
            end_col=30,
            signature="def process_payment(amount: float) -> bool:",
            docstring="Process credit card billing transaction.",
        )
        session.add(sym_bill)
        await session.flush()

        chunk_bill_content = "def process_payment(amount: float) -> bool:\n    '''Process credit card billing transaction.'''\n    return amount > 0"
        chunk_bill = CodeChunk(
            file_id=file_bill.id,
            symbol_id=sym_bill.id,
            symbol_fqn=sym_bill.fully_qualified_name,
            language="python",
            start_line=10,
            end_line=45,
            content=chunk_bill_content,
            token_count=25,
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
            embedding=provider.embed_document("services/billing_service.py | Func: process_payment", chunk_bill_content),
        )
        session.add(chunk_bill)
        await session.commit()

        # Test Signal 1: Exact Matcher
        exact_res = await ExactMatcher.match(
            session=session,
            repository_version_id=ver.id,
            query="AuthService",
        )
        assert len(exact_res) == 1
        assert exact_res[0].symbol_fqn == "services.auth_service.AuthService"
        assert exact_res[0].match_type == "exact"

        # Test Signal 2: Semantic Searcher
        sem_res = await SemanticSearcher.search(
            session=session,
            repository_version_id=ver.id,
            query="credit card payment transaction",
            provider=provider,
        )
        assert len(sem_res) >= 1
        assert sem_res[0].symbol_fqn == "services.billing_service.process_payment"

        # Test Signal 3: Keyword Searcher
        kw_res = await KeywordSearcher.search(
            session=session,
            repository_version_id=ver.id,
            query="verify_jwt_token",
        )
        assert len(kw_res) >= 1
        assert kw_res[0].symbol_fqn == "services.auth_service.AuthService"

        # Test Hybrid Engine with Reciprocal Rank Fusion
        hybrid_res = await HybridRetrievalEngine.retrieve(
            session=session,
            repository_version_id=ver.id,
            query="AuthService token verification",
            mode="hybrid",
            provider=provider,
        )
        assert hybrid_res.total_results >= 1
        top_hit = hybrid_res.chunks[0]
        assert top_hit.symbol_fqn == "services.auth_service.AuthService"
        assert top_hit.score > 0.0

        # Test Filtering by language
        filtered_res = await HybridRetrievalEngine.retrieve(
            session=session,
            repository_version_id=ver.id,
            query="process_payment",
            mode="hybrid",
            language_filter="typescript",  # Should find nothing since both are python
            provider=provider,
        )
        assert filtered_res.total_results == 0

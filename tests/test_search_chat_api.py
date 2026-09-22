import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, Symbol, CodeChunk
from packages.code_intel.embeddings.provider import get_embedding_provider
from apps.api.app.main import app

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()

@pytest.mark.asyncio
async def test_search_and_chat_api_endpoints():
    unique_suffix = uuid.uuid4().hex[:8]
    provider = get_embedding_provider(dimension=768)

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/api_test_{unique_suffix}/repo",
            owner=f"owner_{unique_suffix}",
            name=f"repo_{unique_suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="api1234",
            branch="main",
            status="COMPLETED",
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
        )
        session.add(ver)
        await session.flush()

        f1 = File(
            repository_version_id=ver.id,
            path="src/auth_service.py",
            language="python",
            line_count=40,
            byte_size=1000,
            sha256_hash="hashapi",
        )
        session.add(f1)
        await session.flush()

        s1 = Symbol(
            file_id=f1.id,
            name="AuthService",
            fully_qualified_name="src.auth_service.AuthService",
            kind="class",
            start_line=5,
            end_line=30,
            start_col=0,
            end_col=20,
            signature="class AuthService:",
            docstring="Handles user authentication.",
        )
        session.add(s1)
        await session.flush()

        chunk_content = "class AuthService:\n    def login(self, username, password):\n        return True"
        c1 = CodeChunk(
            file_id=f1.id,
            symbol_id=s1.id,
            symbol_fqn=s1.fully_qualified_name,
            language="python",
            start_line=5,
            end_line=30,
            content=chunk_content,
            token_count=20,
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
            embedding=provider.embed_document("src/auth_service.py | Symbol: AuthService", chunk_content),
        )
        session.add(c1)
        await session.commit()

        repo_id = repo.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Test POST /api/v1/repositories/{id}/search (Hybrid mode)
        search_resp = await client.post(
            f"/api/v1/repositories/{repo_id}/search",
            json={"query": "AuthService login", "mode": "hybrid", "limit": 5},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["total_results"] >= 1
        assert "src/auth_service.py" in search_data["results"][0]["file_path"]

        # 2. Test POST /api/v1/repositories/{id}/search (Exact mode)
        exact_resp = await client.post(
            f"/api/v1/repositories/{repo_id}/search",
            json={"query": "AuthService", "mode": "exact"},
        )
        assert exact_resp.status_code == 200
        exact_data = exact_resp.json()
        assert exact_data["total_results"] == 1
        assert exact_data["results"][0]["symbol_fqn"] == "src.auth_service.AuthService"

        # 3. Test POST /api/v1/repositories/{id}/chat (Grounded RAG Chat)
        chat_resp = await client.post(
            f"/api/v1/repositories/{repo_id}/chat",
            json={"message": "How does the AuthService handle login?"},
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert "response" in chat_data
        assert len(chat_data["citations"]) >= 1
        assert chat_data["citations"][0]["file_path"] == "src/auth_service.py"
        session_id = chat_data["session_id"]

        # 4. Test GET /api/v1/repositories/{id}/chat/sessions
        sessions_resp = await client.get(f"/api/v1/repositories/{repo_id}/chat/sessions")
        assert sessions_resp.status_code == 200
        sessions_data = sessions_resp.json()
        assert len(sessions_data) >= 1
        assert sessions_data[0]["id"] == session_id

        # 5. Test GET /api/v1/repositories/{id}/chat/sessions/{session_id}
        sess_detail_resp = await client.get(f"/api/v1/repositories/{repo_id}/chat/sessions/{session_id}")
        assert sess_detail_resp.status_code == 200
        sess_detail = sess_detail_resp.json()
        assert len(sess_detail["messages"]) >= 2  # user + assistant

        # 6. Test POST /api/v1/repositories/{id}/reindex
        reindex_resp = await client.post(f"/api/v1/repositories/{repo_id}/reindex")
        assert reindex_resp.status_code == 200
        reindex_data = reindex_resp.json()
        assert reindex_data["reindexed_chunks"] >= 1

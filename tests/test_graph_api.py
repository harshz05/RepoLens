import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, Symbol, Dependency
from apps.api.app.main import app

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()

@pytest.mark.asyncio
async def test_graph_api_and_symbol_dependencies():
    unique_suffix = uuid.uuid4().hex[:8]
    # Seed test repository with symbols and dependencies
    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/graph_test_{unique_suffix}/repo",
            owner=f"owner_{unique_suffix}",
            name=f"repo_{unique_suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="abc1234",
            branch="main",
            status="COMPLETED",
        )
        session.add(ver)
        await session.flush()

        f1 = File(
            repository_version_id=ver.id,
            path="src/app.py",
            language="python",
            line_count=50,
            byte_size=1200,
            sha256_hash="hash1",
        )
        session.add(f1)
        await session.flush()

        s1 = Symbol(
            file_id=f1.id,
            name="main_handler",
            fully_qualified_name="src/app.py::main_handler",
            kind="function",
            start_line=5,
            end_line=10,
            start_col=0,
            end_col=20,
        )
        s2 = Symbol(
            file_id=f1.id,
            name="format_data",
            fully_qualified_name="src/app.py::format_data",
            kind="function",
            start_line=15,
            end_line=20,
            start_col=0,
            end_col=20,
        )
        session.add_all([s1, s2])
        await session.flush()

        dep = Dependency(
            caller_symbol_id=s1.id,
            callee_symbol_id=s2.id,
            dependency_type="call",
            file_id=f1.id,
            line_number=7,
        )
        session.add(dep)
        await session.commit()

        repo_id = repo.id
        s1_id = s1.id
        s2_id = s2.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Test GET /api/v1/repositories/{id}/graph
        graph_resp = await client.get(f"/api/v1/repositories/{repo_id}/graph")
        assert graph_resp.status_code == 200
        graph_data = graph_resp.json()

        assert graph_data["repository_id"] == repo_id
        assert graph_data["total_nodes"] == 2
        assert graph_data["total_edges"] == 1
        node_ids = [n["id"] for n in graph_data["nodes"]]
        assert s1_id in node_ids
        assert s2_id in node_ids
        assert graph_data["edges"][0]["source"] == s1_id
        assert graph_data["edges"][0]["target"] == s2_id

        # 2. Test GET /api/v1/repositories/{id}/symbols/{symbol_id}/dependencies
        sym_resp = await client.get(f"/api/v1/repositories/{repo_id}/symbols/{s1_id}/dependencies")
        assert sym_resp.status_code == 200
        sym_data = sym_resp.json()

        assert sym_data["symbol"]["name"] == "main_handler"
        assert len(sym_data["callees"]) == 1
        assert sym_data["callees"][0]["id"] == s2_id

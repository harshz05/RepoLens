import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from packages.db.session import init_db
from apps.api.app.main import app

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_invalid_repo_url_ingest():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/ingest", json={"github_url": "invalid-url"})
        assert response.status_code == 400
        assert "Invalid repository URL" in response.json()["detail"]

@pytest.mark.asyncio
async def test_list_repositories():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

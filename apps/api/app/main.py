import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.db.session import init_db
from apps.api.app.api.v1.repositories import router as repositories_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    await init_db()
    yield
    # Shutdown logic if any

app = FastAPI(
    title="RepoLens API",
    description="AI Codebase Intelligence Platform API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS: explicit origin allow-list (comma-separated env var).
# A wildcard origin combined with credentials is unsafe (and flagged by RepoLens' own SEC-007 rule).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(repositories_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "RepoLens API Gateway",
        "version": "1.0.0",
    }
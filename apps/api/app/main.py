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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "RepoLens API Gateway",
        "version": "1.0.0",
    }

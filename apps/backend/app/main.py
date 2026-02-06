"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth.routes import router as auth_router
from app.api.nlq.routes import router as nlq_router
from app.api.schema.routes import router as schema_router
from app.api.rag.routes import router as rag_router
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="ClarityQL API",
    version="0.1.0",
    description="Natural Language Query API for analytics",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "environment": settings.environment}


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(nlq_router, prefix="/api/nlq", tags=["NLQ"])
app.include_router(schema_router, prefix="/api/schema", tags=["Schema"])
app.include_router(rag_router, prefix="/api/rag", tags=["RAG Ingestion"])

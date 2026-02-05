from fastapi import FastAPI

from app.api.auth.routes import router as auth_router
from app.api.nlq.routes import router as nlq_router
from app.api.schema.routes import router as schema_router

app = FastAPI(title="ClarityQL API", version="0.1.0")


@app.get("/healthz")
def health_check() -> dict:
    return {"status": "ok"}


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(nlq_router, prefix="/nlq", tags=["nlq"])
app.include_router(schema_router, prefix="/schema", tags=["schema"])

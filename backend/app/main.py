from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import intelligence, query, schema


settings = get_settings()

app = FastAPI(
    title="Issa Insight API",
    description="Natural-language analytics API for Issa conversation data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schema.router, prefix="/api/schema", tags=["schema"])
app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["intelligence"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

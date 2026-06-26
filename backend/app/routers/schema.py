from fastapi import APIRouter, HTTPException

from app.services.schema import get_schema_summary, list_public_tables

router = APIRouter()


@router.get("/tables")
def tables() -> dict[str, list[str]]:
    try:
        return {"tables": list_public_tables()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/summary")
def summary() -> dict:
    try:
        return get_schema_summary()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


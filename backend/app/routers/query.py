from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.query_engine import answer_question

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    history: list[dict] = Field(default_factory=list, max_length=6)


@router.post("/query")
def query(request: QueryRequest) -> dict:
    try:
        return answer_question(request.question, request.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

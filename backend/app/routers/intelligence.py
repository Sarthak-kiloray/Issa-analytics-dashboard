from fastapi import APIRouter, HTTPException

from app.services.intelligence import get_anomaly_radar, get_client_risk_queue

router = APIRouter()


@router.get("/radar")
def radar() -> dict:
    try:
        return get_anomaly_radar()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/risk-queue")
def risk_queue() -> dict:
    try:
        return get_client_risk_queue()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


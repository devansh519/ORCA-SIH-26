from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.alerts import AlertCheckRequest, FrequentZoneCreate
from app.services.geofence_alerts import GeofenceAlertService

router = APIRouter(prefix="/api/v1/alerts", tags=["proactive-alerts"])


@router.post("/check")
async def check_alerts(request: AlertCheckRequest):
    try:
        service = GeofenceAlertService()
        return await service.check_all(
            user_id=request.user_id,
            force=request.force,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/active")
async def active_alerts(user_id: str | None = Query(default=None)):
    try:
        service = GeofenceAlertService()
        return {
            "status": "completed",
            "alerts": await service.active_alerts(user_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/zones")
async def frequent_zones(user_id: str | None = Query(default=None)):
    try:
        service = GeofenceAlertService()
        return {
            "status": "completed",
            "zones": await service.list_zones(user_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

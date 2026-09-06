from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.geofence_alerts import GeofenceAlertService

logger = logging.getLogger("orca.geofence_poller")


class GeofenceAlertPoller:
    """
    ORCA proactive geofence poller.

    Behavior:
      1. Performs a real geofence check during application startup.
      2. Only after that check completes, starts the recurring 3-hour timer.
      3. Keeps the last run/result/error available through the status endpoint.

    Running the first check synchronously inside `start()` avoids a subtle
    development-server/reloader race where a newly created background task
    may not get CPU time before a diagnostic request is handled.
    """

    def __init__(self, interval_seconds: int = 3 * 60 * 60) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

        self.running = False
        self.last_run_at: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

        self.service = GeofenceAlertService()

    async def run_once(self) -> dict[str, Any]:
        """Execute one complete proactive geofence check."""
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        self.last_error = None

        print(
            "[ORCA POLLER] CHECK STARTED "
            f"at {self.last_run_at}"
        )

        try:
            result = await self.service.check_all()

            self.last_result = result

            print(
                "[ORCA POLLER] CHECK COMPLETE "
                f"zones={result.get('checked_zones', 0)} "
                f"alerts_created={result.get('alerts_created', 0)}"
            )

            logger.info(
                "Geofence poll complete: zones=%s alerts=%s",
                result.get("checked_zones", 0),
                result.get("alerts_created", 0),
            )

            return result

        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.last_result = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

            print(f"[ORCA POLLER ERROR] {self.last_error}")
            logger.exception("Geofence alert poll failed")

            return self.last_result

    async def _run_recurring(self) -> None:
        """Wait between checks and execute the next proactive check."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                if not self._stop.is_set():
                    await self.run_once()

    async def start(self) -> None:
        if self.running:
            return

        self._stop.clear()
        self.running = True

        print(
            "[ORCA POLLER] STARTED "
            f"(interval={self.interval_seconds}s)"
        )

        # IMPORTANT: run the first check before returning from startup.
        # This makes the proactive behavior deterministic and observable.
        await self.run_once()

        # Schedule only the recurring portion after the initial check.
        self._task = asyncio.create_task(
            self._run_recurring(),
            name="orca-geofence-alert-poller",
        )

        print("[ORCA POLLER] RECURRING SCHEDULE ACTIVE")

    async def stop(self) -> None:
        if not self.running:
            return

        self._stop.set()
        self.running = False

        if self._task:
            if not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        print("[ORCA POLLER] STOPPED")

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
            "last_error": self.last_error,
        }

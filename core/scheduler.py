from __future__ import annotations

import threading
from datetime import datetime, timezone

from core.cache import load_refresh_status, save_refresh_status
from core.refresh import refresh_targets


_WORKER_LOCK = threading.RLock()
_WORKER: threading.Thread | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def get_refresh_status() -> dict:
    return load_refresh_status()


def is_refresh_running() -> bool:
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return True
    status = get_refresh_status()
    if not status.get("running"):
        return False
    updated_at = parse_utc(str(status.get("updated_at", "")))
    if updated_at is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
    return age_seconds < 900


def schedule_background_refresh(
    target_names: list[str],
    settings: dict,
    reason: str,
    cold_start_names: set[str] | None = None,
) -> bool:
    if not target_names:
        return False
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return False
        if is_refresh_running():
            return False

        thread = threading.Thread(
            target=_run_worker,
            args=(list(target_names), dict(settings), reason, set(cold_start_names or set())),
            daemon=True,
            name="chokepoint-refresh-worker",
        )
        globals()["_WORKER"] = thread
        thread.start()
        return True


def _run_worker(target_names: list[str], settings: dict, reason: str, cold_start_names: set[str]) -> None:
    logs: list[str] = []

    def emit(message: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} | {message}"
        logs.append(line)
        save_refresh_status(
            {
                "running": True,
                "reason": reason,
                "targets": target_names,
                "started_at": started_at,
                "updated_at": utc_now(),
                "message": message,
                "logs": logs[-120:],
                "error": "",
            }
        )

    started_at = utc_now()
    save_refresh_status(
        {
            "running": True,
            "reason": reason,
            "targets": target_names,
            "started_at": started_at,
            "updated_at": started_at,
            "message": "Refresh worker started.",
            "logs": [],
            "error": "",
        }
    )
    try:
        emit(f"Background refresh started for {', '.join(target_names)}.")
        refresh_targets(
            target_names=target_names,
            settings=settings,
            emit=emit,
            cold_start_names=cold_start_names,
        )
        emit("Background refresh complete.")
        save_refresh_status(
            {
                "running": False,
                "reason": reason,
                "targets": target_names,
                "started_at": started_at,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "message": "Background refresh complete.",
                "logs": logs[-120:],
                "error": "",
            }
        )
    except Exception as exc:
        logs.append(f"{datetime.now().strftime('%H:%M:%S')} | ERROR | {exc}")
        save_refresh_status(
            {
                "running": False,
                "reason": reason,
                "targets": target_names,
                "started_at": started_at,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "message": "Background refresh failed.",
                "logs": logs[-120:],
                "error": str(exc),
            }
        )

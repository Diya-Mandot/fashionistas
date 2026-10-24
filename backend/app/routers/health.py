"""Configuration reads are free. Explicit POST probes can use paid API calls."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.integrations.agents_client import AgentsClient
from app.integrations.common import AdapterError
from app.integrations.decisions_adapter import DecisionsClient

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/apis")
def api_configuration(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "verified": False,
        "note": "Configuration only. POST /api/health/apis/check explicitly tests the configured modes.",
        "key_configured": bool(settings.openai_api_key.strip()),
        "agents": {"runtime": "agents_sdk", "mode": settings.agents_mode, "model": settings.agents_model},
        "decisions": {"mode": settings.decisions_mode, "model": settings.decisions_model},
    }


@router.post("/apis/check")
async def check_apis(settings: Settings = Depends(get_settings)) -> dict:
    async def check(name: str) -> dict:
        try:
            if name == "agents":
                result = await AgentsClient(settings).run_agent("Reply with the single word ready and no questions.", [], {})
                passed = result.data.output.get("answer", "").strip().lower() == "ready"
            else:
                result = await DecisionsClient(settings).check_connection()
                passed = result.data.passed
            return {"ok": passed, "source": result.source, "live_verified": passed and result.source == "live",
                    "recorded_at": result.recorded_at, "warnings": result.warnings}
        except AdapterError as exc:
            return {"ok": False, "live_verified": False, "error": str(exc)}

    agents, decisions = await asyncio.gather(check("agents"), check("decisions"))
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "agents": agents, "decisions": decisions}

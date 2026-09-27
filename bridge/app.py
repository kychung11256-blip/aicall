import json
import os
import re
import uuid
import asyncio
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
records: dict[str, dict] = {}


@dataclass(frozen=True)
class Settings:
    key: str
    allowed: frozenset[str]
    live: bool
    url: str
    api_key: str
    api_secret: str
    trunk: str
    agent: str


def settings() -> Settings:
    return Settings(
        os.getenv("BRIDGE_KEY", ""),
        frozenset(x.strip() for x in os.getenv("ALLOW_NUMBERS", "").split(",") if x.strip()),
        os.getenv("ENABLE_LIVE_CALLS", "false").lower() == "true",
        os.getenv("LIVEKIT_URL", ""),
        os.getenv("LIVEKIT_API_KEY", ""),
        os.getenv("LIVEKIT_API_SECRET", ""),
        os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", ""),
        os.getenv("LIVEKIT_AGENT_NAME", ""),
    )


def approved_dograh_prompt() -> tuple[str, str]:
    """Read one published startCall -> endCall workflow; reject unsupported graphs."""
    base = os.getenv("DOGRAH_BASE_URL", "").rstrip("/")
    key = os.getenv("DOGRAH_API_KEY", "")
    workflow_id = os.getenv("DOGRAH_WORKFLOW_ID", "")
    if not base or not key or not workflow_id.isdigit():
        raise ValueError("Dograh is not configured")
    req = urllib.request.Request(
        f"{base}/workflow/fetch/{workflow_id}",
        headers={"X-API-Key": key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.load(response)
    if data.get("version_status") != "published":
        raise ValueError("Workflow must be published")
    graph = data.get("workflow_definition") or {}
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    start = next((n for n in nodes if n.get("type") == "startCall"), None)
    end = next((n for n in nodes if n.get("type") == "endCall"), None)
    if (len(nodes) != 2 or len(edges) != 1 or not start or not end
            or edges[0].get("source") != start.get("id")
            or edges[0].get("target") != end.get("id")):
        raise ValueError("Only startCall -> endCall is supported in this trial")
    prompt = start.get("data", {}).get("prompt", "").strip()
    version = str(data.get("version_number") or "")
    if not prompt or len(prompt) > 16000 or not version:
        raise ValueError("Invalid published workflow")
    return version, prompt


class CallRequest(BaseModel):
    lead_id: str = Field(min_length=1, max_length=128)
    phone: str
    workflow_version: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)


async def dial(cfg: Settings, room: str, request: CallRequest, instructions: str) -> None:
    # Dispatch before dialing, so an Agent is waiting when the callee answers.
    from livekit import api

    client = api.LiveKitAPI(
        url=cfg.url, api_key=cfg.api_key, api_secret=cfg.api_secret
    )
    try:
        await client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=cfg.agent,
                room=room,
                metadata=json.dumps({
                    "lead_id": request.lead_id,
                    "workflow_version": request.workflow_version,
                    "instructions": instructions,
                }),
            )
        )
        await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=cfg.trunk,
                sip_call_to=request.phone,
                room_name=room,
                participant_identity=f"lead-{uuid.uuid4().hex[:12]}",
            )
        )
    finally:
        await client.aclose()


app = FastAPI(title="Dograh LiveKit Bridge Prototype")


@app.post("/calls", status_code=202)
async def create_call(request: CallRequest, x_bridge_key: str = Header(default="")):
    cfg = settings()
    if not cfg.key or x_bridge_key != cfg.key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not PHONE.fullmatch(request.phone) or request.phone not in cfg.allowed:
        raise HTTPException(status_code=403, detail="Number not on test allowlist")
    try:
        version, instructions = await asyncio.to_thread(approved_dograh_prompt)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Dograh unavailable: {type(exc).__name__}") from exc
    if request.workflow_version != version:
        raise HTTPException(status_code=409, detail=f"Use published workflow version {version}")
    existing = records.get(request.idempotency_key)
    if existing:
        if existing["lead_id"] != request.lead_id or existing["phone"] != request.phone or existing["workflow_version"] != request.workflow_version:
            raise HTTPException(status_code=409, detail="Idempotency key conflict")
        return existing
    room = f"sales-{uuid.uuid4().hex}"
    result = {
        "idempotency_key": request.idempotency_key,
        "lead_id": request.lead_id,
        "phone": request.phone,
        "workflow_version": request.workflow_version,
        "room": room,
        "status": "dry_run",
    }
    if cfg.live:
        if not all((cfg.url, cfg.api_key, cfg.api_secret, cfg.trunk, cfg.agent)):
            raise HTTPException(status_code=503, detail="LiveKit is not configured")
        records[request.idempotency_key] = {**result, "status": "initiating"}
        try:
            await dial(cfg, room, request, instructions)
        except Exception:
            records[request.idempotency_key]["status"] = "unknown_check_provider_before_retry"
            raise HTTPException(status_code=502, detail="Call setup failed; check provider before retry")
        result["status"] = "dial_requested"
    records[request.idempotency_key] = result
    return result

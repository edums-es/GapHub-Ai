import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from cryptography.fernet import Fernet, InvalidToken
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from auth import get_current_user

logger = logging.getLogger(__name__)

scheduler_router = APIRouter(prefix="/api")

_scheduler = AsyncIOScheduler(timezone="UTC")
_db = None

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
try:
    _fernet = Fernet(ENCRYPTION_KEY.encode())
except Exception:
    _fernet = Fernet(Fernet.generate_key())


def _decrypt(data: str) -> str:
    try:
        return _fernet.decrypt(data.encode()).decode()
    except (InvalidToken, Exception):
        return data


class ScheduleCreate(BaseModel):
    agent_id: str
    name: str
    cron_expression: str
    input_message: str
    active: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    input_message: Optional[str] = None
    active: Optional[bool] = None


async def run_scheduled_job(schedule_id: str):
    """Execute an agent based on schedule."""
    global _db
    if _db is None:
        logger.error(f"Scheduler: DB not initialized for job {schedule_id}")
        return
    try:
        schedule = await _db.schedules.find_one({"schedule_id": schedule_id, "active": True}, {"_id": 0})
        if not schedule:
            logger.info(f"Schedule {schedule_id} not found or inactive")
            return

        agent = await _db.agents.find_one({"agent_id": schedule["agent_id"]}, {"_id": 0})
        if not agent or agent.get("status") != "active":
            logger.info(f"Agent for schedule {schedule_id} not active")
            return

        workspace_creds = {}
        creds_list = await _db.credentials.find({"workspace_id": schedule["workspace_id"]}, {"_id": 0}).to_list(50)
        for cred in creds_list:
            decrypted = {}
            for k, v in cred.get("data", {}).items():
                try:
                    decrypted[k] = _decrypt(str(v))
                except Exception:
                    decrypted[k] = v
            decrypted["workspace_id"] = schedule["workspace_id"]
            workspace_creds[cred["mcp_id"]] = decrypted

        from agents import execute_agent
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        run_doc = {
            "run_id": run_id,
            "agent_id": schedule["agent_id"],
            "workspace_id": schedule["workspace_id"],
            "user_id": "scheduler",
            "status": "running",
            "input": schedule["input_message"],
            "output": None,
            "steps": [],
            "error": None,
            "started_at": now,
            "completed_at": None,
            "triggered_by": "schedule",
            "schedule_id": schedule_id,
        }
        await _db.runs.insert_one({**run_doc})

        try:
            output, steps = await execute_agent(agent, schedule["input_message"], workspace_creds)
            await _db.runs.update_one(
                {"run_id": run_id},
                {"$set": {"status": "completed", "output": output, "steps": steps, "completed_at": datetime.now(timezone.utc)}}
            )
            await _db.schedules.update_one(
                {"schedule_id": schedule_id},
                {"$set": {"last_run": now, "last_run_status": "completed"}}
            )
            logger.info(f"Scheduled job {schedule_id} completed")
        except Exception as e:
            await _db.runs.update_one(
                {"run_id": run_id},
                {"$set": {"status": "failed", "error": str(e), "completed_at": datetime.now(timezone.utc)}}
            )
            await _db.schedules.update_one(
                {"schedule_id": schedule_id},
                {"$set": {"last_run": now, "last_run_status": "failed"}}
            )
            logger.error(f"Scheduled job {schedule_id} failed: {e}")

    except Exception as e:
        logger.error(f"Scheduler job error for {schedule_id}: {e}")


def _add_job(schedule_id: str, cron_expression: str):
    try:
        trigger = CronTrigger.from_crontab(cron_expression, timezone="UTC")
        _scheduler.add_job(
            run_scheduled_job,
            trigger=trigger,
            args=[schedule_id],
            id=schedule_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(f"Added scheduler job: {schedule_id} ({cron_expression})")
    except Exception as e:
        logger.error(f"Failed to add schedule job {schedule_id}: {e}")


def _remove_job(schedule_id: str):
    try:
        if _scheduler.get_job(schedule_id):
            _scheduler.remove_job(schedule_id)
            logger.info(f"Removed scheduler job: {schedule_id}")
    except Exception as e:
        logger.error(f"Failed to remove schedule job {schedule_id}: {e}")


async def init_scheduler(db):
    global _db
    _db = db
    _scheduler.start()
    schedules = await db.schedules.find({"active": True}, {"_id": 0}).to_list(500)
    for schedule in schedules:
        _add_job(schedule["schedule_id"], schedule["cron_expression"])
    logger.info(f"Scheduler initialized with {len(schedules)} active jobs")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


# ── Routes ────────────────────────────────────────────────────────────────────

@scheduler_router.get("/schedules")
async def list_schedules(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    schedules = await db.schedules.find(
        {"workspace_id": user["workspace_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"schedules": schedules}


@scheduler_router.post("/schedules")
async def create_schedule(request: Request, body: ScheduleCreate):
    user = await get_current_user(request)
    db = request.app.state.db

    try:
        CronTrigger.from_crontab(body.cron_expression, timezone="UTC")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Expressão cron inválida: {str(e)}")

    agent = await db.agents.find_one(
        {"agent_id": body.agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    schedule_id = f"sched_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    schedule = {
        "schedule_id": schedule_id,
        "workspace_id": user["workspace_id"],
        "agent_id": body.agent_id,
        "agent_name": agent.get("name", ""),
        "name": body.name,
        "cron_expression": body.cron_expression,
        "input_message": body.input_message,
        "active": body.active,
        "last_run": None,
        "last_run_status": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.schedules.insert_one({**schedule})
    schedule.pop("_id", None)

    if body.active:
        _add_job(schedule_id, body.cron_expression)

    return schedule


@scheduler_router.put("/schedules/{schedule_id}")
async def update_schedule(request: Request, schedule_id: str, body: ScheduleUpdate):
    user = await get_current_user(request)
    db = request.app.state.db

    existing = await db.schedules.find_one(
        {"schedule_id": schedule_id, "workspace_id": user["workspace_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    update = {k: v for k, v in body.model_dump().items() if v is not None}

    new_cron = update.get("cron_expression", existing["cron_expression"])
    if "cron_expression" in update:
        try:
            CronTrigger.from_crontab(new_cron, timezone="UTC")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Expressão cron inválida: {str(e)}")

    update["updated_at"] = datetime.now(timezone.utc)
    await db.schedules.update_one({"schedule_id": schedule_id}, {"$set": update})

    new_active = update.get("active", existing["active"])
    if new_active:
        _add_job(schedule_id, new_cron)
    else:
        _remove_job(schedule_id)

    updated = await db.schedules.find_one({"schedule_id": schedule_id}, {"_id": 0})
    return updated


@scheduler_router.delete("/schedules/{schedule_id}")
async def delete_schedule(request: Request, schedule_id: str):
    user = await get_current_user(request)
    db = request.app.state.db

    result = await db.schedules.delete_one(
        {"schedule_id": schedule_id, "workspace_id": user["workspace_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    _remove_job(schedule_id)
    return {"message": "Agendamento excluído"}

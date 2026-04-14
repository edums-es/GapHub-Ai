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




# ── Auto-Polling de Leads Pendentes ──────────────────────────────────────────
# NOVA FUNCIONALIDADE: Job automático que verifica leads pendentes no CRM
# e dispara o agente de IA para cada ticket não processado ainda.
#
# Este job é registrado automaticamente no init_scheduler() para todos os
# agentes que tenham a flag auto_process_pending=True.

async def poll_pending_leads_for_agent(agent_id: str):
    """
    Job APScheduler: varre tickets pendentes do CRM e dispara o agente de IA
    para cada um que ainda não foi processado nos últimos 30 minutos.
    Chamado automaticamente pelo APScheduler quando configurado.
    """
    global _db
    if _db is None:
        logger.error(f"[PollPending] DB não inicializado para agente {agent_id}")
        return

    try:
        agent = await _db.agents.find_one({"agent_id": agent_id, "active": True} if False else {"agent_id": agent_id}, {"_id": 0})
        if not agent or agent.get("status") != "active":
            logger.info(f"[PollPending] Agente {agent_id} não ativo, pulando poll")
            return

        workspace_id = agent.get("workspace_id", "")

        # Carrega credenciais do workspace (padrão correto: decrypt field-by-field)
        workspace_creds = {}
        creds_list = await _db.credentials.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(50)
        for cred in creds_list:
            decrypted = {}
            for k, v in cred.get("data", {}).items():
                try:
                    decrypted[k] = _decrypt(str(v))
                except Exception:
                    decrypted[k] = v
            decrypted["workspace_id"] = workspace_id
            workspace_creds[cred["mcp_id"]] = decrypted

        # Credenciais MCP por agente
        agent_mcp_doc = await _db.mcp_credentials.find_one({"agent_id": agent_id}, {"_id": 0})
        if agent_mcp_doc:
            from cryptography.fernet import Fernet
            raw_key = os.environ.get("ENCRYPTION_KEY", "").strip()
            try:
                f = Fernet(raw_key.encode()) if raw_key else None
                def _d(v):
                    try:
                        return f.decrypt(v.encode()).decode() if f else v
                    except Exception:
                        return v
            except Exception:
                _d = lambda v: v

            agent_mcp_creds = {
                "apiUrl": agent_mcp_doc.get("apiUrl", ""),
                "userToken": _d(agent_mcp_doc["userToken"]) if agent_mcp_doc.get("userToken") else "",
                "wabaId": agent_mcp_doc.get("wabaId", ""),
                "base_url": agent_mcp_doc.get("apiUrl", ""),
                "token": _d(agent_mcp_doc["userToken"]) if agent_mcp_doc.get("userToken") else "",
                "workspace_id": workspace_id,
            }
            workspace_creds["clickmassa"] = agent_mcp_creds

        # Busca tickets pendentes
        from tools import execute_tool
        pending_result = await execute_tool(
            "clickmassa", "listar_tickets_pendentes", {}, workspace_creds.get("clickmassa", {})
        )

        tickets = pending_result.get("tickets", [])
        if isinstance(pending_result, list):
            tickets = pending_result

        if not tickets:
            logger.info(f"[PollPending] Agente {agent_id}: nenhum ticket pendente")
            return

        logger.info(f"[PollPending] Agente {agent_id}: {len(tickets)} tickets pendentes")

        from agents import execute_agent
        from datetime import timedelta
        processed = 0

        for ticket in tickets[:10]:  # max 10 por ciclo
            ticket_id = str(ticket.get("id", ""))
            contact = ticket.get("contact", {})
            contact_number = contact.get("number", "")
            contact_name = contact.get("name", contact_number)

            if not ticket_id:
                continue

            # Deduplica: evita reprocessar ticket recente
            recent = await _db.runs.find_one({
                "agent_id": agent_id,
                "metadata.ticket_id": ticket_id,
                "status": {"$in": ["completed", "running"]},
                "started_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=30)},
            })
            if recent:
                logger.info(f"[PollPending] Ticket {ticket_id} já processado recentemente")
                continue

            last_msg = ticket.get("lastMessage", {})
            last_msg_body = last_msg.get("body", "") if last_msg else ""

            agent_input = (
                f"Novo lead pendente na fila do CRM.\n"
                f"Ticket ID: {ticket_id}\n"
                f"Contato: {contact_name} ({contact_number})\n"
                f"Última mensagem: {last_msg_body}\n\n"
                f"MISSÃO: O usuário pediu EXPLICITAMENTE para você responder a este ticket.\n"
                f"Por favor:\n"
                f"1. Use buscar_mensagens_ticket(ticket_id=\"{ticket_id}\") para ler a conversa completa\n"
                f"2. Entenda o contexto e a necessidade do lead\n"
                f"3. Responda ao lead de forma adequada. Use OBRIGATORIAMENTE a ferramenta enviar_mensagem_direta passando o ticket_id=\"{ticket_id}\".\n"
                f"4. Se necessário, feche o ticket ou atribua a um atendente humano."
            )

            run_id = f"run_{uuid.uuid4().hex[:12]}"
            session_id = f"poll_{agent_id}_{ticket_id}"
            now = datetime.now(timezone.utc)

            run_doc = {
                "run_id": run_id,
                "agent_id": agent_id,
                "workspace_id": workspace_id,
                "user_id": "scheduler_poll",
                "session_id": session_id,
                "status": "running",
                "input": agent_input,
                "output": None,
                "steps": [],
                "error": None,
                "started_at": now,
                "completed_at": None,
                "triggered_by": "auto_poll_pending",
                "source": "pending_leads_processor",
                "metadata": {"ticket_id": ticket_id, "contact_number": contact_number},
            }
            await _db.runs.insert_one(run_doc)

            try:
                import asyncio as _asyncio
                output, steps = await _asyncio.wait_for(
                    execute_agent(agent, agent_input, workspace_creds, _db, session_id),
                    timeout=90.0
                )
                await _db.runs.update_one(
                    {"run_id": run_id},
                    {"$set": {
                        "status": "completed",
                        "output": output,
                        "steps": steps,
                        "completed_at": datetime.now(timezone.utc),
                    }}
                )
                processed += 1
                logger.info(f"[PollPending] Ticket {ticket_id} processado com sucesso")
            except Exception as e:
                await _db.runs.update_one(
                    {"run_id": run_id},
                    {"$set": {
                        "status": "failed",
                        "error": str(e),
                        "completed_at": datetime.now(timezone.utc),
                    }}
                )
                logger.error(f"[PollPending] Erro ao processar ticket {ticket_id}: {e}")

        logger.info(f"[PollPending] Agente {agent_id}: {processed} leads processados neste ciclo")

    except Exception as e:
        logger.error(f"[PollPending] Erro geral para agente {agent_id}: {e}")


def register_pending_leads_poll(agent_id: str, interval_minutes: int = 2):
    """
    Registra job de polling automático de leads pendentes para um agente.
    Roda a cada `interval_minutes` minutos.
    Chamado pelo frontend/API quando o usuário ativa o processamento automático.
    """
    job_id = f"poll_pending_{agent_id}"
    try:
        from apscheduler.triggers.interval import IntervalTrigger
        trigger = IntervalTrigger(minutes=interval_minutes, timezone="UTC")
        _scheduler.add_job(
            poll_pending_leads_for_agent,
            trigger=trigger,
            args=[agent_id],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=60,
        )
        logger.info(f"[PollPending] Job registrado para agente {agent_id} (intervalo: {interval_minutes}min)")
    except Exception as e:
        logger.error(f"[PollPending] Erro ao registrar job para {agent_id}: {e}")


def unregister_pending_leads_poll(agent_id: str):
    """Remove job de polling de leads para um agente."""
    job_id = f"poll_pending_{agent_id}"
    _remove_job(job_id)



async def init_scheduler(db):
    global _db
    _db = db
    _scheduler.start()
    schedules = await db.schedules.find({"active": True}, {"_id": 0}).to_list(500)
    for schedule in schedules:
        _add_job(schedule["schedule_id"], schedule["cron_expression"])
    logger.info(f"Scheduler initialized with {len(schedules)} active jobs")

    # CORREÇÃO BUG 4: Registra polling automático de leads para agentes com auto_process_pending=True
    # O intervalo padrão é 2 minutos — configurável por agente via campo poll_interval_minutes.
    try:
        auto_agents = await db.agents.find(
            {"auto_process_pending": True, "status": "active"}, {"_id": 0}
        ).to_list(100)
        for agent in auto_agents:
            interval = agent.get("poll_interval_minutes", 2)
            register_pending_leads_poll(agent["agent_id"], interval)
        if auto_agents:
            logger.info(f"[PollPending] {len(auto_agents)} agente(s) com auto-polling registrado(s)")
    except Exception as e:
        logger.warning(f"[PollPending] Erro ao carregar agentes com auto_process_pending: {e}")


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


@scheduler_router.post("/agents/{agent_id}/auto-poll")
async def enable_auto_poll(request: Request, agent_id: str, interval_minutes: int = 2):
    """
    NOVA ROTA: Ativa o polling automático de leads pendentes para um agente.
    O agente verificará a fila de pendentes a cada `interval_minutes` minutos.
    """
    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {
            "auto_process_pending": True,
            "poll_interval_minutes": interval_minutes,
            "updated_at": datetime.now(timezone.utc),
        }}
    )
    register_pending_leads_poll(agent_id, interval_minutes)

    return {
        "agent_id": agent_id,
        "auto_process_pending": True,
        "poll_interval_minutes": interval_minutes,
        "message": f"Auto-polling ativado. Leads pendentes serão verificados a cada {interval_minutes} minuto(s).",
    }


@scheduler_router.delete("/agents/{agent_id}/auto-poll")
async def disable_auto_poll(request: Request, agent_id: str):
    """NOVA ROTA: Desativa o polling automático de leads para um agente."""
    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"auto_process_pending": False, "updated_at": datetime.now(timezone.utc)}}
    )
    unregister_pending_leads_poll(agent_id)

    return {"agent_id": agent_id, "auto_process_pending": False, "message": "Auto-polling desativado."}

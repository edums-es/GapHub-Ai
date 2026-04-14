import os
import uuid
import json
import logging
import asyncio
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from cryptography.fernet import Fernet, InvalidToken

from auth import get_current_user
from tools import execute_tool, build_tool_definitions

logger = logging.getLogger(__name__)

agents_router = APIRouter(prefix="/api")

# ── Bug Fix #1: ENCRYPTION_KEY estável entre restarts ────────────────────────
# A chave é gerada UMA vez e persistida no .env automaticamente.
# Se .env não for gravável, lança erro claro em vez de gerar chave volátil.

def _load_or_create_encryption_key() -> Fernet:
    """
    Carrega ENCRYPTION_KEY do ambiente. Se não existir:
    - Gera uma chave nova
    - Persiste no arquivo .env (pasta do backend)
    - Loga aviso pedindo restart para carregar a chave persistida
    Nunca gera uma chave volátil silenciosamente em produção.
    """
    raw_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if raw_key:
        try:
            f = Fernet(raw_key.encode())
            return f
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY inválida no ambiente. "
                "Certifique-se de usar uma chave Fernet válida (base64-url de 32 bytes). "
                "Gere uma nova com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

    # Chave não configurada — gera e persiste
    new_key = Fernet.generate_key().decode()
    env_path = Path(__file__).parent / ".env"
    try:
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        if "ENCRYPTION_KEY=" not in existing:
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\nENCRYPTION_KEY={new_key}\n")
            logger.warning(
                "ENCRYPTION_KEY não configurada. Uma nova chave foi gerada e salva em .env. "
                "Reinicie o servidor para carregar a chave persistida e evitar perda de dados criptografados."
            )
        else:
            logger.error(
                "ENCRYPTION_KEY está no .env mas não foi carregada — verifique o arquivo .env. "
                "Usando chave temporária (dados criptografados SERÃO PERDIDOS no próximo restart)."
            )
    except OSError as e:
        logger.error(
            f"Não foi possível persistir ENCRYPTION_KEY em {env_path}: {e}. "
            "Usando chave temporária. Configure ENCRYPTION_KEY manualmente no ambiente!"
        )

    os.environ["ENCRYPTION_KEY"] = new_key
    return Fernet(new_key.encode())


fernet = _load_or_create_encryption_key()


def encrypt(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()


def decrypt(data: str) -> str:
    try:
        return fernet.decrypt(data.encode()).decode()
    except InvalidToken:
        return data


# ── Models ──────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    llm_config: Optional[dict] = {}
    nodes: Optional[List[dict]] = []
    edges: Optional[List[dict]] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    llm_config: Optional[dict] = None
    nodes: Optional[List[dict]] = None
    edges: Optional[List[dict]] = None


class CredentialCreate(BaseModel):
    mcp_id: str
    data: dict


class AgentRunRequest(BaseModel):
    input: str
    session_id: Optional[str] = None


# ── Agent Routes ─────────────────────────────────────────────────────────────

@agents_router.get("/agents")
async def list_agents(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    ws_id = user["workspace_id"]
    agents = await db.agents.find({"workspace_id": ws_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    # Append run counts
    for agent in agents:
        count = await db.runs.count_documents({"agent_id": agent["agent_id"]})
        agent["run_count"] = count
    return {"agents": agents}


@agents_router.post("/agents")
async def create_agent(request: Request, body: AgentCreate):
    user = await get_current_user(request)
    db = request.app.state.db
    ws_id = user["workspace_id"]
    agent_id = f"agent_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Default nodes for a new agent
    default_nodes = body.nodes if body.nodes else [
        {"node_id": "trigger_1", "type": "trigger", "position": {"x": 80, "y": 240}, "config": {"label": "Iniciar", "description": "Entrada manual do usuário"}},
        {"node_id": "llm_core", "type": "llm", "position": {"x": 380, "y": 240}, "config": {"label": "Agente IA"}},
        {"node_id": "output_1", "type": "output", "position": {"x": 680, "y": 240}, "config": {"label": "Resultado"}},
    ]
    default_edges = body.edges if body.edges else [
        {"id": "e1", "source": "trigger_1", "target": "llm_core"},
        {"id": "e2", "source": "llm_core", "target": "output_1"},
    ]

    agent = {
        "agent_id": agent_id,
        "workspace_id": ws_id,
        "name": body.name,
        "description": body.description,
        "status": "active",
        "llm_config": body.llm_config or {"provider": "openai", "model": "gpt-4o-mini", "api_key": "", "system_prompt": "Você é um assistente de CRM inteligente.", "temperature": 0.7, "max_tokens": 4096},
        "nodes": default_nodes,
        "edges": default_edges,
        "created_at": now,
        "updated_at": now,
    }
    await db.agents.insert_one({**agent})
    agent.pop("_id", None)
    return agent


@agents_router.get("/agents/{agent_id}")
async def get_agent(request: Request, agent_id: str):
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    return agent


@agents_router.put("/agents/{agent_id}")
async def update_agent(request: Request, agent_id: str, body: AgentUpdate):
    user = await get_current_user(request)
    db = request.app.state.db
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc)
    result = await db.agents.update_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]},
        {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    agent = await db.agents.find_one({"agent_id": agent_id}, {"_id": 0})
    return agent


@agents_router.delete("/agents/{agent_id}")
async def delete_agent(request: Request, agent_id: str):
    user = await get_current_user(request)
    db = request.app.state.db
    result = await db.agents.delete_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    return {"message": "Agente excluído"}


# ── Credentials Routes ────────────────────────────────────────────────────────

@agents_router.get("/credentials")
async def list_credentials(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    creds = await db.credentials.find({"workspace_id": user["workspace_id"]}, {"_id": 0}).to_list(100)
    # Mask sensitive data
    for c in creds:
        masked = {}
        for k, v in c.get("data", {}).items():
            if any(s in k.lower() for s in ["password", "key", "token", "secret"]):
                masked[k] = "••••••••" if v else ""
            else:
                masked[k] = v
        c["data_masked"] = masked
    return {"credentials": creds}


@agents_router.post("/credentials")
async def upsert_credential(request: Request, body: CredentialCreate):
    user = await get_current_user(request)
    db = request.app.state.db
    ws_id = user["workspace_id"]

    existing = await db.credentials.find_one({"workspace_id": ws_id, "mcp_id": body.mcp_id})

    if existing:
        # Merge: preserve existing encrypted values for sensitive fields left blank
        merged = dict(existing.get("data", {}))  # keep existing encrypted data as base
        for k, v in body.data.items():
            is_sensitive = any(s in k.lower() for s in ["password", "key", "token", "secret"])
            if is_sensitive and not str(v).strip():
                continue  # keep existing encrypted value
            merged[k] = encrypt(str(v)) if is_sensitive else v

        await db.credentials.update_one(
            {"workspace_id": ws_id, "mcp_id": body.mcp_id},
            {"$set": {"data": merged, "updated_at": datetime.now(timezone.utc)}}
        )
    else:
        encrypted_data = {
            k: encrypt(str(v)) if any(s in k.lower() for s in ["password", "key", "token", "secret"]) else v
            for k, v in body.data.items()
        }
        await db.credentials.insert_one({
            "cred_id": f"cred_{uuid.uuid4().hex[:12]}",
            "workspace_id": ws_id,
            "mcp_id": body.mcp_id,
            "data": encrypted_data,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    return {"message": "Credencial salva"}


@agents_router.delete("/credentials/{mcp_id}")
async def delete_credential(request: Request, mcp_id: str):
    user = await get_current_user(request)
    db = request.app.state.db
    await db.credentials.delete_one({"workspace_id": user["workspace_id"], "mcp_id": mcp_id})
    return {"message": "Credencial removida"}


# ── Per-Agent MCP Credentials (mcp_credentials collection) ───────────────────
# Allows each agent to have its own ClickMassa credentials (apiUrl, userToken, wabaId)
# encrypted with Fernet and stored in the mcp_credentials collection.

class AgentMCPCredential(BaseModel):
    apiUrl: str = ""
    userToken: str = ""
    wabaId: Optional[str] = ""


@agents_router.get("/agents/{agent_id}/mcp-credentials")
async def get_agent_mcp_credentials(request: Request, agent_id: str):
    """Retorna credenciais MCP do agente (campos sensíveis mascarados)."""
    user = await get_current_user(request)
    db = request.app.state.db
    # Ensure agent belongs to user's workspace
    agent = await db.agents.find_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0, "agent_id": 1}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    doc = await db.mcp_credentials.find_one({"agent_id": agent_id}, {"_id": 0})
    if not doc:
        return {"agent_id": agent_id, "configured": False}

    # Decrypt and mask sensitive fields for response
    def _mask(val: str) -> str:
        try:
            decrypted = decrypt(val)
            return "••••" + decrypted[-4:] if len(decrypted) > 4 else "••••"
        except Exception:
            return "••••"

    return {
        "agent_id": agent_id,
        "configured": True,
        "apiUrl": doc.get("apiUrl", ""),  # URL não é sensível
        "userToken": _mask(doc["userToken"]) if doc.get("userToken") else "",
        "wabaId": doc.get("wabaId", ""),
        "updated_at": doc.get("updated_at"),
    }


@agents_router.put("/agents/{agent_id}/mcp-credentials")
async def upsert_agent_mcp_credentials(request: Request, agent_id: str, body: AgentMCPCredential):
    """
    Salva credenciais MCP por agente (criptografadas com Fernet).
    Permite que cada agente use uma conta ClickMassa diferente — ideal para multi-tenant.
    """
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0, "agent_id": 1}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    now = datetime.now(timezone.utc)
    doc = {
        "agent_id": agent_id,
        "workspace_id": user["workspace_id"],
        "apiUrl": body.apiUrl,  # URL não é sensível
        "userToken": encrypt(body.userToken) if body.userToken else "",
        "wabaId": body.wabaId or "",
        "updated_at": now,
    }

    existing = await db.mcp_credentials.find_one({"agent_id": agent_id})
    if existing:
        await db.mcp_credentials.update_one({"agent_id": agent_id}, {"$set": doc})
    else:
        doc["created_at"] = now
        await db.mcp_credentials.insert_one(doc)

    return {"message": "Credenciais MCP do agente salvas com sucesso.", "agent_id": agent_id}


@agents_router.delete("/agents/{agent_id}/mcp-credentials")
async def delete_agent_mcp_credentials(request: Request, agent_id: str):
    """Remove credenciais MCP específicas do agente."""
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0, "agent_id": 1}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    await db.mcp_credentials.delete_one({"agent_id": agent_id})
    return {"message": "Credenciais MCP do agente removidas."}


async def _get_agent_mcp_credentials(db, agent_id: str) -> Optional[dict]:
    """
    Helper interno: retorna credenciais MCP decriptadas para um agente específico.
    Retorna None se o agente não tiver credenciais próprias configuradas.
    """
    doc = await db.mcp_credentials.find_one({"agent_id": agent_id}, {"_id": 0})
    if not doc:
        return None
    return {
        "apiUrl": doc.get("apiUrl", ""),
        "userToken": decrypt(doc["userToken"]) if doc.get("userToken") else "",
        "wabaId": doc.get("wabaId", ""),
        # Campos legados para compatibilidade com tools.py
        "base_url": doc.get("apiUrl", ""),
        "token": decrypt(doc["userToken"]) if doc.get("userToken") else "",
    }


# ── Run Routes ────────────────────────────────────────────────────────────────

@agents_router.get("/runs")
async def list_runs(request: Request, limit: int = 50):
    user = await get_current_user(request)
    db = request.app.state.db
    # Get all agents for this workspace
    agents = await db.agents.find({"workspace_id": user["workspace_id"]}, {"agent_id": 1, "name": 1, "_id": 0}).to_list(200)
    agent_ids = [a["agent_id"] for a in agents]
    agent_names = {a["agent_id"]: a["name"] for a in agents}
    if not agent_ids:
        return {"runs": []}
    runs = await db.runs.find({"agent_id": {"$in": agent_ids}}, {"_id": 0}).sort("started_at", -1).to_list(limit)
    for r in runs:
        r["agent_name"] = agent_names.get(r["agent_id"], "Desconhecido")
    return {"runs": runs}


@agents_router.get("/agents/{agent_id}/runs")
async def list_agent_runs(request: Request, agent_id: str):
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    runs = await db.runs.find({"agent_id": agent_id}, {"_id": 0}).sort("started_at", -1).to_list(50)
    return {"runs": runs}


@agents_router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    user = await get_current_user(request)
    db = request.app.state.db
    run = await db.runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return run


# ── Agent Execution ───────────────────────────────────────────────────────────

@agents_router.post("/agents/{agent_id}/run")
async def run_agent(request: Request, agent_id: str, body: AgentRunRequest):
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    if agent.get("status") != "active":
        raise HTTPException(status_code=400, detail="Agente inativo")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Get credentials (workspace-level)
    workspace_creds = {}
    creds_list = await db.credentials.find({"workspace_id": user["workspace_id"]}, {"_id": 0}).to_list(50)
    for cred in creds_list:
        decrypted = {}
        for k, v in cred.get("data", {}).items():
            try:
                decrypted[k] = decrypt(str(v))
            except Exception:
                decrypted[k] = v
        decrypted["workspace_id"] = user["workspace_id"]
        workspace_creds[cred["mcp_id"]] = decrypted

    # Per-agent MCP credentials override workspace-level credentials for ClickMassa
    agent_mcp_creds = await _get_agent_mcp_credentials(db, agent_id)
    if agent_mcp_creds:
        agent_mcp_creds["workspace_id"] = user["workspace_id"]
        workspace_creds["clickmassa"] = agent_mcp_creds

    # Resolve session_id — usa o fornecido ou gera um novo por agente+usuário
    session_id = body.session_id or f"{agent_id}_{user['user_id']}"

    # Save run as running
    run_doc = {
        "run_id": run_id,
        "agent_id": agent_id,
        "workspace_id": user["workspace_id"],
        "user_id": user["user_id"],
        "session_id": session_id,
        "status": "running",
        "input": body.input,
        "output": None,
        "steps": [],
        "error": None,
        "started_at": now,
        "completed_at": None,
    }
    await db.runs.insert_one({**run_doc})

    try:
        output, steps = await asyncio.wait_for(
            execute_agent(agent, body.input, workspace_creds, db, session_id),
            timeout=90.0
        )
        await db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "completed", "output": output, "steps": steps, "completed_at": datetime.now(timezone.utc)}}
        )
        return {"run_id": run_id, "status": "completed", "output": output, "steps": steps}
    except asyncio.TimeoutError:
        await db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "failed", "error": "Tempo limite de 90s excedido. Tente um comando mais específico.", "completed_at": datetime.now(timezone.utc)}}
        )
        raise HTTPException(status_code=408, detail="Tempo limite excedido. Tente um comando mais específico ou verifique as credenciais configuradas.")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Agent run error {run_id}: {error_msg}")
        await db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "failed", "error": error_msg, "completed_at": datetime.now(timezone.utc)}}
        )
        raise HTTPException(status_code=500, detail=f"Erro na execução: {error_msg}")


@agents_router.post("/agents/{agent_id}/run/stream")
async def run_agent_stream(request: Request, agent_id: str, body: AgentRunRequest):
    """
    Streaming SSE verdadeiro token a token — usa asyncio.Queue como canal entre o loop
    de execução do agente (background task) e o gerador SSE (resposta HTTP).

    Eventos emitidos:
      {"type": "token",      "text": "..."}          — fragmento de texto do LLM
      {"type": "tool_start", "tool": "...", "params": {...}}  — início de chamada de ferramenta
      {"type": "tool_done",  "tool": "...", "result": {...}}  — resultado da ferramenta
      {"type": "done",       "output": "...", "steps": [...]} — resposta final completa
      {"type": "error",      "error": "..."}          — erro durante execução
    """
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    if agent.get("status") != "active":
        raise HTTPException(status_code=400, detail="Agente inativo")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    workspace_creds = {}
    creds_list = await db.credentials.find({"workspace_id": user["workspace_id"]}, {"_id": 0}).to_list(50)
    for cred in creds_list:
        decrypted = {}
        for k, v in cred.get("data", {}).items():
            try:
                decrypted[k] = decrypt(str(v))
            except Exception:
                decrypted[k] = v
        decrypted["workspace_id"] = user["workspace_id"]
        workspace_creds[cred["mcp_id"]] = decrypted

    # Per-agent MCP credentials override workspace-level for ClickMassa
    agent_mcp_creds = await _get_agent_mcp_credentials(db, agent_id)
    if agent_mcp_creds:
        agent_mcp_creds["workspace_id"] = user["workspace_id"]
        workspace_creds["clickmassa"] = agent_mcp_creds

    session_id = body.session_id or f"{agent_id}_{user['user_id']}"

    await db.runs.insert_one({
        "run_id": run_id, "agent_id": agent_id,
        "workspace_id": user["workspace_id"], "user_id": user["user_id"],
        "session_id": session_id, "status": "running",
        "input": body.input, "output": None, "steps": [], "error": None,
        "started_at": now, "completed_at": None,
    })

    # Queue-based true streaming: agent pushes events, generator consumes them
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)
    _SENTINEL = object()  # sinal de fim de stream

    async def agent_worker():
        """Roda o agente em background e envia eventos para a queue."""
        try:
            full_output, steps = await asyncio.wait_for(
                execute_agent_streaming_queue(
                    agent, body.input, workspace_creds, db, session_id, run_id, queue
                ),
                timeout=90.0,
            )
            await db.runs.update_one(
                {"run_id": run_id},
                {"$set": {"status": "completed", "output": full_output, "steps": steps,
                           "completed_at": datetime.now(timezone.utc)}}
            )
            await queue.put({"type": "done", "run_id": run_id, "output": full_output, "steps": steps})
        except asyncio.TimeoutError:
            err = "Tempo limite de 90s excedido."
            await db.runs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "error": err, "completed_at": datetime.now(timezone.utc)}})
            await queue.put({"type": "error", "error": err})
        except Exception as e:
            err = str(e)
            logger.error(f"Stream run error {run_id}: {err}")
            await db.runs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "error": err, "completed_at": datetime.now(timezone.utc)}})
            await queue.put({"type": "error", "error": err})
        finally:
            await queue.put(_SENTINEL)

    async def event_generator():
        task = asyncio.create_task(agent_worker())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=95.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Stream timeout'})}\n\n"
                    break
                if event is _SENTINEL:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def execute_agent_streaming_queue(
    agent: dict, user_input: str, workspace_creds: dict,
    db=None, session_id: str = None, run_id: str = None,
    queue: asyncio.Queue = None,
) -> tuple:
    """
    Versão streaming REAL com asyncio.Queue.
    Envia eventos token a token e tool_start/tool_done para a queue.
    Retorna (output_completo, steps) ao final.
    """
    import litellm
    llm_config = agent.get("llm_config", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    api_key = llm_config.get("api_key") or os.environ.get("EMERGENT_LLM_KEY")
    system_prompt = llm_config.get("system_prompt", "Você é um assistente inteligente de CRM.")
    temperature = float(llm_config.get("temperature", 0.7))
    max_tokens = int(llm_config.get("max_tokens", 4096))

    if not api_key:
        raise ValueError("API Key do LLM não configurada.")

    nodes = [n for n in agent.get("nodes", []) if n.get("type") == "tool"]
    tool_defs = build_tool_definitions(nodes)

    history = []
    if db is not None and session_id:
        try:
            doc = await db.chat_sessions.find_one(
                {"session_id": session_id, "agent_id": agent.get("agent_id")}, {"_id": 0}
            )
            if doc:
                history = doc.get("history", [])[-40:]
        except Exception:
            pass

    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_input}]
    steps = []
    max_iterations = 8
    litellm.set_verbose = False

    async def _emit(event: dict):
        if queue is not None:
            await queue.put(event)

    for iteration in range(max_iterations):
        kwargs = {
            "model": f"{provider}/{model}", "messages": messages,
            "api_key": api_key, "temperature": temperature, "max_tokens": max_tokens,
            "stream": True,
        }
        if tool_defs:
            kwargs["tools"] = tool_defs

        chunks = []
        tool_calls_raw = {}

        async for chunk in await litellm.acompletion(**kwargs):
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            # Emit text tokens immediately as they arrive
            if delta.content:
                chunks.append(delta.content)
                await _emit({"type": "token", "text": delta.content})
            # Accumulate tool call fragments
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                    if tc.function:
                        if tc.function.name:
                            tool_calls_raw[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_raw[idx]["arguments"] += tc.function.arguments
                    if tc.id:
                        tool_calls_raw[idx]["id"] = tc.id

        full_content = "".join(chunks)

        if tool_calls_raw:
            msg_dict = {
                "role": "assistant", "content": full_content or "",
                "tool_calls": [
                    {"id": v["id"], "type": "function", "function": {"name": v["name"], "arguments": v["arguments"]}}
                    for v in tool_calls_raw.values()
                ],
            }
            messages.append(msg_dict)

            for v in tool_calls_raw.values():
                fn_name = v["name"]
                try:
                    params = json.loads(v["arguments"])
                except Exception:
                    params = {}
                mcp_id, tool_name = fn_name.split("__", 1) if "__" in fn_name else ("clickmassa", fn_name)
                creds = workspace_creds.get(mcp_id, {})

                # Notify frontend that a tool is running
                await _emit({"type": "tool_start", "tool": fn_name, "params": params})

                result = await execute_tool(mcp_id, tool_name, params, creds)
                steps.append({"tool": fn_name, "params": params, "result": result, "iteration": iteration})
                messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False), "tool_call_id": v["id"]})

                await _emit({"type": "tool_done", "tool": fn_name, "result": result})
        else:
            final_output = full_content or "Execução concluída."
            if db is not None and session_id:
                try:
                    await db.chat_sessions.update_one(
                        {"session_id": session_id, "agent_id": agent.get("agent_id")},
                        {"$push": {"history": {"$each": [
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": final_output},
                        ]}},
                         "$set": {"updated_at": datetime.now(timezone.utc),
                                  "agent_id": agent.get("agent_id"),
                                  "session_id": session_id},
                         "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                        upsert=True,
                    )
                except Exception:
                    pass
            return final_output, steps

    return "Limite máximo de iterações atingido.", steps


# Legacy alias kept for backwards compatibility (non-streaming path uses execute_agent)
async def execute_agent_streaming(agent: dict, user_input: str, workspace_creds: dict,
                                  db=None, session_id: str = None, run_id: str = None):
    """Legacy wrapper — delegates to queue-based implementation with no queue (accumulates)."""
    return await execute_agent_streaming_queue(
        agent, user_input, workspace_creds, db, session_id, run_id, queue=None
    )


@agents_router.post("/runs/cleanup-stale")
async def cleanup_stale_runs(request: Request):
    """Mark runs stuck in 'running' for > 10 min as failed."""
    user = await get_current_user(request)
    db = request.app.state.db
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    result = await db.runs.update_many(
        {
            "workspace_id": user["workspace_id"],
            "status": "running",
            "started_at": {"$lt": stale_cutoff},
        },
        {"$set": {
            "status": "failed",
            "error": "Execução interrompida (timeout de conexão)",
            "completed_at": datetime.now(timezone.utc),
        }}
    )
    return {"cleaned": result.modified_count}


async def execute_agent(agent: dict, user_input: str, workspace_creds: dict, db=None, session_id: str = None):
    import litellm
    llm_config = agent.get("llm_config", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    api_key = llm_config.get("api_key") or os.environ.get("EMERGENT_LLM_KEY")
    user_system_prompt = llm_config.get("system_prompt", "Você é um assistente inteligente de CRM. Responda sempre em português.")
    temperature = float(llm_config.get("temperature", 0.7))
    max_tokens = int(llm_config.get("max_tokens", 4096))

    if not api_key:
        raise ValueError("API Key do LLM não configurada. Configure no nó LLM do agente.")

    # Mandatory CRM behavior rules appended to every agent
    MANDATORY_CRM_RULES = """

---
REGRAS OBRIGATÓRIAS DO CRM (SEMPRE SIGA — SEM EXCEÇÃO):

1. DIREÇÃO DAS MENSAGENS NOS TICKETS:
   Ao receber mensagens do CRM, cada mensagem virá prefixada assim:
   - [LEAD]: texto → O CLIENTE/LEAD escreveu isso. É a voz do cliente.
   - [EMPRESA]: texto → A EMPRESA/ATENDENTE enviou isso. NÃO é o cliente falando.
   - [NOTA INTERNA]: texto → Nota interna da equipe, invisível ao lead.
   NUNCA confunda [EMPRESA] com mensagem do lead.
   Sempre leia todos os prefixos antes de tirar conclusões sobre o que o lead quer.

2. QUANDO ENVIAR MENSAGEM AO LEAD:
   - USE "enviar_mensagem_direta" ou "enviar_mensagem" SOMENTE quando o usuário pedir EXPLICITAMENTE:
     "responda ao lead", "envie uma mensagem", "contate o cliente", "mande para o número X".
   - Em NENHUMA outra situação envie mensagem ao lead por conta própria.

3. QUANDO USAR NOTA INTERNA (enviar_nota_interna):
   - Para TODA análise, qualificação, classificação, resumo, observação ou alerta de uso interno.
   - A nota interna NÃO aparece para o lead — é visível apenas para a equipe.

4. TRANSFERÊNCIA PARA HUMANO:
   - Use "devolver_para_fila" para devolver ticket a um atendente humano.
   - Avise ao usuário quando transferir.

5. ANÁLISE DE TICKETS:
   - Ao analisar tickets, primeiro chame "buscar_mensagens_ticket" para ver a conversa completa.
   - Use os prefixos [LEAD], [EMPRESA], [NOTA INTERNA] para entender quem disse o quê.
---"""

    system_prompt = user_system_prompt + MANDATORY_CRM_RULES

    nodes = [n for n in agent.get("nodes", []) if n.get("type") == "tool"]
    tool_defs = build_tool_definitions(nodes)

    # ── Carrega histórico da sessão do MongoDB ──────────────────────────────
    history = []
    if db is not None and session_id:
        try:
            doc = await db.chat_sessions.find_one(
                {"session_id": session_id, "agent_id": agent.get("agent_id")},
                {"_id": 0}
            )
            if doc:
                history = doc.get("history", [])
                # Mantém no máximo as últimas 20 trocas (40 mensagens) para não estourar o contexto
                if len(history) > 40:
                    history = history[-40:]
        except Exception as e:
            logger.warning(f"Erro ao carregar histórico da sessão {session_id}: {e}")

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_input},
    ]

    steps = []
    max_iterations = 8
    litellm.set_verbose = False

    for iteration in range(max_iterations):
        kwargs = {
            "model": f"{provider}/{model}",
            "messages": messages,
            "api_key": api_key,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tool_defs:
            kwargs["tools"] = tool_defs

        response = await litellm.acompletion(**kwargs)
        msg = response.choices[0].message

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            msg_dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]
            messages.append(msg_dict)

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    params = json.loads(tc.function.arguments)
                except Exception:
                    params = {}

                # Parse mcp_id__tool_name format
                if "__" in fn_name:
                    mcp_id, tool_name = fn_name.split("__", 1)
                else:
                    mcp_id, tool_name = "clickmassa", fn_name

                creds = workspace_creds.get(mcp_id, {})
                result = await execute_tool(mcp_id, tool_name, params, creds)

                steps.append({
                    "tool": fn_name,
                    "params": params,
                    "result": result,
                    "iteration": iteration,
                })
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                    "tool_call_id": tc.id,
                })
        else:
            final_output = msg.content or "Execução concluída sem resposta."

            # ── Salva histórico da sessão no MongoDB ────────────────────────
            if db is not None and session_id:
                try:
                    # Adiciona ao histórico: a mensagem do usuário + a resposta do agente
                    new_entries = [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": final_output},
                    ]
                    await db.chat_sessions.update_one(
                        {"session_id": session_id, "agent_id": agent.get("agent_id")},
                        {
                            "$push": {"history": {"$each": new_entries}},
                            "$set": {
                                "updated_at": datetime.now(timezone.utc),
                                "agent_id": agent.get("agent_id"),
                                "session_id": session_id,
                            },
                            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
                        },
                        upsert=True,
                    )
                except Exception as e:
                    logger.warning(f"Erro ao salvar histórico da sessão {session_id}: {e}")

            return final_output, steps

    return "Limite máximo de iterações atingido.", steps


# ── Workspace Routes ──────────────────────────────────────────────────────────

@agents_router.get("/workspace")
async def get_workspace(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    ws = await db.workspaces.find_one({"workspace_id": user["workspace_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    # Add stats
    ws["agent_count"] = await db.agents.count_documents({"workspace_id": user["workspace_id"]})
    ws["run_count"] = await db.runs.count_documents({"workspace_id": user["workspace_id"]})
    ws["credential_count"] = await db.credentials.count_documents({"workspace_id": user["workspace_id"]})
    return ws


@agents_router.put("/workspace")
async def update_workspace(request: Request, body: dict):
    user = await get_current_user(request)
    db = request.app.state.db
    allowed = {k: v for k, v in body.items() if k in ["name"]}
    await db.workspaces.update_one({"workspace_id": user["workspace_id"]}, {"$set": allowed})
    return {"message": "Workspace atualizado"}


@agents_router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    ws_id = user["workspace_id"]

    agents = await db.agents.find({"workspace_id": ws_id}, {"_id": 0}).to_list(100)
    agent_ids = [a["agent_id"] for a in agents]
    total_runs = await db.runs.count_documents({"agent_id": {"$in": agent_ids}}) if agent_ids else 0
    completed_runs = await db.runs.count_documents({"agent_id": {"$in": agent_ids}, "status": "completed"}) if agent_ids else 0
    recent_runs = await db.runs.find({"agent_id": {"$in": agent_ids}}, {"_id": 0}).sort("started_at", -1).to_list(5) if agent_ids else []

    agent_names = {a["agent_id"]: a["name"] for a in agents}
    for r in recent_runs:
        r["agent_name"] = agent_names.get(r["agent_id"], "Desconhecido")

    success_rate = round((completed_runs / total_runs * 100) if total_runs > 0 else 0, 1)

    # Per-agent usage metrics using MongoDB aggregation
    agent_metrics = []
    if agent_ids:
        try:
            pipeline = [
                {"$match": {"agent_id": {"$in": agent_ids}}},
                {"$group": {
                    "_id": "$agent_id",
                    "total_runs": {"$sum": 1},
                    "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                    "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                    "last_run": {"$max": "$started_at"},
                }},
            ]
            metrics_raw = await db.runs.aggregate(pipeline).to_list(200)
            metrics_by_id = {m["_id"]: m for m in metrics_raw}

            for a in agents:
                aid = a["agent_id"]
                m = metrics_by_id.get(aid, {})
                total = m.get("total_runs", 0)
                completed = m.get("completed", 0)
                agent_metrics.append({
                    "agent_id": aid,
                    "name": a.get("name", aid),
                    "status": a.get("status", "inactive"),
                    "total_runs": total,
                    "completed_runs": completed,
                    "failed_runs": m.get("failed", 0),
                    "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
                    "last_run": m.get("last_run"),
                })
        except Exception as e:
            logger.warning(f"Erro ao calcular métricas por agente: {e}")

    return {
        "total_agents": len(agents),
        "active_agents": sum(1 for a in agents if a.get("status") == "active"),
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "success_rate": success_rate,
        "recent_runs": recent_runs,
        "recent_agents": agents[:5],
        "agent_metrics": agent_metrics,  # Métricas detalhadas por agente
    }


# ── Webhook Trigger ───────────────────────────────────────────────────────────
# Permite que sistemas externos (CRM, n8n, Zapier, etc.) disparem agentes
# via HTTP POST sem autenticação JWT — usando um secret por agente.
#
# Uso:
#   POST /api/webhook/{agent_id}
#   Header: X-Webhook-Secret: <secret>
#   Body: {"input": "mensagem", "metadata": {...}}
#
# O campo webhook_secret é gerado automaticamente ao criar o agente se não
# fornecido. Pode ser rotacionado via PUT /api/agents/{agent_id}/webhook-secret.

class WebhookPayload(BaseModel):
    input: str
    metadata: Optional[dict] = None  # dados extras (ex: número de contato, tag do CRM)
    session_id: Optional[str] = None


@agents_router.post("/webhook/{agent_id}")
async def webhook_trigger(
    request: Request,
    agent_id: str,
):
    """
    Endpoint público para disparar agentes via webhook.
    Aceita o payload nativo do GapHub ou Webhooks nativos do ClickMassa (Evo).
    """
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    if agent.get("status") != "active":
        raise HTTPException(status_code=403, detail="Agente inativo — ative-o antes de usar webhooks")

    stored_secret = agent.get("webhook_secret", "")
    if not stored_secret:
        raise HTTPException(
            status_code=403,
            detail="Este agente não tem webhook configurado. Acesse Configurações do Agente para gerar um secret."
        )

    # 1. Validação de Autenticação Flexível (Suporta X-Webhook-Secret ou Authorization Bearer)
    auth_header = request.headers.get("Authorization", "")
    secret_header = request.headers.get("X-Webhook-Secret", "")
    token_provided = secret_header or auth_header.replace("Bearer ", "").strip()

    if not token_provided:
        # Se na plataforma CRM o usuário não passou Header, nós permitimos tentar parear
        # Caso contrário falha. No ClickMassa, o token vai no Header de Auth
        raise HTTPException(status_code=401, detail="Header de autenticação obrigatório")

    if not hmac.compare_digest(stored_secret, token_provided):
        raise HTTPException(status_code=401, detail="Webhook secret inválido")

    # 2. Parseamento de Payload Flexível
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo da requisição deve ser JSON válido")

    user_input = ""
    metadata = {}
    session_id = None

    # Detecta se é um Webhook Nativo ClickMassa Evo (Event: messages.upsert)
    if "event" in payload or "messages" in payload or "ticket" in payload:
        # ClickMassa/Z-API style payload
        # Exemplos comuns: Eventos de mensagem
        logger.info(f"Recebido Webhook externo CRM no Agente {agent_id}. Payload keys: {list(payload.keys())}")
        
        # Filtro de Loop Infinito: não processa mensagens enviadas por nós mesmos
        is_from_me = payload.get("fromMe", False) or payload.get("message", {}).get("fromMe", False)
        if is_from_me:
            return {"status": "ignored", "message": "Mensagem gerada pelo próprio sistema ignorada"}
        
        # Extrai a mensagem e meta
        if "body" in payload:
            user_input = payload["body"]
        elif "message" in payload and "body" in payload["message"]:
            user_input = payload["message"]["body"]
        elif "text" in payload:
            user_input = payload["text"]
            
        ticket_id = payload.get("ticketId") or payload.get("ticket", {}).get("id") or ""
        contact_id = payload.get("contactId") or payload.get("contact", {}).get("id") or ""
        
        metadata = {"crm_webhook": True, "ticket_id": ticket_id, "contact_id": contact_id}
        if ticket_id:
            session_id = f"webhook_{agent_id}_{ticket_id}"

    else:
        # Padrão nativo do GapHub
        user_input = payload.get("input", "")
        metadata = payload.get("metadata", {})
        session_id = payload.get("session_id")

    if not user_input:
        return {"status": "ignored", "message": "Nenhum input processável encontrado no payload do webhook."}

    # Carrega credenciais do workspace
    workspace_id = agent.get("workspace_id", "")
    workspace_creds = {}
    try:
        cred_docs = await db.credentials.find({"workspace_id": workspace_id}).to_list(50)
        for cred_doc in cred_docs:
            decrypted = {}
            for k, v in cred_doc.get("data", {}).items():
                try:
                    decrypted[k] = decrypt(str(v))
                except Exception:
                    decrypted[k] = v
            decrypted["workspace_id"] = workspace_id
            workspace_creds[cred_doc["mcp_id"]] = decrypted
    except Exception as e:
        logger.warning(f"Webhook: erro ao carregar credenciais do workspace {workspace_id}: {e}")

    try:
        agent_mcp_creds = await _get_agent_mcp_credentials(db, agent_id)
        if agent_mcp_creds:
            agent_mcp_creds["workspace_id"] = workspace_id
            workspace_creds["clickmassa"] = agent_mcp_creds
    except Exception as e:
        logger.warning(f"Webhook: erro ao carregar MCP credentials do agente {agent_id}: {e}")

    # Força contexto do CRM no prompt
    if metadata.get("ticket_id"):
        meta_str = json.dumps(metadata, ensure_ascii=False)
        user_input = (
            f"Mensagem recebida do lead via Webhook:\n"
            f"\"{user_input}\"\n\n"
            f"MISSÃO: Responda a este lead.\n"
            f"1. Se desejar usar ferramentas, você DEVE usar o ticket_id={metadata.get('ticket_id')} na ferramenta enviar_mensagem_direta e buscar_mensagens_ticket."
        )

    # Cria registro de run
    run_id = str(uuid.uuid4())
    session_id = session_id or f"webhook_{agent_id}_{run_id[:8]}"
    run_doc = {
        "run_id": run_id,
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "input": user_input,
        "metadata": metadata,
        "session_id": session_id,
        "status": "running",
        "source": "webhook",
        "started_at": datetime.now(timezone.utc),
    }
    await db.runs.insert_one(run_doc)

    # Executa agente em background (fire-and-forget)
    async def run_background():
        try:
            # CORREÇÃO BUG 1: execute_agent retorna tupla (output, steps), não dict.
            # Usar result.get() causava AttributeError silencioso que marcava o run como failed.
            output, steps = await execute_agent(agent, user_input, workspace_creds, db=db, session_id=session_id)
            await db.runs.update_one(
                {"run_id": run_id},
                {"$set": {
                    "status": "completed",
                    "output": output,
                    "steps": steps,
                    "completed_at": datetime.now(timezone.utc),
                }}
            )
        except Exception as e:
            logger.error(f"Webhook run {run_id} falhou: {e}")
            await db.runs.update_one(
                {"run_id": run_id},
                {"$set": {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc),
                }}
            )

    asyncio.create_task(run_background())

    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "session_id": session_id,
        "status": "queued",
        "message": "Agente disparado via webhook. Use GET /api/runs/{run_id} para acompanhar.",
    }


@agents_router.post("/agents/{agent_id}/webhook-secret")
async def rotate_webhook_secret(request: Request, agent_id: str):
    """
    Gera (ou rotaciona) o webhook secret do agente.
    Requer autenticação JWT normal.
    """
    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    new_secret = uuid.uuid4().hex + uuid.uuid4().hex  # 64 chars hex
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"webhook_secret": new_secret, "updated_at": datetime.now(timezone.utc)}}
    )

    return {
        "agent_id": agent_id,
        "webhook_secret": new_secret,
        "webhook_url": f"/api/webhook/{agent_id}",
        "message": "Secret gerado. Guarde-o com segurança — não será exibido novamente."
    }




# ── Lead Queue Auto-Processor ─────────────────────────────────────────────────
# NOVA FUNCIONALIDADE: Permite que o agente processe automaticamente todos os
# tickets pendentes do CRM sem precisar de intervenção manual.
#
# Uso via API:
#   POST /api/agents/{agent_id}/process-pending-leads
#
# Uso via agendamento automático (APScheduler — ver scheduler.py):
#   Crie um schedule com cron_expression="* * * * *" e
#   input_message="PROCESSAR_LEADS_PENDENTES" apontando para este agente.
#
# Uso via webhook do CRM (recomendado):
#   Configure o CRM para chamar POST /api/webhook/{agent_id} quando um novo
#   ticket entrar na fila pendente.

class PendingLeadsRequest(BaseModel):
    """Parâmetros opcionais para o processamento de leads pendentes."""
    max_leads: int = 10  # máximo de leads a processar por execução
    auto_respond: bool = True  # se True, o agente responde automaticamente


@agents_router.post("/agents/{agent_id}/process-pending-leads")
async def process_pending_leads(
    request: Request,
    agent_id: str,
    body: PendingLeadsRequest = None,
):
    """
    CORREÇÃO BUG 4 — Mecanismo de polling automático de leads pendentes.

    Este endpoint:
    1. Busca todos os tickets com status 'pending' no CRM via ClickMassa
    2. Para cada ticket, dispara o agente de IA em background
    3. O agente lê as mensagens do ticket, entende o contexto e responde automaticamente

    Pode ser chamado:
    - Manualmente pelo frontend
    - Via webhook do CRM quando um novo ticket fica pendente
    - Via APScheduler (cron) configurado para rodar a cada N minutos
    - Via Railway cron job (se configurado no railway.toml)
    """
    if body is None:
        body = PendingLeadsRequest()

    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    if agent.get("status") != "active":
        raise HTTPException(status_code=400, detail="Agente inativo — ative-o antes de processar leads")

    # Carrega credenciais (mesmo padrão do run_agent)
    workspace_creds = {}
    creds_list = await db.credentials.find({"workspace_id": user["workspace_id"]}, {"_id": 0}).to_list(50)
    for cred in creds_list:
        decrypted = {}
        for k, v in cred.get("data", {}).items():
            try:
                decrypted[k] = decrypt(str(v))
            except Exception:
                decrypted[k] = v
        decrypted["workspace_id"] = user["workspace_id"]
        workspace_creds[cred["mcp_id"]] = decrypted

    # Injeta credenciais MCP por agente
    agent_mcp_creds = await _get_agent_mcp_credentials(db, agent_id)
    if agent_mcp_creds:
        agent_mcp_creds["workspace_id"] = user["workspace_id"]
        workspace_creds["clickmassa"] = agent_mcp_creds

    # Dispara processamento em background (não bloqueia a resposta HTTP)
    async def process_leads_background():
        processed = 0
        errors = 0
        try:
            from tools import execute_tool
            # Busca tickets pendentes via ferramenta do CRM
            pending_result = await execute_tool(
                "clickmassa", "listar_tickets_pendentes", {}, workspace_creds.get("clickmassa", {})
            )

            tickets = pending_result.get("tickets", [])
            if isinstance(pending_result, list):
                tickets = pending_result

            logger.info(f"[PendingLeads] Agente {agent_id}: {len(tickets)} tickets pendentes encontrados")

            for ticket in tickets[:body.max_leads]:
                ticket_id = str(ticket.get("id", ""))
                contact = ticket.get("contact", {})
                contact_number = contact.get("number", "")
                contact_name = contact.get("name", contact_number)

                if not ticket_id:
                    continue

                # Evita processar o mesmo ticket múltiplas vezes
                # Verifica se já existe run recente para este ticket
                recent_run = await db.runs.find_one({
                    "agent_id": agent_id,
                    "metadata.ticket_id": ticket_id,
                    "status": {"$in": ["completed", "running"]},
                    "started_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=30)},
                })
                if recent_run:
                    logger.info(f"[PendingLeads] Ticket {ticket_id} já processado recentemente, pulando.")
                    continue

                # Monta input para o agente com contexto do lead
                last_msg = ticket.get("lastMessage", {})
                last_msg_body = last_msg.get("body", "") if last_msg else ""

                agent_input = (
                    f"Novo lead pendente na fila do CRM.\n"
                    f"Ticket ID: {ticket_id}\n"
                    f"Contato: {contact_name} ({contact_number})\n"
                    f"Última mensagem: {last_msg_body}\n\n"
                    f"Por favor:\n"
                    f"1. Use buscar_mensagens_ticket(ticket_id=\"{ticket_id}\") para ler a conversa completa\n"
                    f"2. Entenda o contexto e a necessidade do lead\n"
                    f"3. Responda ao lead de forma adequada usando enviar_mensagem_direta ou a ferramenta de mensagem disponível\n"
                    f"4. Se necessário, feche o ticket ou atribua a um atendente humano"
                )

                run_id = f"run_{uuid.uuid4().hex[:12]}"
                session_id = f"pending_{agent_id}_{ticket_id}"
                now = datetime.now(timezone.utc)

                run_doc = {
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "workspace_id": user["workspace_id"],
                    "user_id": "system_auto",
                    "session_id": session_id,
                    "status": "running",
                    "input": agent_input,
                    "output": None,
                    "steps": [],
                    "error": None,
                    "started_at": now,
                    "completed_at": None,
                    "source": "pending_leads_processor",
                    "metadata": {"ticket_id": ticket_id, "contact_number": contact_number},
                }
                await db.runs.insert_one(run_doc)

                try:
                    output, steps = await asyncio.wait_for(
                        execute_agent(agent, agent_input, workspace_creds, db, session_id),
                        timeout=90.0
                    )
                    await db.runs.update_one(
                        {"run_id": run_id},
                        {"$set": {
                            "status": "completed",
                            "output": output,
                            "steps": steps,
                            "completed_at": datetime.now(timezone.utc),
                        }}
                    )
                    processed += 1
                    logger.info(f"[PendingLeads] Ticket {ticket_id} processado com sucesso")
                except asyncio.TimeoutError:
                    await db.runs.update_one(
                        {"run_id": run_id},
                        {"$set": {
                            "status": "failed",
                            "error": "Timeout de 90s ao processar ticket",
                            "completed_at": datetime.now(timezone.utc),
                        }}
                    )
                    errors += 1
                except Exception as e:
                    await db.runs.update_one(
                        {"run_id": run_id},
                        {"$set": {
                            "status": "failed",
                            "error": str(e),
                            "completed_at": datetime.now(timezone.utc),
                        }}
                    )
                    errors += 1
                    logger.error(f"[PendingLeads] Erro ao processar ticket {ticket_id}: {e}")

        except Exception as e:
            logger.error(f"[PendingLeads] Erro geral no processamento: {e}")

        logger.info(f"[PendingLeads] Processamento concluído: {processed} sucesso, {errors} erros")

    asyncio.create_task(process_leads_background())

    return {
        "agent_id": agent_id,
        "status": "processing",
        "max_leads": body.max_leads,
        "message": f"Processamento de leads pendentes iniciado em background. Máximo: {body.max_leads} leads.",
    }


@agents_router.get("/agents/{agent_id}/process-pending-leads/status")
async def pending_leads_status(request: Request, agent_id: str):
    """Retorna estatísticas dos últimos processamentos automáticos de leads."""
    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    # Runs das últimas 24h com source=pending_leads_processor
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    runs = await db.runs.find({
        "agent_id": agent_id,
        "source": "pending_leads_processor",
        "started_at": {"$gte": cutoff},
    }, {"_id": 0}).sort("started_at", -1).to_list(50)

    return {
        "agent_id": agent_id,
        "runs_24h": len(runs),
        "completed": sum(1 for r in runs if r.get("status") == "completed"),
        "failed": sum(1 for r in runs if r.get("status") == "failed"),
        "recent_runs": runs[:10],
    }


@agents_router.get("/agents/{agent_id}/webhook-info")
async def get_webhook_info(request: Request, agent_id: str):
    """
    Retorna informações do webhook do agente (sem expor o secret).
    """
    user = await get_current_user(request)
    db = request.app.state.db

    agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": user["workspace_id"]})
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    has_secret = bool(agent.get("webhook_secret", ""))
    return {
        "agent_id": agent_id,
        "has_webhook": has_secret,
        "webhook_url": f"/api/webhook/{agent_id}" if has_secret else None,
        "status": agent.get("status"),
        "message": "Use POST /api/agents/{agent_id}/webhook-secret para gerar ou rotacionar o secret." if not has_secret else "Webhook ativo.",
    }

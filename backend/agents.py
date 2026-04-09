import os
import uuid
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from cryptography.fernet import Fernet, InvalidToken

from auth import get_current_user
from tools import execute_tool, build_tool_definitions

logger = logging.getLogger(__name__)

agents_router = APIRouter(prefix="/api")

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
try:
    fernet = Fernet(ENCRYPTION_KEY.encode())
except Exception:
    fernet = Fernet(Fernet.generate_key())


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

    # Get credentials
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

    # Save run as running
    run_doc = {
        "run_id": run_id,
        "agent_id": agent_id,
        "workspace_id": user["workspace_id"],
        "user_id": user["user_id"],
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
            execute_agent(agent, body.input, workspace_creds),
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


async def execute_agent(agent: dict, user_input: str, workspace_creds: dict):
    import litellm
    llm_config = agent.get("llm_config", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    api_key = llm_config.get("api_key") or os.environ.get("EMERGENT_LLM_KEY")
    system_prompt = llm_config.get("system_prompt", "Você é um assistente inteligente de CRM. Responda sempre em português.")
    temperature = float(llm_config.get("temperature", 0.7))
    max_tokens = int(llm_config.get("max_tokens", 4096))

    if not api_key:
        raise ValueError("API Key do LLM não configurada. Configure no nó LLM do agente.")

    nodes = [n for n in agent.get("nodes", []) if n.get("type") == "tool"]
    tool_defs = build_tool_definitions(nodes)

    messages = [
        {"role": "system", "content": system_prompt},
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

    return {
        "total_agents": len(agents),
        "active_agents": sum(1 for a in agents if a.get("status") == "active"),
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "success_rate": success_rate,
        "recent_runs": recent_runs,
        "recent_agents": agents[:5],
    }

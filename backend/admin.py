import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from auth import get_current_user

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/admin")


async def require_super_admin(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Acesso negado. Apenas super admins.")
    return user


@admin_router.get("/stats")
async def admin_stats(request: Request):
    await require_super_admin(request)
    db = request.app.state.db

    total_users = await db.users.count_documents({})
    total_workspaces = await db.workspaces.count_documents({})
    total_agents = await db.agents.count_documents({})
    total_runs = await db.runs.count_documents({})
    completed_runs = await db.runs.count_documents({"status": "completed"})
    failed_runs = await db.runs.count_documents({"status": "failed"})
    total_schedules = await db.schedules.count_documents({})
    active_schedules = await db.schedules.count_documents({"active": True})

    recent_users = await db.users.find(
        {}, {"_id": 0, "password_hash": 0}
    ).sort("created_at", -1).to_list(5)

    return {
        "total_users": total_users,
        "total_workspaces": total_workspaces,
        "total_agents": total_agents,
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "success_rate": round((completed_runs / total_runs * 100) if total_runs > 0 else 0, 1),
        "total_schedules": total_schedules,
        "active_schedules": active_schedules,
        "recent_users": recent_users,
    }


@admin_router.get("/tenants")
async def list_tenants(request: Request):
    await require_super_admin(request)
    db = request.app.state.db

    workspaces = await db.workspaces.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    result = []
    for ws in workspaces:
        owner = await db.users.find_one(
            {"user_id": ws.get("owner_id")}, {"_id": 0, "password_hash": 0}
        )
        ws["owner"] = owner or {}
        ws["agent_count"] = await db.agents.count_documents({"workspace_id": ws["workspace_id"]})
        ws["run_count"] = await db.runs.count_documents({"workspace_id": ws["workspace_id"]})
        ws["credential_count"] = await db.credentials.count_documents({"workspace_id": ws["workspace_id"]})
        ws["schedule_count"] = await db.schedules.count_documents({"workspace_id": ws["workspace_id"]})
        result.append(ws)
    return {"tenants": result}


@admin_router.get("/tenants/{workspace_id}")
async def get_tenant(request: Request, workspace_id: str):
    await require_super_admin(request)
    db = request.app.state.db

    ws = await db.workspaces.find_one({"workspace_id": workspace_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    owner = await db.users.find_one(
        {"user_id": ws.get("owner_id")}, {"_id": 0, "password_hash": 0}
    )
    ws["owner"] = owner or {}
    ws["agent_count"] = await db.agents.count_documents({"workspace_id": workspace_id})
    ws["run_count"] = await db.runs.count_documents({"workspace_id": workspace_id})
    agents = await db.agents.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(100)
    ws["agents"] = agents
    return ws


@admin_router.put("/tenants/{workspace_id}")
async def update_tenant(request: Request, workspace_id: str, body: dict):
    await require_super_admin(request)
    db = request.app.state.db

    allowed = {k: v for k, v in body.items() if k in ["plan", "name", "status"]}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar")
    allowed["updated_at"] = datetime.now(timezone.utc)
    result = await db.workspaces.update_one({"workspace_id": workspace_id}, {"$set": allowed})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")
    return {"message": "Tenant atualizado com sucesso"}


@admin_router.delete("/users/{user_id}")
async def delete_user(request: Request, user_id: str):
    admin = await require_super_admin(request)
    db = request.app.state.db

    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Não é possível excluir seu próprio usuário")

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    ws_id = user.get("workspace_id")
    agent_docs = await db.agents.find({"workspace_id": ws_id}, {"agent_id": 1}).to_list(200)
    agent_ids = [a["agent_id"] for a in agent_docs]

    if agent_ids:
        await db.runs.delete_many({"agent_id": {"$in": agent_ids}})
    await db.agents.delete_many({"workspace_id": ws_id})
    await db.credentials.delete_many({"workspace_id": ws_id})
    await db.schedules.delete_many({"workspace_id": ws_id})
    await db.workspaces.delete_one({"workspace_id": ws_id})
    await db.users.delete_one({"user_id": user_id})

    return {"message": f"Usuário {user.get('email', user_id)} e todos os dados excluídos"}

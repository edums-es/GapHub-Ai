"""
backend/workflows_api.py — Endpoints CRUD + sandbox para workflows.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from workflow_engine import execute_workflow, validate_workflow
from workflow_templates import WORKFLOW_TEMPLATES, get_template

logger = logging.getLogger(__name__)

workflows_router = APIRouter(prefix="/api/workflows", tags=["workflows"])
workflow_templates_router = APIRouter(prefix="/api/workflow-templates", tags=["workflows"])


# ═════════════════════════════════════════════════════════════════════════
# Schemas
# ═════════════════════════════════════════════════════════════════════════


class WorkflowNode(BaseModel):
    id: str
    type: str
    label: str = ""
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    config: Dict[str, Any] = Field(default_factory=dict)
    next: Optional[str] = None


class WorkflowPayload(BaseModel):
    name: str
    description: str = ""
    trigger_type: str = "webhook"
    nodes: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowTestRunPayload(BaseModel):
    input: str
    ticket_id: str = ""
    contact_number: str = ""
    contact_name: str = "Teste"
    contact_id: str = ""
    variables: Dict[str, Any] = Field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════


def _clean_workflow_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Converte ObjectId + datetime para JSON-serializable."""
    if not doc:
        return doc
    out = dict(doc)
    if "_id" in out:
        out.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ═════════════════════════════════════════════════════════════════════════
# CRUD
# ═════════════════════════════════════════════════════════════════════════


@workflows_router.get("")
async def list_workflows(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    items = await db.workflows.find({"workspace_id": workspace_id}).sort("created_at", -1).to_list(200)
    return {"workflows": [_clean_workflow_doc(i) for i in items]}


@workflows_router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    doc = await db.workflows.find_one({"workflow_id": workflow_id, "workspace_id": workspace_id})
    if not doc:
        raise HTTPException(404, "Workflow não encontrado")
    return _clean_workflow_doc(doc)


@workflows_router.post("")
async def create_workflow(
    payload: WorkflowPayload,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "workflow_id": workflow_id,
        "workspace_id": workspace_id,
        "created_by": current_user.get("email", ""),
        "name": payload.name,
        "description": payload.description,
        "trigger_type": payload.trigger_type,
        "nodes": payload.nodes,
        "created_at": now,
        "updated_at": now,
    }

    errors = validate_workflow(doc)
    if errors:
        raise HTTPException(400, detail={"message": "Workflow inválido", "errors": errors})

    await db.workflows.insert_one(doc)
    return _clean_workflow_doc(doc)


@workflows_router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowPayload,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    existing = await db.workflows.find_one({"workflow_id": workflow_id, "workspace_id": workspace_id})
    if not existing:
        raise HTTPException(404, "Workflow não encontrado")

    update = {
        "name": payload.name,
        "description": payload.description,
        "trigger_type": payload.trigger_type,
        "nodes": payload.nodes,
        "updated_at": datetime.now(timezone.utc),
    }

    # Valida antes de salvar (não bloqueia em caso de erro — usuário pode estar salvando rascunho)
    merged = {**existing, **update}
    errors = validate_workflow(merged)

    await db.workflows.update_one({"workflow_id": workflow_id}, {"$set": update})
    result = await db.workflows.find_one({"workflow_id": workflow_id})
    result_clean = _clean_workflow_doc(result) if result else {}
    result_clean["validation_errors"] = errors
    return result_clean


@workflows_router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    result = await db.workflows.delete_one({"workflow_id": workflow_id, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Workflow não encontrado")
    # Limpa link em agentes que referenciavam este workflow
    await db.agents.update_many(
        {"workspace_id": workspace_id, "workflow_id": workflow_id},
        {"$unset": {"workflow_id": ""}},
    )
    return {"status": "ok", "deleted": workflow_id}


# ═════════════════════════════════════════════════════════════════════════
# Sandbox — roda o workflow com input simulado (não envia mensagem de verdade)
# ═════════════════════════════════════════════════════════════════════════


@workflows_router.post("/{workflow_id}/test-run")
async def test_run_workflow(
    workflow_id: str,
    payload: WorkflowTestRunPayload,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    doc = await db.workflows.find_one({"workflow_id": workflow_id, "workspace_id": workspace_id})
    if not doc:
        raise HTTPException(404, "Workflow não encontrado")

    errors = validate_workflow(doc)
    if errors:
        return {"status": "invalid", "validation_errors": errors, "steps": []}

    # Mock tool executor — não envia nada de verdade
    async def mock_execute_tool(mcp_id: str, tool_name: str, params: Dict[str, Any], creds: Dict[str, Any]):
        return {
            "simulated": True,
            "mcp": mcp_id,
            "tool": tool_name,
            "params": params,
            "message": f"(sandbox) chamaria {mcp_id}.{tool_name}",
        }

    context = {
        "input": payload.input,
        "ticket_id": payload.ticket_id or "sandbox-ticket",
        "contact_id": payload.contact_id or "sandbox-contact",
        "contact_number": payload.contact_number or "5500000000000",
        "contact_name": payload.contact_name,
        "workspace_id": workspace_id,
        "variables": dict(payload.variables or {}),
        "steps": [],
        "output": "",
        "errors": [],
    }

    # Modelo default para LLM em sandbox: usa o que estiver configurado no workspace
    default_model = "openai/gpt-4o-mini"
    llm_kwargs: Dict[str, Any] = {}

    deps = {
        "execute_tool": mock_execute_tool,
        "workspace_creds": {},
        "default_model": default_model,
        "llm_kwargs": llm_kwargs,
    }

    result = await execute_workflow(doc, context, deps)
    return {
        "status": "ok",
        "workflow_id": workflow_id,
        "run_id": result.get("run_id"),
        "output": result.get("output", ""),
        "variables": result.get("variables", {}),
        "steps": result.get("steps", []),
        "errors": result.get("errors", []),
        "duration_ms": result.get("duration_ms"),
    }


# ═════════════════════════════════════════════════════════════════════════
# Criar workflow a partir de template
# ═════════════════════════════════════════════════════════════════════════


@workflows_router.post("/from-template/{template_id}")
async def create_from_template(
    template_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(404, f"Template '{template_id}' não existe")

    db = request.app.state.db
    workspace_id = current_user.get("workspace_id", "")
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "workflow_id": workflow_id,
        "workspace_id": workspace_id,
        "created_by": current_user.get("email", ""),
        "name": tmpl["name"],
        "description": tmpl["description"],
        "trigger_type": tmpl.get("trigger_type", "webhook"),
        "nodes": copy.deepcopy(tmpl["nodes"]),
        "template_id": template_id,
        "created_at": now,
        "updated_at": now,
    }

    await db.workflows.insert_one(doc)
    return _clean_workflow_doc(doc)


# ═════════════════════════════════════════════════════════════════════════
# Templates públicos (galeria)
# ═════════════════════════════════════════════════════════════════════════


@workflow_templates_router.get("")
async def list_workflow_templates(current_user: dict = Depends(get_current_user)):
    # Retorna só metadados (não os nós inteiros) para a galeria
    return {
        "templates": [
            {
                "template_id": t["template_id"],
                "name": t["name"],
                "description": t["description"],
                "trigger_type": t.get("trigger_type", "webhook"),
                "node_count": len(t.get("nodes", [])),
            }
            for t in WORKFLOW_TEMPLATES
        ]
    }


@workflow_templates_router.get("/{template_id}")
async def get_workflow_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
):
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(404, f"Template '{template_id}' não existe")
    return tmpl

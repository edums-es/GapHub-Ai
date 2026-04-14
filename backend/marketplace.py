"""
marketplace.py — Bug Fix #3: Marketplace migrado para MongoDB.

O MCP_CATALOG Python permanece como "catálogo base" de fallback e fonte de verdade
para instalações iniciais. Novos templates podem ser criados via API e ficam na
coleção `marketplace_templates` do MongoDB — sem necessidade de redeploy.

Prioridade de consulta: MongoDB > MCP_CATALOG Python (fallback).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

marketplace_router = APIRouter(prefix="/api/marketplace")

MCP_CATALOG = [
    {
        "id": "clickmassa",
        "name": "ClickMassa CRM",
        "description": "Controle total do seu CRM ClickMassa. Gerencie contatos, tickets, mensagens, automações e funis via IA.",
        "category": "crm",
        "icon": "database",
        "color": "#F97316",
        "status": "active",
        "version": "2.0",
        "author": "GapHub",
        "installs": 1240,
        "rating": 4.9,
        "credentials_required": ["base_url", "email", "password", "token"],
        "tools": [
            {"name": "buscar_contato_por_numero", "description": "Busca contato por número de WhatsApp"},
            {"name": "buscar_contato_por_id", "description": "Busca contato por ID interno"},
            {"name": "listar_contatos", "description": "Lista todos os contatos"},
            {"name": "criar_contato", "description": "Cria novo contato"},
            {"name": "atualizar_contato", "description": "Atualiza dados do contato"},
            {"name": "adicionar_etiquetas", "description": "Adiciona etiquetas ao contato"},
            {"name": "enviar_mensagem", "description": "Envia mensagem via push API (usa créditos)"},
            {"name": "enviar_mensagem_direta", "description": "Envia mensagem ao cliente sem consumir créditos Push. Prefira enviar o ticket_id ao invés do número para garantir o match exato — USE SOMENTE quando explícito."},
            {"name": "enviar_nota_interna", "description": "Adiciona nota interna no ticket usando o ticket_id ou número. Totalmente invisível para o lead."},
            {"name": "buscar_mensagens_ticket", "description": "Busca conversa completa de um ticket com direção de cada mensagem (fromMe: quem enviou cada mensagem)"},
            {"name": "listar_tickets_pendentes", "description": "Lista tickets na fila de espera"},
            {"name": "listar_tickets_abertos", "description": "Lista tickets em atendimento"},
            {"name": "fechar_ticket", "description": "Encerra atendimento"},
            {"name": "devolver_para_fila", "description": "Devolve ticket para fila de atendimento humano"},
            {"name": "listar_status_lead", "description": "Lista fases do funil de vendas"},
            {"name": "listar_origens_lead", "description": "Lista origens de leads"},
            {"name": "criar_tarefa", "description": "Cria tarefa, ligação ou compromisso"},
            {"name": "listar_tarefas", "description": "Lista tarefas agendadas"},
            {"name": "listar_conexoes_whatsapp", "description": "Lista canais de WhatsApp"},
            {"name": "listar_fluxos_chat", "description": "Lista chatbots nativos"},
            {"name": "atribuir_fluxo_chat", "description": "Ativa/desativa chatbot"},
            {"name": "listar_funis", "description": "Lista funis de follow-up"},
            {"name": "criar_funil", "description": "Cria funil de follow-up"},
            {"name": "atribuir_funil_contato", "description": "Insere lead em funil"},
        ],
    },
    {
        "id": "web_search",
        "name": "Busca na Web",
        "description": "Permite que a IA pesquise informações em tempo real na internet para enriquecer respostas.",
        "category": "search",
        "icon": "search",
        "color": "#3B82F6",
        "status": "active",
        "version": "1.0",
        "author": "GapHub",
        "installs": 890,
        "rating": 4.7,
        "credentials_required": [],
        "tools": [
            {"name": "buscar_web", "description": "Pesquisa na internet e retorna resultados relevantes"},
        ],
    },
    {
        "id": "http_request",
        "name": "HTTP Request",
        "description": "Faça requisições HTTP/REST para qualquer API externa. Ideal para integrações personalizadas.",
        "category": "developer",
        "icon": "globe",
        "color": "#8B5CF6",
        "status": "active",
        "version": "1.0",
        "author": "GapHub",
        "installs": 675,
        "rating": 4.8,
        "credentials_required": [],
        "tools": [
            {"name": "http_get", "description": "Requisição GET para uma URL"},
            {"name": "http_post", "description": "Requisição POST com payload JSON"},
        ],
    },
    {
        "id": "whatsapp_evolution",
        "name": "WhatsApp Evolution",
        "description": "Integração direta com WhatsApp via Evolution API. Envio de mensagens, mídia e gerenciamento de grupos.",
        "category": "communication",
        "icon": "message-circle",
        "color": "#10B981",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["api_url", "api_key", "instance_name"],
        "tools": [],
    },
    {
        "id": "google_calendar",
        "name": "Google Calendar",
        "description": "Crie eventos, consulte agendas e gerencie compromissos diretamente pelo agente de IA.",
        "category": "productivity",
        "icon": "calendar",
        "color": "#4285F4",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["oauth_token"],
        "tools": [],
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "description": "Envie, leia e organize emails diretamente pelo agente. Perfeito para automações de follow-up.",
        "category": "communication",
        "icon": "mail",
        "color": "#EA4335",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["oauth_token"],
        "tools": [],
    },
    {
        "id": "n8n_webhook",
        "name": "N8N Webhook",
        "description": "Dispare e receba webhooks do N8N para integrar com qualquer fluxo de automação existente.",
        "category": "automation",
        "icon": "zap",
        "color": "#FF6D00",
        "status": "active",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["webhook_url"],
        "tools": [],
    },
    {
        "id": "telegram_bot",
        "name": "Telegram Bot",
        "description": "Conecte o agente ao Telegram para receber comandos e enviar notificações automáticas.",
        "category": "communication",
        "icon": "send",
        "color": "#2AABEE",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["bot_token"],
        "tools": [],
    },
    {
        "id": "stripe",
        "name": "Stripe Payments",
        "description": "Consulte pagamentos, crie links de pagamento e gerencie assinaturas via IA.",
        "category": "finance",
        "icon": "credit-card",
        "color": "#635BFF",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["api_key"],
        "tools": [],
    },
    {
        "id": "github",
        "name": "GitHub",
        "description": "Gerencie repositórios, issues e pull requests diretamente pelo agente de IA.",
        "category": "developer",
        "icon": "github",
        "color": "#ffffff",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["access_token"],
        "tools": [],
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Envie mensagens, leia canais e responda notificações no Slack com agentes autônomos.",
        "category": "communication",
        "icon": "hash",
        "color": "#4A154B",
        "status": "coming_soon",
        "version": "1.0",
        "author": "GapHub",
        "installs": 0,
        "rating": 0,
        "credentials_required": ["bot_token", "channel_id"],
        "tools": [],
    },
]

CATEGORIES = [
    {"id": "all", "label": "Todos"},
    {"id": "crm", "label": "CRM"},
    {"id": "communication", "label": "Comunicação"},
    {"id": "productivity", "label": "Produtividade"},
    {"id": "automation", "label": "Automação"},
    {"id": "developer", "label": "Developer"},
    {"id": "finance", "label": "Finanças"},
    {"id": "search", "label": "Busca"},
]


# ── Pydantic models para CRUD de templates no MongoDB ────────────────────────

class TemplateCreate(BaseModel):
    id: str
    name: str
    description: str
    category: str
    icon: Optional[str] = "zap"
    color: Optional[str] = "#F97316"
    status: Optional[str] = "active"
    version: Optional[str] = "1.0"
    author: Optional[str] = "GapHub"
    credentials_required: Optional[list] = []
    tools: Optional[list] = []


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    tools: Optional[list] = None
    active: Optional[bool] = None


async def _get_db(request: Request):
    return request.app.state.db


async def _load_all_templates(db) -> list:
    """
    Combina MCP_CATALOG (Python) com templates do MongoDB.
    Templates do MongoDB com mesmo id sobrescrevem o catálogo base (override).
    Isso permite atualizar integrações sem redeploy.
    """
    # Base: catálogo Python
    catalog = {m["id"]: dict(m) for m in MCP_CATALOG}

    # Overlay: templates do MongoDB (novos ou overrides)
    try:
        db_templates = await db.marketplace_templates.find(
            {}, {"_id": 0}
        ).to_list(500)
        for tmpl in db_templates:
            catalog[tmpl["id"]] = tmpl
    except Exception:
        pass  # MongoDB indisponível — usa só catálogo Python

    return list(catalog.values())


# ── Endpoints de leitura ─────────────────────────────────────────────────────

@marketplace_router.get("")
async def list_mcps(request: Request, category: str = "all", search: str = ""):
    db = await _get_db(request)
    items = await _load_all_templates(db)
    if category != "all":
        items = [m for m in items if m.get("category") == category]
    if search:
        s = search.lower()
        items = [m for m in items if s in m.get("name", "").lower() or s in m.get("description", "").lower()]
    return {"mcps": items, "categories": CATEGORIES, "total": len(items)}


@marketplace_router.get("/templates")
async def list_templates(request: Request, category: str = "all"):
    """Lista apenas templates armazenados no MongoDB (excluindo catálogo Python base)."""
    db = await _get_db(request)
    query = {} if category == "all" else {"category": category}
    templates = await db.marketplace_templates.find(query, {"_id": 0}).to_list(500)
    return {"templates": templates, "total": len(templates)}


@marketplace_router.get("/{mcp_id}")
async def get_mcp(request: Request, mcp_id: str):
    db = await _get_db(request)
    # Tenta MongoDB primeiro
    try:
        tmpl = await db.marketplace_templates.find_one({"id": mcp_id}, {"_id": 0})
        if tmpl:
            return tmpl
    except Exception:
        pass
    # Fallback: catálogo Python
    mcp = next((m for m in MCP_CATALOG if m["id"] == mcp_id), None)
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP não encontrado")
    return mcp


# ── Endpoints de escrita (CRUD) ───────────────────────────────────────────────

@marketplace_router.post("/templates")
async def create_template(request: Request, body: TemplateCreate):
    """Cria novo template de agente/integração no MongoDB — sem redeploy."""
    db = await _get_db(request)
    existing = await db.marketplace_templates.find_one({"id": body.id})
    if existing:
        raise HTTPException(status_code=409, detail=f"Template com id '{body.id}' já existe. Use PUT para atualizar.")
    doc = body.model_dump()
    doc["active"] = True
    doc["installs"] = 0
    doc["rating"] = 0
    doc["created_at"] = datetime.now(timezone.utc)
    doc["updated_at"] = datetime.now(timezone.utc)
    await db.marketplace_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@marketplace_router.put("/templates/{mcp_id}")
async def update_template(request: Request, mcp_id: str, body: TemplateUpdate):
    """Atualiza template existente no MongoDB."""
    db = await _get_db(request)
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc)
    result = await db.marketplace_templates.update_one(
        {"id": mcp_id}, {"$set": update}, upsert=False
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado no banco. Use POST para criar.")
    tmpl = await db.marketplace_templates.find_one({"id": mcp_id}, {"_id": 0})
    return tmpl


@marketplace_router.delete("/templates/{mcp_id}")
async def delete_template(request: Request, mcp_id: str):
    """Remove template do MongoDB (não afeta catálogo Python base)."""
    db = await _get_db(request)
    result = await db.marketplace_templates.delete_one({"id": mcp_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado no banco.")
    return {"message": f"Template '{mcp_id}' removido com sucesso."}

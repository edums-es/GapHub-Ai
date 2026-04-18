import os
import re
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


# ─────────────────────────────────────────────────────────────────────────────
# Agent runtime helpers — anti-loop, dialogue sanitization, prompt rules.
# Shared by both execute_agent (sync) and execute_agent_streaming_queue (stream).
# ─────────────────────────────────────────────────────────────────────────────

# Regex that matches hallucinated dialogue markers the LLM sometimes emits when
# it starts simulating the lead responding to itself. We cut the text at the
# FIRST occurrence of any of these patterns, keeping only the genuine reply.
_DIALOGUE_MARKER_RE = re.compile(
    r"(?im)^\s*(?:"
    r"\[LEAD\]|\[EMPRESA\]|\[NOTA INTERNA\]|"
    r"Lead|Cliente|Usu[aá]rio|User|"
    r"Agente|Atendente|Assistant|Bot|IA|AI"
    r")\s*:"
)


def _sanitize_agent_text(text: Optional[str]) -> str:
    """
    Strip hallucinated dialogue from LLM output.

    If the LLM replies with something like:
        "Olá João!\n\nLead: Tudo bem?\nAgente: Sim!"
    we return only "Olá João!" — everything after the first dialogue marker is
    hallucinated self-dialogue and must not be sent to the real lead.
    """
    if not text:
        return ""
    m = _DIALOGUE_MARKER_RE.search(text)
    if m:
        text = text[: m.start()]
    return text.strip()


# Mandatory CRM behavior rules appended to every agent's system prompt.
# Promoted to module level so both execute_agent and the streaming variant share
# the same safety rails.
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

2. OBRIGATÓRIO: USAR TOOLS QUANDO AÇÕES FOREM SOLICITADAS:
   Se o lead SOLICITAR qualquer ação, você DEVE usar a ferramenta apropriada:
   - "quero agendar uma call/reunião" → Use "criar_tarefa" para criar lembrete
   - "me lembra de algo" → Use "criar_tarefa"
   - "quem é você?" → Responda normalmente, sem tool necessária
   - "vou passar o contato" → Use "atualizar_contato" para adicionar info
   - Quando não souber → Use "devolver_para_fila" para transferir para humano
   
   Ao usar ferramentas:
   - Use APENAS APÓS entender a solicitação completa
   - NUNCA promises sem usar tool ("vou agendar" sem criar tarefa = NÃO有效!)
   - Use "enviar_nota_internal" para registrar contexto da ação

3. QUANDO ENVIAR MENSAGEM AO LEAD:
   - Se o input começar com "[WEBHOOK AUTOMÁTICO — RESPOSTA OBRIGATÓRIA]":
     * Use "enviar_mensagem" ou "enviar_mensagem_direta" EXATAMENTE UMA VEZ.
     * O sistema adiciona automaticamente fromMe=True para registrar como mensagem da empresa.
     * APÓS enviar, PARE COMPLETAMENTE. Não faça mais nenhuma chamada de ferramenta.
     * DON'T use "buscar_mensagens_ticket" — a mensagem já está no input.
     * NÃO simule o lead respondendo. NÃO continue a conversa sozinho.
     * Resposta em UMA mensagem, encerrada.
   - Em outros contextos, use "enviar_mensagem_direta" SOMENTE quando explicitamente pedido.
   - NUNCA envie mensagens múltiplas em sequência sem o lead terRespondido entre elas.
   - NUNCA escreva diálogos fictícios como "Lead: ...", "Cliente: ...", "Agente: ..." dentro
     do texto da mensagem. Envie APENAS sua resposta direta, em primeira pessoa.

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


# Tools that are blocked in webhook mode: if we already have the lead's message
# in the payload, re-fetching ticket history just lets the agent see its own
# prior reply and answer itself. Any tool that lets the LLM "look at other
# tickets" is blocked — the agent must stay strictly scoped to the ticket
# that triggered the webhook.
#
# Nota: enviar_mensagem e enviar_mensagem_direta agora usam fromMe=True automaticamente,
# então ambas podem ser usadas em webhook mode.
WEBHOOK_BLOCKED_TOOLS = {
    # Listagem/busca de mensagens ou outros tickets (fuga de escopo)
    "buscar_mensagens_ticket",
    "listar_tickets_pendentes",
    "listar_tickets_abertos",
    "listar_tickets",
    "buscar_tickets",
    "buscar_ticket_por_id",
    "buscar_contato_por_numero",
    "buscar_contato_por_id",
    "listar_contatos",
    "get_messages",
    "list_messages",
    # MCP-namespaced variants (clickmassa__*)
    "clickmassa__buscar_mensagens_ticket",
    "clickmassa__listar_tickets_pendentes",
    "clickmassa__listar_tickets_abertos",
    "clickmassa__listar_tickets",
    "clickmassa__buscar_tickets",
    "clickmassa__buscar_ticket_por_id",
    "clickmassa__buscar_contato_por_numero",
    "clickmassa__buscar_contato_por_id",
    "clickmassa__listar_contatos",
}


# ── MANDATORY_CRM_RULES variant for webhook mode ──────────────────────────────
# The default rules reference tools like buscar_mensagens_ticket that are blocked
# in webhook mode. Using the default prompt creates a contradiction (prompt says
# "use buscar_mensagens_ticket" but the tool is absent). This slim version is
# self-consistent with the tool allow-list.
MANDATORY_CRM_RULES_WEBHOOK = """

---
REGRAS OBRIGATÓRIAS — MODO WEBHOOK (SEMPRE SIGA, SEM EXCEÇÃO):

1. ESCOPO ÚNICO: Você está respondendo a UM ÚNICO ticket.
   O ticket_id e o número do lead estão no input.
   ticket_id = {}

2. FLUXO DE AÇÃO (OBRIGATÓRIO):
   QUANDO O LEAD PEDIR ALGO, SIGA ESTES PASSOS:
   
   PASSO 1: O lead pediu algo? (agendar, lembrar, passar dado)
   PASSO 2: Qual tool usar?
     - "agendar call/reunião" → criar_tarefa
     - "me lembra de algo" → criar_tarefa  
     - "passar email/telefone" → atualizar_contato
     - "não consigo fazer" → devolver_para_fila
   PASSO 3: Execute a tool PRIMEIRO
   PASSO 4: Depois envie mensagem ao lead confirmando
   
   EXEMPLO CORRETO:
   Lead: "Quero agendar uma call"
   → criar_tarefa(tipo="C", titulo="Call com [nome]", data="amanhã")
   → enviar_mensagem("Perfeito! Agendei a call para amanhã às 10h. Um atendente vai confirmar os detalhes.")

   EXEMPLO ERRADO:
   Lead: "Quero agendar uma call"
   → "Claro, vou agendar!" (SEM USAR criar_tarefa) ← ERRADO!

3. FERRAMENTAS DISPONÍVEIS (USE!):
   - criar_tarefa: para criar tarefas, ligações, compromissos
   - atualizar_contato: para atualizar dados do lead
   - enviar_nota_interna: para registrar contexto internal
   - devolver_para_fila: para transferir para atendente humano
   - enviar_mensagem: para responder ao lead (fromMe=True automático)

4. ENVIO DE MENSAGEM: Após executar qualquer action tool,
   use enviar_mensagem para confirmar ao lead.

5. REGISTRE AÇÕES: Sempre use enviar_nota_interna para documentar
   o que você fez (criou tarefa, atualizou contato, etc).
---"""


def _enforce_ticket_scope(
    fn_name: str,
    params: dict,
    allowed_ticket_id: str,
    allowed_numero: str,
) -> tuple:
    """
    Em webhook_mode, valida que tools de envio/ação só operam no ticket/número
    que disparou o webhook. Retorna (fn_name_final, params_ajustados, erro_dict_ou_None).

    Comportamento:
      - Se params traz ticket_id diferente do esperado → retorna erro (blocked).
      - Se params traz numero/phone diferente do esperado → retorna erro.
      - Se não trouxer, injeta o valor correto (LLM às vezes esquece).
      - Tools que não são de envio passam inalteradas.

    Nota: ambas as ferramentas (enviar_mensagem e enviar_mensagem_direta) agora usam
    fromMe=True automaticamente, então não há mais problema de direção.
    """
    bare = fn_name.split("__", 1)[1] if "__" in (fn_name or "") else (fn_name or "")
    
    # Tools sensíveis ao escopo do ticket
    scoped_tools = {
        "enviar_mensagem", "enviar_mensagem_direta", "enviar_midia",
        "enviar_nota_interna", "fechar_ticket", "devolver_para_fila",
    }
    if bare not in scoped_tools:
        return fn_name, params, None

    out = dict(params or {})

    if allowed_ticket_id:
        provided_tid = str(out.get("ticket_id") or "").strip()
        if provided_tid and provided_tid != str(allowed_ticket_id):
            return fn_name, out, {
                "error": (
                    f"TICKET FORA DE ESCOPO: você tentou operar no ticket_id={provided_tid}, "
                    f"mas o webhook só permite responder no ticket_id={allowed_ticket_id}. "
                    f"Chamada REJEITADA. Encerre a resposta imediatamente."
                ),
                "blocked": True,
                "scope_violation": True,
            }
        # Injeta ticket_id quando ausente — o LLM às vezes esquece, e a tool precisa.
        if not provided_tid:
            out["ticket_id"] = str(allowed_ticket_id)
            logger.info(f"[enforce_ticket_scope] injetando ticket_id={allowed_ticket_id}")

    if allowed_numero:
        for key in ("numero", "number", "phone", "phone_number"):
            provided_num = str(out.get(key) or "").strip()
            if provided_num and provided_num != str(allowed_numero):
                return fn_name, out, {
                    "error": (
                        f"NÚMERO FORA DE ESCOPO: você tentou enviar para {key}={provided_num}, "
                        f"mas o webhook só permite responder ao número {allowed_numero}. "
                        f"Chamada REJEITADA. Encerre a resposta imediatamente."
                    ),
                    "blocked": True,
                    "scope_violation": True,
                }
        # Injeta número se necessário
        if bare in ("enviar_mensagem", "enviar_mensagem_direta") and not any(out.get(k) for k in ("numero", "number", "phone", "phone_number")):
            if allowed_numero:
                out["numero"] = str(allowed_numero)
                logger.info(f"[enforce_ticket_scope] injetando numero={allowed_numero}")

    return fn_name, out, None


def _extract_webhook_fields(payload: dict) -> dict:
    """
    Extrai os campos relevantes do payload do webhook — normalizando entre formatos
    de CRMs diferentes. Função pura (sem side effects) para ser testável.

    Fontes suportadas:
      - ClickMassa: dados aninhados em payload["message"] (ticketId, contactId, body, fromMe).
      - Chatwoot: dados em payload["data"] (conversation, sender, content).
      - Payloads planos: campos direto no root do payload.

    Retorna dict com: user_input, ticket_id, contact_number, contact_name,
    contact_id, from_me, is_private, msg_type, msg_id, ticket_status,
    ticket_obj, data_wrap, msg_obj.
    """
    payload = payload or {}
    data_wrap = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    msg_obj = payload.get("message") or data_wrap.get("message") or {}
    if not isinstance(msg_obj, dict):
        msg_obj = {}
    # ClickMassa ANINHA o ticket completo (com contato e status) dentro de
    # payload.message.ticket. Procurar lá primeiro, depois os formatos antigos.
    ticket_obj = (
        msg_obj.get("ticket")              # ← ClickMassa (caminho principal)
        or payload.get("ticket")
        or data_wrap.get("ticket")
        or data_wrap.get("conversation")
        or {}
    )
    if not isinstance(ticket_obj, dict):
        ticket_obj = {}
    # O contato também vem em ticket.contact (ClickMassa) — isso dá o número
    # do WhatsApp do lead, que é OBRIGATÓRIO para enviar_mensagem_direta.
    contact_obj = (
        ticket_obj.get("contact")          # ← ClickMassa (ticket.contact.number)
        or payload.get("contact")
        or data_wrap.get("contact")
        or data_wrap.get("sender")
        or msg_obj.get("contact")
        or {}
    )
    if not isinstance(contact_obj, dict):
        contact_obj = {}

    # from_me
    sender_obj = data_wrap.get("sender") if isinstance(data_wrap.get("sender"), dict) else {}
    sender_type = (
        sender_obj.get("type", "")
        or payload.get("senderType", "")
        or payload.get("authorType", "")
        or ""
    )
    from_me = bool(
        payload.get("fromMe")
        or msg_obj.get("fromMe")
        or data_wrap.get("fromMe")
        or (data_wrap.get("message_type") in ("outgoing", 1))
        or (str(data_wrap.get("message_type", "")).lower() == "outgoing")
        or (str(sender_type).lower() in ("agent", "agent_bot", "bot", "system"))
        or payload.get("isFromBot")
        or payload.get("isBot")
    )
    is_private = bool(
        payload.get("isPrivate")
        or msg_obj.get("isPrivate")
        or data_wrap.get("private")
    )
    msg_type = (
        payload.get("messageType")
        or msg_obj.get("messageType")
        or msg_obj.get("type")
        or data_wrap.get("message_type")
        or "chat"
    )
    if str(msg_type).lower() == "notification":
        is_private = True

    # user_input
    user_input = (
        msg_obj.get("body")
        or payload.get("body")
        or data_wrap.get("content")
        or data_wrap.get("body")
        or payload.get("text")
        or data_wrap.get("text")
        or payload.get("input")
        or ""
    )
    if isinstance(user_input, str):
        user_input = user_input.strip()

    # ticket_id — ClickMassa aninha dentro de message
    raw_ticket_id = (
        msg_obj.get("ticketId")
        or msg_obj.get("ticket_id")
        or payload.get("ticketId")
        or payload.get("ticket_id")
        or ticket_obj.get("id")
        or data_wrap.get("ticketId")
        or data_wrap.get("ticket_id")
    )
    ticket_id = str(raw_ticket_id) if raw_ticket_id is not None else ""
    if ticket_id in ("None", "null", "0", ""):
        ticket_id = ""

    # contact info
    contact_number = str(
        contact_obj.get("number")
        or contact_obj.get("phone")
        or contact_obj.get("phone_number")
        or msg_obj.get("number")
        or msg_obj.get("phone")
        or payload.get("contactNumber")
        or payload.get("numero")
        or sender_obj.get("phone_number")
        or ""
    ).strip()
    contact_name = str(
        contact_obj.get("name")
        or msg_obj.get("contactName")
        or payload.get("contactName")
        or sender_obj.get("name")
        or ""
    ).strip()
    contact_id = str(
        contact_obj.get("id")
        or msg_obj.get("contactId")
        or payload.get("contactId")
        or ""
    )

    # msg_id
    msg_id = str(
        msg_obj.get("id")
        or payload.get("messageId")
        or payload.get("id")
        or data_wrap.get("id")
        or ""
    ).strip()

    # ticket_status — várias fontes
    _ticket_user = ticket_obj.get("user") if isinstance(ticket_obj.get("user"), dict) else {}
    ticket_status = str(
        ticket_obj.get("status")
        or ticket_obj.get("state")
        or data_wrap.get("status")
        or ""
    ).strip().lower()

    return {
        "user_input": user_input,
        "ticket_id": ticket_id,
        "contact_number": contact_number,
        "contact_name": contact_name,
        "contact_id": contact_id,
        "from_me": from_me,
        "is_private": is_private,
        "msg_type": msg_type,
        "sender_type": sender_type,
        "msg_id": msg_id,
        "ticket_status": ticket_status,
        "ticket_obj": ticket_obj,
        "data_wrap": data_wrap,
        "msg_obj": msg_obj,
        "_ticket_user": _ticket_user,
    }


_WEBHOOK_PREFIX_RE = re.compile(
    r"^\[WEBHOOK AUTOMÁTICO — RESPOSTA OBRIGATÓRIA\]\s*\n"
    r"Mensagem recebida do lead via CRM:\s*\n\"(.*?)\"",
    re.DOTALL,
)


def _extract_clean_user_input(user_input: str) -> str:
    """Strip the webhook orchestration envelope, returning the raw lead message."""
    if not user_input:
        return ""
    m = _WEBHOOK_PREFIX_RE.search(user_input)
    if m:
        return m.group(1).strip()
    return user_input.strip()


def _is_send_tool(fn_name: str) -> bool:
    """True if the tool call sends a visible message to the lead (not an internal note)."""
    if not fn_name:
        return False
    # Strip mcp_id__ prefix if present.
    bare = fn_name.split("__", 1)[1] if "__" in fn_name else fn_name
    # enviar_nota_interna does NOT count — it's invisible to the lead.
    return bare.startswith("enviar_mensagem") or bare.startswith("enviar_midia")


def _compose_skill_prompt(agent: dict) -> str:
    """Concatena os prompt fragments dos skill packs habilitados no agente."""
    try:
        from skill_packs import compose_packs_prompt
    except Exception:
        return ""
    pack_ids = (agent or {}).get("enabled_skill_packs", []) or []
    return compose_packs_prompt(pack_ids)

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
    enabled_skill_packs: Optional[List[str]] = None


class SkillPacksUpdate(BaseModel):
    enabled_skill_packs: List[str]


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


# ── Skill Packs Routes ────────────────────────────────────────────────────────
# Packs são "nós condicionados": conjuntos curados de tools + prompt fragment.
# O cliente marca os packs desejados no agente; isso determina que tools o LLM
# enxerga e que papel ele adota. Livre de DB — o catálogo vive em skill_packs.py.

@agents_router.get("/skill-packs")
async def list_skill_packs(request: Request):
    """Lista todos os skill packs disponíveis. Auth obrigatória."""
    await get_current_user(request)
    from skill_packs import list_packs_public
    packs = list_packs_public()
    return {"packs": packs, "total": len(packs)}


@agents_router.get("/agents/{agent_id}/skill-packs")
async def get_agent_skill_packs(request: Request, agent_id: str):
    """Retorna os packs habilitados para o agente + metadata do catálogo."""
    user = await get_current_user(request)
    db = request.app.state.db
    agent = await db.agents.find_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    from skill_packs import list_packs_public, get_pack
    enabled_ids = agent.get("enabled_skill_packs", []) or []
    enabled = []
    for pid in enabled_ids:
        p = get_pack(pid)
        if p:
            # serializa sem o prompt interno
            enabled.append({k: v for k, v in p.items() if k != "prompt"})
    return {
        "agent_id": agent_id,
        "enabled_skill_packs": enabled_ids,
        "enabled_details": enabled,
        "available": list_packs_public(),
    }


@agents_router.put("/agents/{agent_id}/skill-packs")
async def update_agent_skill_packs(request: Request, agent_id: str, body: SkillPacksUpdate):
    """Define quais skill packs estão habilitados para este agente."""
    user = await get_current_user(request)
    db = request.app.state.db

    from skill_packs import get_pack
    unknown = [pid for pid in body.enabled_skill_packs if not get_pack(pid)]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Skill pack(s) desconhecido(s): {unknown}",
        )

    result = await db.agents.update_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]},
        {
            "$set": {
                "enabled_skill_packs": body.enabled_skill_packs,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    agent = await db.agents.find_one(
        {"agent_id": agent_id, "workspace_id": user["workspace_id"]}, {"_id": 0}
    )
    return {"agent": agent, "enabled_skill_packs": body.enabled_skill_packs}


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
    agent: dict,
    user_input: str,
    workspace_creds: dict,
    db=None,
    session_id: str = None,
    run_id: str = None,
    queue: asyncio.Queue = None,
    webhook_mode: bool = False,
    original_input_for_history: Optional[str] = None,
) -> tuple:
    """
    Streaming REAL com asyncio.Queue — mesmas proteções anti-loop do execute_agent.
    Envia eventos token a token e tool_start/tool_done para a queue.
    Retorna (output_completo, steps) ao final.
    """
    import litellm
    llm_config = agent.get("llm_config", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    api_key = llm_config.get("api_key") or os.environ.get("EMERGENT_LLM_KEY")
    user_system_prompt = llm_config.get(
        "system_prompt", "Você é um assistente inteligente de CRM."
    )
    temperature = float(llm_config.get("temperature", 0.7))
    max_tokens = int(llm_config.get("max_tokens", 4096))

    if not api_key:
        raise ValueError("API Key do LLM não configurada.")

    # Apply the same skill-pack + CRM-rules prompt composition as execute_agent
    skill_prompt = _compose_skill_prompt(agent)
    system_prompt = user_system_prompt + skill_prompt + MANDATORY_CRM_RULES

    nodes = [n for n in agent.get("nodes", []) if n.get("type") == "tool"]
    tool_defs = build_tool_definitions(nodes, agent=agent)
    
    # Se NENHUMA tool disponível (sem nodes, sem skill packs), adiciona as tools padrão do ClickMassa
    if not tool_defs:
        from tools import CLICKMASSA_DEFAULT_TOOLS
        tool_defs = CLICKMASSA_DEFAULT_TOOLS
        logger.info(f"[execute_agent_streaming] usando tools padrão do ClickMassa: {len(tool_defs)} tools")

    if webhook_mode:
        before = len(tool_defs)
        tool_defs = [
            t for t in tool_defs
            if t.get("function", {}).get("name", "") not in WEBHOOK_BLOCKED_TOOLS
        ]
        logger.info(
            f"[execute_agent_streaming webhook_mode] tools: {before} → {len(tool_defs)}"
        )

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

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_input},
    ]
    steps: List[dict] = []
    max_iterations = 8
    litellm.set_verbose = False
    _message_sent = False
    _sent_text_to_lead: Optional[str] = None
    final_output = ""

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
            if webhook_mode:
                kwargs["tool_choice"] = "required"

        chunks = []
        tool_calls_raw = {}

        try:
            stream = await litellm.acompletion(**kwargs)
        except Exception as e:
            if "tool_choice" in kwargs and "tool_choice" in str(e).lower():
                logger.warning(
                    f"[execute_agent_streaming] provider rejeitou tool_choice, retry sem: {e}"
                )
                kwargs.pop("tool_choice", None)
                stream = await litellm.acompletion(**kwargs)
            else:
                raise

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            if delta.content:
                chunks.append(delta.content)
                await _emit({"type": "token", "text": delta.content})
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
            messages.append({
                "role": "assistant",
                "content": _sanitize_agent_text(full_content),
                "tool_calls": [
                    {"id": v["id"], "type": "function",
                     "function": {"name": v["name"], "arguments": v["arguments"]}}
                    for v in tool_calls_raw.values()
                ],
            })

            for v in tool_calls_raw.values():
                fn_name = v["name"] or ""
                try:
                    params = json.loads(v["arguments"] or "{}")
                except Exception:
                    params = {}
                mcp_id, tool_name = fn_name.split("__", 1) if "__" in fn_name else ("clickmassa", fn_name)

                is_send = _is_send_tool(fn_name)

                if is_send and _message_sent:
                    blocked = {
                        "error": "ENVIO DUPLICADO BLOQUEADO: já foi enviada 1 mensagem nesta execução.",
                        "blocked": True,
                    }
                    steps.append({
                        "tool": fn_name, "params": params, "result": blocked,
                        "iteration": iteration, "blocked": True,
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(blocked, ensure_ascii=False),
                        "tool_call_id": v["id"],
                    })
                    await _emit({"type": "tool_done", "tool": fn_name, "result": blocked})
                    continue

                if is_send:
                    for key in ("mensagem", "message", "body", "text", "texto"):
                        if key in params and isinstance(params[key], str):
                            params[key] = _sanitize_agent_text(params[key])

                creds = workspace_creds.get(mcp_id, {})
                await _emit({"type": "tool_start", "tool": fn_name, "params": params})

                result = await execute_tool(mcp_id, tool_name, params, creds)
                steps.append({
                    "tool": fn_name, "params": params, "result": result, "iteration": iteration,
                })
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                    "tool_call_id": v["id"],
                })
                await _emit({"type": "tool_done", "tool": fn_name, "result": result})

                if is_send:
                    _message_sent = True
                    _sent_text_to_lead = (
                        params.get("mensagem") or params.get("message")
                        or params.get("body") or params.get("text")
                        or params.get("texto") or ""
                    )

            if _message_sent:
                final_output = _sent_text_to_lead or _sanitize_agent_text(full_content) or "Mensagem enviada."
                break
        else:
            final_output = _sanitize_agent_text(full_content) or "Execução concluída."
            break

    else:
        final_output = final_output or "Limite máximo de iterações atingido."

    # ── Histórico da sessão (branch único ao final) ─────────────────────────
    if db is not None and session_id:
        try:
            clean_user_input = original_input_for_history or _extract_clean_user_input(user_input)
            await db.chat_sessions.update_one(
                {"session_id": session_id, "agent_id": agent.get("agent_id")},
                {"$push": {"history": {"$each": [
                    {"role": "user", "content": clean_user_input},
                    {"role": "assistant", "content": final_output},
                ]}},
                 "$set": {"updated_at": datetime.now(timezone.utc),
                          "agent_id": agent.get("agent_id"),
                          "session_id": session_id},
                 "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Erro ao salvar histórico streaming da sessão {session_id}: {e}")

    return final_output, steps


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


async def execute_agent(
    agent: dict,
    user_input: str,
    workspace_creds: dict,
    db=None,
    session_id: str = None,
    max_iterations: int = 8,
    webhook_mode: bool = False,
    original_input_for_history: Optional[str] = None,
    allowed_ticket_id: str = "",
    allowed_numero: str = "",
):
    """
    Orquestra a execução do agente LLM com as ferramentas do MCP.

    Anti-loop guarantees (ordem de defesa):
      1. Tools de busca/listagem são BLOQUEADAS em webhook_mode (WEBHOOK_BLOCKED_TOOLS).
      2. Tools de envio são LOCKADAS ao ticket_id/número do disparador
         via _enforce_ticket_scope — se o LLM trocar os IDs, a chamada é rejeitada.
      3. Apenas UM envio de mensagem ao lead por execução (singleton send).
      4. msg.content e tool args passam por _sanitize_agent_text antes de sair.
      5. tool_choice="required" em webhook_mode força o LLM a chamar tool.
      6. Histórico salvo uma única vez ao final com o texto realmente enviado.
    """
    import litellm
    llm_config = agent.get("llm_config", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    api_key = llm_config.get("api_key") or os.environ.get("EMERGENT_LLM_KEY")
    user_system_prompt = llm_config.get(
        "system_prompt",
        "Você é um assistente inteligente de CRM. Responda sempre em português.",
    )
    temperature = float(llm_config.get("temperature", 0.7))
    max_tokens = int(llm_config.get("max_tokens", 4096))

    if not api_key:
        raise ValueError("API Key do LLM não configurada. Configure no nó LLM do agente.")

    # Compose system prompt: user prompt + mandatory CRM rules + skill pack fragments.
    # Em webhook_mode usamos uma versão ENXUTA das regras, consistente com a
    # lista de tools permitidas (sem mencionar buscar_mensagens_ticket etc.).
    skill_prompt = _compose_skill_prompt(agent)
    rules = MANDATORY_CRM_RULES_WEBHOOK if webhook_mode else MANDATORY_CRM_RULES
    system_prompt = user_system_prompt + skill_prompt + rules

    # Build tool definitions: either from classic nodes, or expanded from
    # enabled_skill_packs, or both.
    nodes = [n for n in agent.get("nodes", []) if n.get("type") == "tool"]
    tool_defs = build_tool_definitions(nodes, agent=agent)
    
    # Se NENHUMA tool disponível (sem nodes, sem skill packs), adiciona as tools padrão do ClickMassa
    if not tool_defs:
        from tools import CLICKMASSA_DEFAULT_TOOLS
        tool_defs = CLICKMASSA_DEFAULT_TOOLS
        logger.info(f"[execute_agent] usando tools padrão do ClickMassa: {len(tool_defs)} tools")

    # Em modo webhook o agente só pode ENVIAR — ferramentas de busca são bloqueadas.
    # Isso evita o loop "busca histórico → vê resposta própria → responde de novo".
    if webhook_mode:
        before = len(tool_defs)
        tool_defs = [
            t for t in tool_defs
            if t.get("function", {}).get("name", "") not in WEBHOOK_BLOCKED_TOOLS
        ]
        logger.info(
            f"[execute_agent webhook_mode] tools: {before} total → {len(tool_defs)} disponíveis "
            f"({[t.get('function',{}).get('name') for t in tool_defs]})"
        )

    # ── Carrega histórico da sessão do MongoDB ──────────────────────────────
    history = []
    if db is not None and session_id:
        try:
            doc = await db.chat_sessions.find_one(
                {"session_id": session_id, "agent_id": agent.get("agent_id")},
                {"_id": 0},
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

    steps: List[dict] = []
    litellm.set_verbose = False
    _message_sent = False              # singleton guard: only one send per run
    _sent_text_to_lead: Optional[str] = None  # the text actually delivered to the lead
    final_output = ""

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
            # In webhook mode force the LLM to call a tool rather than freely
            # chatting — this is the strongest single defense against the
            # "agent responds to itself" failure mode. If a provider rejects
            # the flag (some non-OpenAI models via litellm), we retry without.
            if webhook_mode:
                kwargs["tool_choice"] = "required"

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            if "tool_choice" in kwargs and "tool_choice" in str(e).lower():
                logger.warning(
                    f"[execute_agent] provider não aceita tool_choice=required, "
                    f"removendo e tentando de novo: {e}"
                )
                kwargs.pop("tool_choice", None)
                response = await litellm.acompletion(**kwargs)
            else:
                raise

        msg = response.choices[0].message

        has_tool_calls = hasattr(msg, "tool_calls") and msg.tool_calls
        if has_tool_calls:
            # Record the assistant turn (with tool calls) for the next iteration's context.
            raw_content = msg.content or ""
            messages.append({
                "role": "assistant",
                "content": _sanitize_agent_text(raw_content),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name or ""
                try:
                    params = json.loads(tc.function.arguments or "{}")
                except Exception:
                    params = {}

                # Parse mcp_id__tool_name format
                if "__" in fn_name:
                    mcp_id, tool_name = fn_name.split("__", 1)
                else:
                    mcp_id, tool_name = "clickmassa", fn_name

                is_send = _is_send_tool(fn_name)

                # Singleton guard: at most ONE send to the lead per execution.
                # Any subsequent send call (same iteration or later) is blocked
                # with a controlled error tool result — the LLM sees it and
                # stops trying to double-message.
                if is_send and _message_sent:
                    blocked = {
                        "error": (
                            "ENVIO DUPLICADO BLOQUEADO: já foi enviada 1 mensagem ao "
                            "lead nesta execução. Encerre a resposta — não chame mais "
                            "ferramentas de envio."
                        ),
                        "blocked": True,
                    }
                    steps.append({
                        "tool": fn_name,
                        "params": params,
                        "result": blocked,
                        "iteration": iteration,
                        "blocked": True,
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(blocked, ensure_ascii=False),
                        "tool_call_id": tc.id,
                    })
                    continue

                # Sanitize the outbound message text BEFORE it leaves the system.
                # This is the last line of defense against hallucinated dialogue
                # ("Lead: ...\nAgente: ...") being delivered to the real lead.
                if is_send:
                    for key in ("mensagem", "message", "body", "text", "texto"):
                        if key in params and isinstance(params[key], str):
                            params[key] = _sanitize_agent_text(params[key])

                # TICKET SCOPE LOCK — em webhook_mode, valida que o LLM não está
                # tentando enviar para outro ticket/número. Se tentar, a chamada
                # é REJEITADA e o LLM recebe um tool_result de erro → para.
                # Também pode converter enviar_mensagem_direta (sem número) em
                # enviar_mensagem (com ticket_id), devolvendo um fn_name novo.
                if webhook_mode and (allowed_ticket_id or allowed_numero):
                    new_fn_name, params, scope_err = _enforce_ticket_scope(
                        fn_name, params, allowed_ticket_id, allowed_numero
                    )
                    if scope_err:
                        logger.warning(
                            f"[execute_agent webhook_mode] scope violation em {fn_name}: "
                            f"tentou ticket={params.get('ticket_id')} numero={params.get('numero') or params.get('phone_number')} "
                            f"permitido=ticket_id={allowed_ticket_id} numero={allowed_numero}"
                        )
                        steps.append({
                            "tool": fn_name,
                            "params": params,
                            "result": scope_err,
                            "iteration": iteration,
                            "blocked": True,
                        })
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(scope_err, ensure_ascii=False),
                            "tool_call_id": tc.id,
                        })
                        continue
                    # Se a tool foi reescrita (ex: enviar_mensagem_direta → enviar_mensagem),
                    # atualiza fn_name/tool_name para o execute_tool usar o nome correto.
                    if new_fn_name != fn_name:
                        logger.info(
                            f"[execute_agent webhook_mode] tool reescrita: {fn_name} → {new_fn_name} "
                            f"(numero vazio + ticket_id={allowed_ticket_id})"
                        )
                        fn_name = new_fn_name
                        if "__" in fn_name:
                            mcp_id, tool_name = fn_name.split("__", 1)
                        else:
                            tool_name = fn_name

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

                if is_send:
                    _message_sent = True
                    _sent_text_to_lead = (
                        params.get("mensagem")
                        or params.get("message")
                        or params.get("body")
                        or params.get("text")
                        or params.get("texto")
                        or ""
                    )

            if _message_sent:
                # Whatever was actually delivered to the lead is our canonical output.
                final_output = _sent_text_to_lead or _sanitize_agent_text(msg.content) or "Mensagem enviada ao lead."
                break
        else:
            # Text-only response. This is the normal terminating branch for
            # non-webhook chat runs (e.g. user chatting with the agent in the UI).
            final_output = _sanitize_agent_text(msg.content) or "Execução concluída sem resposta."
            break

    else:
        # for/else: loop exhausted without break
        final_output = final_output or "Limite máximo de iterações atingido."

    # ── Persiste histórico da sessão (branch único — sempre executa) ────────
    if db is not None and session_id:
        try:
            clean_user_input = original_input_for_history or _extract_clean_user_input(user_input)
            new_entries = [
                {"role": "user", "content": clean_user_input},
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

    # 2. Lê e loga o payload bruto para diagnóstico
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo da requisição deve ser JSON válido")

    # LOG COMPLETO para diagnóstico — visível nos logs do Railway
    logger.info(f"[Webhook {agent_id}] payload keys={list(payload.keys())}")
    logger.info(f"[Webhook {agent_id}] payload={json.dumps(payload, ensure_ascii=False)[:800]}")

    # 3. Extrai todos os campos via função pura testada (_extract_webhook_fields).
    # Essa função conhece os formatos do ClickMassa (ticket aninhado em
    # payload.message.ticket), Chatwoot (payload.data.conversation) e payloads
    # planos — centralizando toda a lógica de normalização em um só lugar.
    fields = _extract_webhook_fields(payload)
    data_wrap       = fields["data_wrap"]
    msg_obj         = fields["msg_obj"]
    ticket_obj      = fields["ticket_obj"]
    from_me         = fields["from_me"]
    is_private      = fields["is_private"]
    msg_type        = fields["msg_type"]
    sender_type     = fields["sender_type"]

    logger.info(f"[Webhook {agent_id}] filtros: from_me={from_me} is_private={is_private} msg_type={msg_type} sender_type={sender_type}")

    if from_me:
        logger.info(f"[Webhook {agent_id}] ignorado: fromMe=True")
        return {"status": "ignored", "reason": "Mensagem enviada pela empresa — ignorada para evitar loop"}
    if is_private:
        logger.info(f"[Webhook {agent_id}] ignorado: nota interna ou notificação")
        return {"status": "ignored", "reason": "Nota interna ou notificação ignorada"}

    # ── GATE DE STATUS DO TICKET (BLACKLIST-FIRST) ────────────────────────────
    # Filosofia: default é PROCESSAR. Só bloqueia se o status indica claramente
    # "já atendido/fechado/resolvido". Qualquer outro valor (incluindo vazio,
    # "open", "pending", "aberto", "novo", "in_queue", etc.) passa.
    #
    # Isso evita falsos bloqueios quando o CRM usa nomenclaturas que não estão
    # na nossa whitelist. O objetivo é filtrar APENAS tickets comprovadamente
    # fora do fluxo "bot responde pendente".
    #
    # Override: WEBHOOK_BLOCKED_STATUSES (env csv) ou
    # agent.webhook_blocked_statuses (array).
    blocked_statuses_env = os.environ.get(
        "WEBHOOK_BLOCKED_STATUSES",
        "closed,resolved,fechado,resolvido,atendido,attending,em_atendimento,completed,done",
    )
    BLOCKED_TICKET_STATUSES = {
        s.strip().lower() for s in blocked_statuses_env.split(",") if s.strip()
    }
    agent_blocked = agent.get("webhook_blocked_statuses")
    if isinstance(agent_blocked, list) and agent_blocked:
        BLOCKED_TICKET_STATUSES = {str(s).lower() for s in agent_blocked if s}

    ticket_status = fields["ticket_status"] or str(
        payload.get("ticketStatus") or payload.get("status") or ""
    ).strip().lower()

    logger.info(
        f"[Webhook {agent_id}] gate: ticket_status='{ticket_status}' "
        f"blocked_set={sorted(BLOCKED_TICKET_STATUSES)}"
    )

    # Match exato OU substring (pega variações tipo "open_closed" ou "ticket_resolved")
    if ticket_status and (
        ticket_status in BLOCKED_TICKET_STATUSES
        or any(kw in ticket_status for kw in BLOCKED_TICKET_STATUSES)
    ):
        logger.info(
            f"[Webhook {agent_id}] ignorado: ticket_status='{ticket_status}' bate em blocked"
        )
        return {
            "status": "ignored",
            "reason": f"Ticket em status '{ticket_status}' — agente não atua em tickets fechados/atendidos",
        }

    # Bloqueio por operador atribuído — OPT-IN (default false).
    # ClickMassa/Chatwoot podem popular userId mesmo com bot-user, então não
    # bloqueamos por default. Ative com agent.webhook_ignore_assigned=true se
    # quiser que humano atendendo pare o bot.
    ignore_assigned = bool(agent.get("webhook_ignore_assigned", False))
    if ignore_assigned:
        ticket_user_dict = ticket_obj.get("user") if isinstance(ticket_obj.get("user"), dict) else {}
        assigned_user_id = (
            ticket_obj.get("userId")
            or ticket_obj.get("user_id")
            or ticket_obj.get("assignedTo")
            or ticket_obj.get("assigned_to")
            or ticket_user_dict.get("id")
            or data_wrap.get("userId")
            or data_wrap.get("user_id")
        )
        if assigned_user_id and str(assigned_user_id) not in ("0", "None", "null", ""):
            logger.info(
                f"[Webhook {agent_id}] ignorado: ticket atribuído a user_id={assigned_user_id} "
                f"(webhook_ignore_assigned=true)"
            )
            return {
                "status": "ignored",
                "reason": "Ticket atribuído a operador humano — agente desativado por webhook_ignore_assigned",
            }
    # ──────────────────────────────────────────────────────────────────────────

    # Campos extraídos pela função pura _extract_webhook_fields (ver topo)
    user_input     = fields["user_input"]
    ticket_id      = fields["ticket_id"]
    contact_number = fields["contact_number"]
    contact_name   = fields["contact_name"]
    contact_id     = fields["contact_id"]

    if not user_input:
        logger.info(f"[Webhook {agent_id}] ignorado: sem conteúdo de mensagem no payload")
        return {"status": "ignored", "reason": "Nenhum conteúdo de mensagem encontrado no payload"}

    logger.info(f"[Webhook {agent_id}] extraído: input='{user_input[:60]}' ticket_id='{ticket_id}' contact_number='{contact_number}' contact_name='{contact_name}'")

    # Log completo dos campos relevantes para o gate — facilita diagnóstico
    # quando o bot "parar de responder".
    _ticket_user = ticket_obj.get("user") if isinstance(ticket_obj.get("user"), dict) else {}
    logger.info(
        f"[Webhook {agent_id}] gate-fields: "
        f"ticket.status={ticket_obj.get('status')!r} "
        f"ticket.state={ticket_obj.get('state')!r} "
        f"data.status={data_wrap.get('status')!r} "
        f"ticket.userId={ticket_obj.get('userId')!r} "
        f"ticket.user.id={_ticket_user.get('id')!r} "
        f"ticket.assignedTo={ticket_obj.get('assignedTo')!r}"
    )

    # ── PROTEÇÃO ANTI-LOOP ─────────────────────────────────────────────────────
    # Camada 1: deduplicação por ID da mensagem
    msg_id = fields["msg_id"]
    if msg_id:
        already = await db.webhook_dedup.find_one({"msg_id": msg_id, "agent_id": agent_id})
        if already:
            logger.info(f"[Webhook {agent_id}] ignorado: msg_id={msg_id} já processado")
            return {"status": "ignored", "reason": "Mensagem já processada (deduplicação por ID)"}
        await db.webhook_dedup.insert_one({
            "msg_id": msg_id, "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc)
        })

    # Camada 1.5: COOLDOWN pós-resposta por ticket.
    # Quando o lead manda várias mensagens seguidas ("Oi", "Olá", "Tô aí"), a ClickMassa
    # dispara um webhook por mensagem — e sem cooldown, o agente responde cada uma
    # separadamente, gerando a rajada de respostas iguais que o operador vê no CRM.
    # Aqui: se o agente já respondeu este ticket nos últimos N segundos, ignora o
    # webhook (a próxima mensagem do lead só será atendida depois da janela).
    # REDUZIDO para 5s default - mais responsivo enquanto evita rajadas.
    cooldown_seconds = int(agent.get("webhook_cooldown_seconds", 5) or 0)
    if cooldown_seconds > 0 and ticket_id:
        last_reply = await db.webhook_last_reply.find_one(
            {"agent_id": agent_id, "ticket_id": str(ticket_id)}
        )
        if last_reply:
            last_at = last_reply.get("replied_at")
            if last_at:
                if last_at.tzinfo is None:
                    last_at = last_at.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
                if elapsed < cooldown_seconds:
                    logger.info(
                        f"[Webhook {agent_id}] ignorado: cooldown ativo para ticket {ticket_id} "
                        f"({elapsed:.1f}s < {cooldown_seconds}s)"
                    )
                    return {
                        "status": "ignored",
                        "reason": f"Cooldown de {cooldown_seconds}s — resposta anterior há {elapsed:.1f}s",
                    }

    # Camada 2: lock atômico por ticket — solução definitiva para race condition.
    # O cooldown anterior usava find_one + insert separados, deixando uma janela de ~10ms
    # onde múltiplos webhooks simultâneos passavam ao mesmo tempo.
    # O upsert com $setOnInsert é atômico no MongoDB: apenas UM webhook insere com sucesso.
    _lock_acquired = False
    if ticket_id:
        lock_key = f"{agent_id}:{ticket_id}"
        try:
            now_utc = datetime.now(timezone.utc)
            lock_result = await db.webhook_locks.update_one(
                {"lock_key": lock_key},
                {"$setOnInsert": {
                    "lock_key": lock_key,
                    "agent_id": agent_id,
                    "created_at": now_utc,
                    "expires_at": now_utc + timedelta(seconds=90),
                }},
                upsert=True,
            )
            if lock_result.upserted_id:
                _lock_acquired = True  # fomos nós que criamos o lock
                logger.info(f"[Webhook {agent_id}] lock adquirido para ticket {ticket_id}")
            else:
                # Documento já existia → outro webhook está processando este ticket
                logger.info(f"[Webhook {agent_id}] lock ativo para ticket {ticket_id} — ignorando webhook duplicado")
                return {"status": "ignored", "reason": "Ticket já sendo processado por outro webhook (lock ativo)"}
        except Exception as lock_err:
            # DuplicateKeyError em corrida extrema → o outro webhook ganhou
            logger.info(f"[Webhook {agent_id}] conflito de lock para ticket {ticket_id}: {lock_err}")
            return {"status": "ignored", "reason": "Conflito de lock — ticket já sendo processado"}
    # ───────────────────────────────────────────────────────────────────────────

    metadata = {
        "crm_webhook": True,
        "ticket_id": ticket_id,
        "contact_id": contact_id,
        "contact_number": contact_number,
        "contact_name": contact_name,
    }
    session_id = f"webhook_{agent_id}_{ticket_id}" if ticket_id else None

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

    # Monta input enriquecido com instrução explícita (apenas para o agente, não salvo no histórico)
    original_input = user_input  # preserva para exibição limpa no histórico
    ticket_id_for_reply = metadata.get("ticket_id", "")
    contact_number_for_reply = metadata.get("contact_number", "")

    # Sempre injeta instrução de resposta — usa ticket_id se disponível, senão número
    contact_info = ""
    if metadata.get("contact_name") or contact_number_for_reply:
        contact_info = f"\nContato: {metadata.get('contact_name', '')} ({contact_number_for_reply})"

    if ticket_id_for_reply:
        reply_instruction = (
            f"INSTRUÇÃO OBRIGATÓRIA E IMUTÁVEL:\n"
            f"- Use 'enviar_mensagem_direta' com ticket_id=\"{ticket_id_for_reply}\" para responder.\n"
            f"- NÃO altere o ticket_id. NÃO liste outros tickets. NÃO busque contatos.\n"
            f"- Se você passar outro ticket_id, a chamada será rejeitada pelo sistema."
        )
    elif contact_number_for_reply:
        reply_instruction = (
            f"INSTRUÇÃO OBRIGATÓRIA E IMUTÁVEL:\n"
            f"- Use 'enviar_mensagem' com numero=\"{contact_number_for_reply}\" para responder.\n"
            f"- NÃO altere o número. NÃO liste outros tickets. NÃO busque contatos.\n"
            f"- Se você passar outro número, a chamada será rejeitada pelo sistema."
        )
    else:
        # Sem ticket_id nem número → não dá para enfileirar com segurança.
        # Logar e ignorar: preferir silêncio a responder em ticket errado.
        logger.warning(
            f"[Webhook {agent_id}] ignorado: payload não tem ticket_id nem contact_number. "
            f"Sem destinatário seguro para responder."
        )
        return {
            "status": "ignored",
            "reason": "Payload sem ticket_id nem contact_number — destinatário indeterminado",
        }

    user_input = (
        f"[WEBHOOK AUTOMÁTICO — RESPOSTA OBRIGATÓRIA]\n"
        f"Mensagem recebida do lead via CRM:\n"
        f"\"{user_input}\"\n"
        + (f"Ticket ID: {ticket_id_for_reply}" if ticket_id_for_reply else "")
        + contact_info + "\n\n"
        + reply_instruction
    )

    # Cria registro de run (salva input original, sem o bloco de instrução)
    run_id = str(uuid.uuid4())
    session_id = session_id or f"webhook_{agent_id}_{run_id[:8]}"
    run_doc = {
        "run_id": run_id,
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "input": original_input,  # input limpo para exibição no histórico
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
            # webhook_mode=True: remove ferramentas de busca de histórico e força
            # tool_choice=required. original_input_for_history salva apenas a mensagem
            # limpa do lead no histórico, não o envelope de instrução do webhook.
            # allowed_ticket_id/allowed_numero ativam o TICKET SCOPE LOCK: se o LLM
            # tentar enviar para outro ticket/número, a chamada é rejeitada.
            output, steps = await execute_agent(
                agent, user_input, workspace_creds, db=db, session_id=session_id,
                max_iterations=3, webhook_mode=True,
                original_input_for_history=original_input,
                allowed_ticket_id=str(ticket_id_for_reply or ""),
                allowed_numero=str(contact_number_for_reply or ""),
            )

            # Fallback automático: se o agente gerou texto mas não chamou enviar_mensagem,
            # envia a resposta programaticamente via Push API (enviar_mensagem) — NUNCA
            # via enviar_mensagem_direta, que registra a mensagem como se fosse do lead
            # no CRM (bug descoberto em 2026-04-18: POST /messages/{id} sem flag de empresa).
            sent_via_tool = any("enviar_mensagem" in s.get("tool", "") for s in steps)
            if not sent_via_tool and workspace_creds.get("clickmassa"):
                creds_cm = workspace_creds["clickmassa"]
                send_result = None
                try:
                    if contact_number_for_reply:
                        logger.info(f"[Webhook {agent_id}] fallback: enviando via Push API (numero={contact_number_for_reply})")
                        send_result = await execute_tool("clickmassa", "enviar_mensagem", {
                            "numero": contact_number_for_reply,
                            "mensagem": output,
                        }, creds_cm)
                    else:
                        # Sem número não dá pra usar Push API. Não fazemos fallback para
                        # enviar_mensagem_direta porque a mensagem apareceria como do lead.
                        logger.warning(
                            f"[Webhook {agent_id}] fallback NÃO executado: sem contact_number. "
                            f"A mensagem do agente foi gerada mas não pôde ser enviada via Push API. "
                            f"Verifique se o payload do CRM traz ticket.contact.number."
                        )

                    if send_result:
                        logger.info(f"[Webhook {agent_id}] fallback result: {json.dumps(send_result, ensure_ascii=False, default=str)[:200]}")
                        steps.append({
                            "tool": "auto_send_fallback",
                            "params": {"numero": contact_number_for_reply},
                            "result": send_result,
                            "iteration": 0,
                        })
                except Exception as send_err:
                    logger.error(f"[Webhook {agent_id}] fallback FALHOU: {send_err}", exc_info=True)
            elif not sent_via_tool:
                logger.warning(f"[Webhook {agent_id}] fallback ignorado: credenciais clickmassa não encontradas. creds keys={list(workspace_creds.keys())}")

            # Registra timestamp da última resposta para alimentar o cooldown da Camada 1.5.
            # Uma resposta foi considerada enviada se:
            #   - o agente chamou enviar_mensagem (sent_via_tool), OU
            #   - o fallback programático executou com sucesso (steps tem auto_send_fallback).
            reply_sent = sent_via_tool or any(
                s.get("tool") == "auto_send_fallback" and s.get("result")
                for s in steps
            )
            if reply_sent and ticket_id:
                try:
                    await db.webhook_last_reply.update_one(
                        {"agent_id": agent_id, "ticket_id": str(ticket_id)},
                        {"$set": {
                            "agent_id": agent_id,
                            "ticket_id": str(ticket_id),
                            "replied_at": datetime.now(timezone.utc),
                            "run_id": run_id,
                        }},
                        upsert=True,
                    )
                    logger.info(f"[Webhook {agent_id}] replied_at registrado para ticket {ticket_id}")
                except Exception as reg_err:
                    logger.warning(f"[Webhook {agent_id}] falha ao registrar replied_at: {reg_err}")

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
            logger.error(f"Webhook run {run_id} falhou: {e}", exc_info=True)
            await db.runs.update_one(
                {"run_id": run_id},
                {"$set": {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc),
                }}
            )
        finally:
            # Libera o lock atômico para que o próximo webhook deste ticket possa ser processado
            if _lock_acquired and ticket_id:
                try:
                    await db.webhook_locks.delete_one({"lock_key": f"{agent_id}:{ticket_id}"})
                    logger.info(f"[Webhook {agent_id}] lock liberado para ticket {ticket_id}")
                except Exception:
                    pass  # TTL do MongoDB vai limpar em 90s de qualquer forma

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
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    """
    CORREÇÃO BUG 4 — Mecanismo de polling automático de leads pendentes.

    Este endpoint:
    1. Busca todos os tickets com status 'pending' no CRM via ClickMassa
    2. Para cada ticket, dispara o agente de IA em background
    3. O agente lê as mensagens do ticket, entende o contexto e responde automaticamente

    Pode ser chamado:
    - Manualmente pelo frontend (via JWT jwtAuth)
    - Via automadores como N8n ou CRMs nativos enviando Header X-Webhook-Secret
    - Via APScheduler (cron) configurado para rodar a cada N minutos
    - Via Railway cron job (se configurado no railway.toml)
    """
    if body is None:
        body = PendingLeadsRequest()

    db = request.app.state.db

    # Verifica autenticação flexível: X-Webhook-Secret (N8n/CRMs) ou token JWT (Dashboard User)
    agent = None
    workspace_id = None

    if x_webhook_secret:
        agent = await db.agents.find_one({"agent_id": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        stored_secret = agent.get("webhook_secret", "")
        if not stored_secret or not hmac.compare_digest(stored_secret, x_webhook_secret):
            raise HTTPException(status_code=401, detail="Webhook secret inválido")
        workspace_id = agent.get("workspace_id")
    else:
        user = await get_current_user(request)
        workspace_id = user["workspace_id"]
        agent = await db.agents.find_one({"agent_id": agent_id, "workspace_id": workspace_id}, {"_id": 0})
        if not agent:
            raise HTTPException(status_code=404, detail="Agente não encontrado no workspace")

    if agent.get("status") != "active":
        raise HTTPException(status_code=400, detail="Agente inativo — ative-o antes de processar leads")

    # Carrega credenciais (mesmo padrão do run_agent)
    workspace_creds = {}
    creds_list = await db.credentials.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(50)
    for cred in creds_list:
        decrypted = {}
        for k, v in cred.get("data", {}).items():
            try:
                decrypted[k] = decrypt(str(v))
            except Exception:
                decrypted[k] = v
        decrypted["workspace_id"] = workspace_id
        workspace_creds[cred["mcp_id"]] = decrypted

    # Injeta credenciais MCP por agente
    agent_mcp_creds = await _get_agent_mcp_credentials(db, agent_id)
    if agent_mcp_creds:
        agent_mcp_creds["workspace_id"] = workspace_id
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

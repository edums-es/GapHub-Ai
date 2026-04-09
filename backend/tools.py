import httpx
import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Cache de tokens de sessão por workspace
_session_cache: Dict[str, str] = {}


async def get_clickmassa_token(credentials: dict) -> str:
    workspace_id = credentials.get("workspace_id", "default")

    # Se token direto estiver configurado, usa primeiro (mais estável)
    direct_token = credentials.get("token", "").strip()
    if direct_token:
        return direct_token

    # Usa cache de sessão se disponível
    if workspace_id in _session_cache:
        return _session_cache[workspace_id]

    # Tenta login com email+senha
    base_url = credentials.get("base_url", "").rstrip("/")
    email = credentials.get("email")
    password = credentials.get("password")

    if email and password:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{base_url}/auth/login", json={"email": email, "password": password})
                data = resp.json()
                if data.get("token"):
                    _session_cache[workspace_id] = data["token"]
                    return data["token"]
                logger.error(f"ClickMassa login sem token: {data}")
        except Exception as e:
            logger.error(f"ClickMassa login error: {e}")

    raise ValueError(
        "Credenciais ClickMassa inválidas ou não configuradas. "
        "Configure email+senha OU token direto nas Configurações."
    )


def _format_messages_with_direction(messages_raw: list) -> list:
    """Format message list with clear direction labels."""
    formatted = []
    for msg in messages_raw:
        if msg.get("messageType") == "notification":
            continue  # pula notificações de sistema
        from_me = msg.get("fromMe", False)
        formatted.append({
            "id": msg.get("id"),
            "direcao": "ENVIADO_PELA_EMPRESA" if from_me else "RECEBIDO_DO_LEAD",
            "fromMe": from_me,
            "texto": msg.get("body", ""),
            "isNotaInterna": msg.get("isPrivate", False),
            "horario": msg.get("createdAt", msg.get("timestamp", "")),
        })
    return formatted


def _annotate_ticket_last_message(ticket: dict) -> dict:
    """Add direction label to last message in a ticket."""
    last_msg = ticket.get("lastMessage")
    if last_msg and isinstance(last_msg, dict):
        from_me = last_msg.get("fromMe", False)
        ticket["lastMessage"]["direcao"] = "ENVIADO_PELA_EMPRESA" if from_me else "RECEBIDO_DO_LEAD"
    return ticket


async def execute_clickmassa_tool(tool_name: str, params: dict, credentials: dict) -> dict:
    base_url = credentials.get("base_url", "").rstrip("/")
    canal_id = credentials.get("canal_id", params.get("canal_id", ""))
    workspace_id = credentials.get("workspace_id", "default")

    try:
        token = await get_clickmassa_token(credentials)
    except ValueError as e:
        return {"error": str(e)}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def do_request():
        async with httpx.AsyncClient(timeout=20) as c:
            if tool_name == "buscar_contato_por_numero":
                return await c.get(f"{base_url}/v1/contacts/number/{params['numero']}", headers=headers)
            elif tool_name == "buscar_contato_por_id":
                return await c.get(f"{base_url}/v1/contacts/{params['id']}", headers=headers)
            elif tool_name == "listar_contatos":
                return await c.get(f"{base_url}/v1/contacts/", headers=headers)
            elif tool_name == "criar_contato":
                body = {"name": params["nome"], "number": params["numero"]}
                if params.get("email"):
                    body["email"] = params["email"]
                if params.get("tags"):
                    body["tags"] = params["tags"]
                return await c.post(f"{base_url}/v1/contacts/", json=body, headers=headers)
            elif tool_name == "atualizar_contato":
                body = {"id": int(params["id"])}
                for k in ["nome", "email", "leadStatusId", "leadOriginId", "tags"]:
                    if params.get(k):
                        key = "name" if k == "nome" else k
                        body[key] = params[k]
                return await c.put(f"{base_url}/contacts/{params['id']}", json=body, headers=headers)
            elif tool_name == "adicionar_etiquetas":
                return await c.patch(f"{base_url}/v1/contacts/{params['id']}", json={"tags": params["tags"]}, headers=headers)
            elif tool_name == "enviar_mensagem":
                cid = params.get("canal_id") or canal_id
                body = {"number": params["numero"], "body": params["mensagem"], "externalKey": f"mcp-{__import__('time').time()}"}
                return await c.post(f"{base_url}/v1/api/external/{cid}", json=body, headers=headers)
            elif tool_name == "enviar_mensagem_direta":
                search = await c.get(f"{base_url}/tickets?searchParam={params['numero']}&showAll=true", headers=headers)
                tickets = search.json().get("tickets", [])
                ticket = next((t for t in tickets if t["contact"]["number"] == params["numero"] and t["status"] in ["open", "pending"]), None)
                if not ticket:
                    return {"error": f"Nenhum ticket aberto para {params['numero']}"}
                return await c.post(f"{base_url}/messages/{ticket['id']}", json={"body": params["mensagem"]}, headers=headers)
            elif tool_name == "enviar_nota_interna":
                search = await c.get(f"{base_url}/tickets?searchParam={params['numero']}&showAll=true", headers=headers)
                tickets = search.json().get("tickets", [])
                ticket = next((t for t in tickets if t["contact"]["number"] == params["numero"]), None)
                if not ticket:
                    # Try by ticket_id directly
                    ticket_id = params.get("ticket_id")
                    if ticket_id:
                        return await c.post(f"{base_url}/messages/{ticket_id}", json={"body": params["nota"], "isPrivate": True}, headers=headers)
                    return {"error": f"Ticket não encontrado para {params['numero']}"}
                return await c.post(f"{base_url}/messages/{ticket['id']}", json={"body": params["nota"], "isPrivate": True}, headers=headers)
            elif tool_name == "buscar_mensagens_ticket":
                ticket_id = params.get("ticket_id")
                page = params.get("pagina", 1)
                r = await c.get(f"{base_url}/messages?ticketId={ticket_id}&pageNumber={page}", headers=headers)
                data = r.json()
                messages_raw = data.get("messages", data if isinstance(data, list) else [])
                formatted = _format_messages_with_direction(messages_raw)
                return {
                    "mensagens": formatted,
                    "total": len(formatted),
                    "instrucao": "fromMe:false=LEAD falou, fromMe:true=EMPRESA falou. NUNCA trate ENVIADO_PELA_EMPRESA como mensagem do lead.",
                }
            elif tool_name == "listar_tickets_pendentes":
                return await c.get(f"{base_url}/tickets?status=pending", headers=headers)
            elif tool_name == "listar_tickets_abertos":
                qs = f"&searchParam={params['busca']}" if params.get("busca") else ""
                return await c.get(f"{base_url}/tickets?status=open{qs}", headers=headers)
            elif tool_name == "fechar_ticket":
                return await c.put(f"{base_url}/tickets/{params['ticket_id']}", json={"status": "closed"}, headers=headers)
            elif tool_name == "devolver_para_fila":
                return await c.put(f"{base_url}/tickets/{params['ticket_id']}", json={"status": "pending", "userId": None}, headers=headers)
            elif tool_name == "listar_status_lead":
                return await c.get(f"{base_url}/lead/status/list", headers=headers)
            elif tool_name == "listar_origens_lead":
                return await c.get(f"{base_url}/lead/origin/list", headers=headers)
            elif tool_name == "criar_tarefa":
                return await c.post(f"{base_url}/tasks", json=params, headers=headers)
            elif tool_name == "listar_tarefas":
                return await c.get(f"{base_url}/tasks", headers=headers)
            elif tool_name == "listar_conexoes_whatsapp":
                return await c.get(f"{base_url}/whatsapp/list", headers=headers)
            elif tool_name == "listar_fluxos_chat":
                return await c.get(f"{base_url}/chat-flow/list", headers=headers)
            elif tool_name == "atribuir_fluxo_chat":
                return await c.put(f"{base_url}/tickets/{params['ticket_id']}", json={"chatFlowId": params['fluxo_id']}, headers=headers)
            elif tool_name == "listar_funis":
                return await c.get(f"{base_url}/funnels", headers=headers)
            elif tool_name == "criar_funil":
                return await c.post(f"{base_url}/funnels", json=params, headers=headers)
            elif tool_name == "atribuir_funil_contato":
                return await c.post(f"{base_url}/funnels/assign", json=params, headers=headers)
            else:
                return None  # não é um objeto httpx.Response

    try:
        result = await do_request()

        # Se retornou dict diretamente (não é Response)
        if isinstance(result, dict):
            return result

        # Verifica token expirado
        if result.status_code == 401:
            # Limpa cache de sessão e tenta com token direto na próxima chamada
            _session_cache.pop(workspace_id, None)
            return {
                "error": "Token inválido ou expirado (401). Sessão limpa. "
                         "Verifique se o Token ou email+senha nas Configurações estão corretos.",
                "http_status": 401,
            }

        try:
            data = result.json()
        except Exception:
            data = {"raw": result.text, "status": result.status_code}

        # Post-process ticket lists to add message direction labels
        if tool_name in ("listar_tickets_pendentes", "listar_tickets_abertos"):
            tickets = data.get("tickets", data if isinstance(data, list) else [])
            if isinstance(tickets, list):
                for ticket in tickets:
                    _annotate_ticket_last_message(ticket)
            data["instrucao_direcao"] = (
                "IMPORTANTE: lastMessage.direcao='RECEBIDO_DO_LEAD' significa que o LEAD mandou a mensagem. "
                "'ENVIADO_PELA_EMPRESA' significa que a EMPRESA enviou. "
                "Use buscar_mensagens_ticket para ver a conversa completa."
            )

        return data

    except Exception as e:
        logger.error(f"Tool execution error {tool_name}: {e}")
        return {"error": str(e)}


async def execute_web_search(params: dict) -> dict:
    query = params.get("query", "")
    return {"results": [
        {"title": f"Resultado para: {query}", "snippet": "Pesquisa simulada - Configure uma chave de API de busca real.", "url": "https://example.com"},
    ]}


async def execute_http_request(tool_name: str, params: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            if tool_name == "http_get":
                r = await c.get(params["url"], headers=params.get("headers", {}))
                return {"status": r.status_code, "body": r.text[:2000]}
            elif tool_name == "http_post":
                r = await c.post(params["url"], json=params.get("body", {}), headers=params.get("headers", {}))
                return {"status": r.status_code, "body": r.text[:2000]}
    except Exception as e:
        return {"error": str(e)}


async def execute_tool(mcp_id: str, tool_name: str, params: dict, credentials: dict) -> dict:
    if mcp_id == "clickmassa":
        return await execute_clickmassa_tool(tool_name, params, credentials)
    elif mcp_id == "web_search":
        return await execute_web_search(params)
    elif mcp_id == "http_request":
        return await execute_http_request(tool_name, params)
    return {"error": f"MCP '{mcp_id}' não suportado ainda"}


def build_tool_definitions(nodes: list) -> List[dict]:
    from marketplace import MCP_CATALOG
    defs = []
    for node in nodes:
        if node.get("type") != "tool":
            continue
        mcp_id = node.get("config", {}).get("mcp_id")
        tool_name = node.get("config", {}).get("tool_name", "*")
        mcp = next((m for m in MCP_CATALOG if m["id"] == mcp_id), None)
        if not mcp:
            continue

        tools_to_add = mcp.get("tools", [])
        if tool_name != "*":
            tools_to_add = [t for t in tools_to_add if t["name"] == tool_name]

        for t in tools_to_add:
            defs.append(_make_tool_def(mcp_id, t["name"], t["description"]))
    return defs


def _make_tool_def(mcp_id: str, name: str, description: str) -> dict:
    SCHEMAS = {
        "buscar_contato_por_numero": {"numero": {"type": "string", "description": "Número com DDI+DDD. Ex: 5527999990000"}},
        "buscar_contato_por_id": {"id": {"type": "string", "description": "ID interno do contato"}},
        "listar_contatos": {},
        "criar_contato": {"nome": {"type": "string"}, "numero": {"type": "string"}, "email": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
        "atualizar_contato": {"id": {"type": "string"}, "nome": {"type": "string"}, "email": {"type": "string"}, "leadStatusId": {"type": "number"}, "leadOriginId": {"type": "number"}},
        "adicionar_etiquetas": {"id": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
        "enviar_mensagem": {
            "numero": {"type": "string", "description": "Número do destinatário"},
            "mensagem": {"type": "string", "description": "Texto da mensagem a enviar ao LEAD — use SOMENTE quando explicitamente pedido para contatar o lead"},
            "canal_id": {"type": "string"},
        },
        "enviar_mensagem_direta": {
            "numero": {"type": "string"},
            "mensagem": {"type": "string", "description": "Texto a enviar ao lead — SOMENTE quando pedido explicitamente para responder ou contatar o lead"},
        },
        "enviar_nota_interna": {
            "numero": {"type": "string", "description": "Número do contato para buscar o ticket"},
            "nota": {"type": "string", "description": "Texto da nota interna — NÃO aparece para o lead. Use para análises, qualificações e observações"},
            "ticket_id": {"type": "string", "description": "ID direto do ticket (alternativo ao número)"},
        },
        "buscar_mensagens_ticket": {
            "ticket_id": {"type": "string", "description": "ID do ticket para buscar conversa completa com direção de mensagens"},
            "pagina": {"type": "number", "description": "Número da página (padrão: 1)"},
        },
        "listar_tickets_pendentes": {},
        "listar_tickets_abertos": {"busca": {"type": "string"}},
        "fechar_ticket": {"ticket_id": {"type": "string"}},
        "devolver_para_fila": {"ticket_id": {"type": "string", "description": "ID do ticket para devolver a um atendente humano"}},
        "listar_status_lead": {},
        "listar_origens_lead": {},
        "criar_tarefa": {"tipo": {"type": "string", "enum": ["T", "L", "C"]}, "titulo": {"type": "string"}, "contato_id": {"type": "string"}, "data": {"type": "string"}},
        "listar_tarefas": {},
        "listar_conexoes_whatsapp": {},
        "listar_fluxos_chat": {},
        "atribuir_fluxo_chat": {"ticket_id": {"type": "string"}, "fluxo_id": {"type": "string"}},
        "listar_funis": {},
        "criar_funil": {"nome": {"type": "string"}, "etapas": {"type": "array", "items": {"type": "object"}}},
        "atribuir_funil_contato": {"contato_id": {"type": "string"}, "funil_id": {"type": "string"}},
        "buscar_web": {"query": {"type": "string", "description": "Termo de busca"}},
        "http_get": {"url": {"type": "string"}, "headers": {"type": "object"}},
        "http_post": {"url": {"type": "string"}, "body": {"type": "object"}, "headers": {"type": "object"}},
    }
    props = SCHEMAS.get(name, {"input": {"type": "string"}})
    required = [k for k in props if k in ["numero", "id", "mensagem", "nota", "ticket_id", "query", "url"]]
    return {
        "type": "function",
        "function": {
            "name": f"{mcp_id}__{name}",
            "description": f"[{mcp_id}] {description}",
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }

import httpx
import asyncio
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ── Bug Fix #2: TTLCache para tokens de sessão — evita vazamento de memória ──
# Substituímos o dict global ilimitado por um cache com expiração (TTL) de 30min.

class _TTLCache:
    """
    Cache simples com TTL (Time-To-Live). Thread-safe para uso assíncrono de
    thread única (asyncio). Não requer dependência externa (cachetools).
    """
    def __init__(self, ttl_seconds: int = 1800):
        self._store: Dict[str, tuple] = {}  # key -> (value, expires_at)
        self._ttl = ttl_seconds

    def _evict_expired(self):
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]

    def __contains__(self, key: str) -> bool:
        if key in self._store:
            _, exp = self._store[key]
            if time.monotonic() < exp:
                return True
            del self._store[key]
        return False

    def __getitem__(self, key: str) -> str:
        if key in self:
            return self._store[key][0]
        raise KeyError(key)

    def __setitem__(self, key: str, value: str):
        self._evict_expired()
        self._store[key] = (value, time.monotonic() + self._ttl)

    def pop(self, key: str, default=None):
        if key in self._store:
            val, _ = self._store.pop(key)
            return val
        return default

    def __len__(self):
        self._evict_expired()
        return len(self._store)


# Cache de tokens de sessão por workspace — TTL de 30 minutos
_session_cache: _TTLCache = _TTLCache(ttl_seconds=1800)

# Cache de canal_id auto-descoberto por workspace. TTL longo: canais raramente mudam.
_canal_id_cache: _TTLCache = _TTLCache(ttl_seconds=3600)  # 1 hora


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


async def _autodiscover_canal_id(base_url: str, token: str, workspace_id: str) -> "str | None":
    """
    Tenta descobrir o canal_id ativo chamando /whatsapp/list e pegando o primeiro
    canal CONECTADO. Cacheado por workspace (TTL 1h). Retorna None se não encontrar.
    Só cacheia resultados válidos — erros não são cacheados.
    """
    cached = _canal_id_cache[workspace_id] if workspace_id in _canal_id_cache else None
    if cached:
        return cached
    try:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=8) as c:
            resp = await c.get(f"{base_url}/whatsapp/list", headers=headers)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        raw_list = data if isinstance(data, list) else (
            data.get("whatsapps") or data.get("data") or data.get("channels") or []
        )
        if not isinstance(raw_list, list):
            return None
        # Prioriza canais com status CONNECTED; senão pega o primeiro com id válido
        connected = [
            ch for ch in raw_list
            if isinstance(ch, dict)
            and str(ch.get("status") or ch.get("state") or "").upper()
            in ("CONNECTED", "OPEN", "ACTIVE", "ONLINE")
            and ch.get("id")
        ]
        chosen = connected[0] if connected else next(
            (ch for ch in raw_list if isinstance(ch, dict) and ch.get("id")), None
        )
        if not chosen:
            return None
        cid = str(chosen["id"])
        if workspace_id:
            _canal_id_cache[workspace_id] = cid
        logger.info(f"[autodiscover_canal_id] workspace={workspace_id} descobriu canal_id={cid}")
        return cid
    except Exception as e:
        logger.warning(f"[autodiscover_canal_id] falhou: {e}")
        return None


def _format_messages_with_direction(messages_raw: list) -> list:
    """
    Formata mensagens com prefixo de texto explícito que o LLM lê diretamente,
    sem depender de interpretar campos JSON como fromMe ou direcao.
    """
    formatted = []
    for msg in messages_raw:
        if msg.get("messageType") == "notification":
            continue

        from_me = msg.get("fromMe", False)
        is_private = msg.get("isPrivate", False)
        body = msg.get("body", "").strip()

        if not body:
            continue

        if is_private:
            prefix = "[NOTA INTERNA]"
        elif from_me:
            prefix = "[EMPRESA]"
        else:
            prefix = "[LEAD]"

        formatted.append({
            "id": msg.get("id"),
            "texto_formatado": f"{prefix}: {body}",
            "prefixo": prefix,
            "fromMe": from_me,
            "isNotaInterna": is_private,
            "horario": msg.get("createdAt", msg.get("timestamp", "")),
        })
    return formatted


def _annotate_ticket_last_message(ticket: dict) -> dict:
    """Add text prefix to last message in a ticket so LLM reads direction as plain text."""
    last_msg = ticket.get("lastMessage")
    if last_msg and isinstance(last_msg, dict):
        from_me = last_msg.get("fromMe", False)
        is_private = last_msg.get("isPrivate", False)
        body = last_msg.get("body", "").strip()
        if is_private:
            prefix = "[NOTA INTERNA]"
        elif from_me:
            prefix = "[EMPRESA]"
        else:
            prefix = "[LEAD]"
        ticket["lastMessage"]["prefixo"] = prefix
        ticket["lastMessage"]["texto_formatado"] = f"{prefix}: {body}" if body else ""
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
                # Envia via Push API (/v1/api/external/{canal_id}) — único endpoint que
                # registra a mensagem como EMPRESA no CRM (aparece à direita com "Envio externo").
                # fromMe=true em POST /messages/{id} NÃO funciona: o ClickMassa ignora o flag
                # e mantém a mensagem como se fosse do lead.
                numero = params.get("numero")
                if not numero:
                    return {"error": "Número é obrigatório."}
                mensagem = params.get("mensagem")
                if not mensagem:
                    return {"error": "Mensagem é obrigatória."}
                cid = params.get("canal_id") or canal_id
                if not cid:
                    cid = await _autodiscover_canal_id(base_url, token, workspace_id)
                if not cid:
                    return {"error": (
                        "canal_id não configurado nas credenciais e não foi possível descobrir "
                        "automaticamente via /whatsapp/list. Configure manualmente em Agent Builder "
                        "→ MCP Credentials → canal_id."
                    )}
                import time as _time
                external_key = params.get("external_key") or f"gaphub-{int(_time.time() * 1000)}"
                return await c.post(
                    f"{base_url}/v1/api/external/{cid}",
                    json={"number": numero, "body": mensagem, "externalKey": external_key},
                    headers=headers,
                )
            elif tool_name == "enviar_mensagem_direta":
                # Também usa Push API — a mensagem é roteada automaticamente pelo ClickMassa
                # para o ticket aberto do número correspondente, e fica registrada como empresa.
                mensagem = params.get("mensagem")
                if not mensagem:
                    return {"error": "Mensagem é obrigatória."}
                numero = params.get("numero")
                ticket_id = params.get("ticket_id")
                # Se vier ticket_id mas não vier numero, busca o número do ticket
                if ticket_id and not numero:
                    try:
                        tk = await c.get(f"{base_url}/tickets/{ticket_id}", headers=headers)
                        td = tk.json()
                        numero = (td.get("contact") or {}).get("number", "")
                    except Exception:
                        numero = ""
                # Se vier só numero sem ticket_id, ok — Push API resolve
                if not numero:
                    return {"error": "Não foi possível determinar o número de destino. Forneça numero ou ticket_id válido."}
                cid = params.get("canal_id") or canal_id
                if not cid:
                    cid = await _autodiscover_canal_id(base_url, token, workspace_id)
                if not cid:
                    return {"error": (
                        "canal_id não configurado. Use enviar_mensagem ou configure canal_id nas credenciais "
                        "(Agent Builder → MCP Credentials → canal_id)."
                    )}
                import time as _time
                external_key = params.get("external_key") or f"gaphub-{int(_time.time() * 1000)}"
                return await c.post(
                    f"{base_url}/v1/api/external/{cid}",
                    json={"number": numero, "body": mensagem, "externalKey": external_key},
                    headers=headers,
                )
            elif tool_name == "enviar_nota_interna":
                ticket_id = params.get("ticket_id")
                if not ticket_id:
                    numero = params.get("numero", "")
                    search = await c.get(f"{base_url}/tickets?searchParam={numero}&showAll=true", headers=headers)
                    tickets = search.json().get("tickets", [])
                    ticket = next((t for t in tickets if t["contact"]["number"] == numero), None)
                    if not ticket:
                        return {"error": f"Ticket não encontrado para {numero}"}
                    ticket_id = ticket['id']
                    
                return await c.post(f"{base_url}/messages/{ticket_id}", json={"body": params["nota"], "isPrivate": True}, headers=headers)
            elif tool_name == "buscar_mensagens_ticket":
                ticket_id = params.get("ticket_id")
                page = params.get("pagina", 1)
                r = await c.get(f"{base_url}/messages?ticketId={ticket_id}&pageNumber={page}", headers=headers)
                data = r.json()
                messages_raw = data.get("messages", data if isinstance(data, list) else [])
                formatted = _format_messages_with_direction(messages_raw)
                # Monta conversa como bloco de texto legível para o LLM
                conversa_texto = "\n".join(m["texto_formatado"] for m in formatted)
                return {
                    "conversa": conversa_texto,
                    "mensagens": formatted,
                    "total": len(formatted),
                    "legenda": "[LEAD] = cliente falou | [EMPRESA] = empresa/atendente falou | [NOTA INTERNA] = só equipe vê",
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
    """
    Ponto central de despacho de ferramentas.
    Para ClickMassa: tenta primeiro via MCPClient (Railway), com fallback à API direta.
    """
    if mcp_id == "clickmassa":
        # Tenta via MCPClient (MCP ClickMassa no Railway) se credenciais MCP disponíveis
        mcp_creds = {
            "apiUrl": credentials.get("apiUrl") or credentials.get("base_url", ""),
            "userToken": credentials.get("userToken") or credentials.get("token", ""),
            "wabaId": credentials.get("wabaId", ""),
        }
        if mcp_creds["userToken"] or mcp_creds["apiUrl"]:
            try:
                from mcp_client import default_mcp_client
                result = await default_mcp_client.call_tool(tool_name, params, mcp_creds)
                # Se MCPClient retornou erro de conexão/ferramenta não encontrada, faz fallback à API direta
                if isinstance(result, dict) and "error" in result:
                    err_msg = str(result.get("error", ""))
                    http_status = result.get("http_status", 0)
                    # Fallback quando: 404 (endpoint ou ferramenta não encontrada),
                    # erros de conectividade, ou timeout
                    if http_status == 404 or any(kw in err_msg for kw in [
                        "conectar", "Timeout", "ConnectError", "404",
                        "não encontrada no MCP", "not found"
                    ]):
                        logger.warning(f"MCPClient falhou para {tool_name} (http_status={http_status}), usando fallback direto: {err_msg}")
                        return await execute_clickmassa_tool(tool_name, params, credentials)
                return result
            except Exception as e:
                logger.warning(f"MCPClient erro ({tool_name}): {e} — usando fallback direto")
        return await execute_clickmassa_tool(tool_name, params, credentials)
    elif mcp_id == "web_search":
        return await execute_web_search(params)
    elif mcp_id == "http_request":
        return await execute_http_request(tool_name, params)
    return {"error": f"MCP '{mcp_id}' não suportado ainda"}


def build_tool_definitions(nodes: list, agent: dict = None) -> List[dict]:
    """
    Monta as tool definitions expostas ao LLM.

    Fontes, em ordem:
      1. `nodes` — tool nodes clássicos desenhados no canvas (compat legado).
      2. `agent.enabled_skill_packs` — packs curados que se expandem em tools.

    As duas fontes coexistem: se um agente tem NODES e PACKS, a união dos dois
    é exposta. Deduplicação por (mcp_id, tool_name).
    """
    from marketplace import MCP_CATALOG
    try:
        from skill_packs import expand_packs_to_tool_refs
    except Exception:  # defensivo — skill_packs é opcional no carregamento
        expand_packs_to_tool_refs = lambda _: []

    # 1) Tool refs vindas dos nodes do canvas
    refs: List[dict] = []
    for node in nodes or []:
        if node.get("type") != "tool":
            continue
        cfg = node.get("config", {}) or {}
        refs.append({"mcp_id": cfg.get("mcp_id"), "tool_name": cfg.get("tool_name", "*")})

    # 2) Tool refs vindas dos skill packs habilitados no agente
    if agent:
        pack_ids = agent.get("enabled_skill_packs", []) or []
        if pack_ids:
            refs.extend(expand_packs_to_tool_refs(pack_ids))

    # 3) Expansão + dedupe
    defs: List[dict] = []
    seen = set()
    for ref in refs:
        mcp_id = ref.get("mcp_id")
        tool_name = ref.get("tool_name", "*")
        if not mcp_id:
            continue

        mcp = next((m for m in MCP_CATALOG if m["id"] == mcp_id), None)
        if not mcp:
            continue

        tools_to_add = mcp.get("tools", [])
        if tool_name != "*":
            tools_to_add = [t for t in tools_to_add if t["name"] == tool_name]

        for t in tools_to_add:
            key = (mcp_id, t["name"])
            if key in seen:
                continue
            seen.add(key)
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
            "numero": {"type": "string", "description": "Número do destinatário com DDI+DDD. Ex: 5527999990000"},
            "mensagem": {"type": "string", "description": "Texto da mensagem a enviar ao lead. Use uma mensagem direta, em primeira pessoa, sem diálogos fictícios."},
        },
        "enviar_mensagem_direta": {
            "numero": {"type": "string", "description": "Número (DDI+DDD) — OPCIONAL se usar ticket_id"},
            "ticket_id": {"type": "string", "description": "ID exato do ticket — MODO MAIS SEGURO e PREFERÍVEL para enviar mensagem e garantir que chega na conversa certa"},
            "mensagem": {"type": "string", "description": "Texto a enviar ao lead — SOMENTE quando explicitamente pedido"},
        },
        "enviar_nota_interna": {
            "numero": {"type": "string", "description": "Número do contato — OPCIONAL se usar ticket_id"},
            "ticket_id": {"type": "string", "description": "ID direto do ticket (MUITO mais seguro que o número)"},
            "nota": {"type": "string", "description": "Texto da nota interna — NÃO aparece para o lead. Use para análises, qualificações e observações"},
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


# Tools padrão do ClickMassa quando agente não tem skill packs nem nodes configurados
CLICKMASSA_DEFAULT_TOOLS = [
    _make_tool_def("clickmassa", "enviar_mensagem", "Envia mensagem de texto ao lead"),
    _make_tool_def("clickmassa", "enviar_mensagem_direta", "Envia mensagem direta ao ticket"),
    _make_tool_def("clickmassa", "enviar_nota_interna", "Cria nota interna no ticket"),
    _make_tool_def("clickmassa", "criar_tarefa", "Cria tarefa, ligação ou compromisso"),
    _make_tool_def("clickmassa", "fechar_ticket", "Fecha o ticket"),
    _make_tool_def("clickmassa", "devolver_para_fila", "Devolve ticket para um atendente humano"),
    _make_tool_def("clickmassa", "atualizar_contato", "Atualiza dados do contato"),
]

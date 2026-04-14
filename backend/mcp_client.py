"""
mcp_client.py — MCPClient: ponto central de comunicação com o MCP ClickMassa.

O MCP ClickMassa (mcpclickmassa-production.up.railway.app) é o ÚNICO ponto de
contato dos agentes com o CRM. Esta classe abstrai o protocolo MCP (HTTP/SSE)
e expõe um método call_tool() simples para os agentes.

Arquitetura multi-tenant (Option B):
- Credenciais chegam POR REQUEST — cada workspace tem suas próprias chaves.
- Nenhuma credencial é armazenada no estado global desta classe.
- O cache de ferramentas disponíveis é indexado por URL do MCP (não por workspace).
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Configuração ─────────────────────────────────────────────────────────────

MCP_BASE_URL = "https://mcpclickmassa-production.up.railway.app"
MCP_TOOL_CALL_TIMEOUT = 30  # segundos por chamada de ferramenta
MCP_TOOLS_CACHE_TTL = 300   # 5 minutos de cache para lista de ferramentas


# ── Cache de lista de ferramentas com TTL ─────────────────────────────────────

class _ToolsCache:
    """Cache simples com TTL para lista de ferramentas disponíveis no MCP."""
    def __init__(self, ttl: int = MCP_TOOLS_CACHE_TTL):
        self._store: Dict[str, tuple] = {}  # url -> (tools_list, expires_at)
        self._ttl = ttl

    def get(self, url: str) -> Optional[List[dict]]:
        if url in self._store:
            tools, exp = self._store[url]
            if time.monotonic() < exp:
                return tools
            del self._store[url]
        return None

    def set(self, url: str, tools: List[dict]):
        self._store[url] = (tools, time.monotonic() + self._ttl)


_tools_cache = _ToolsCache()


# ── MCPClient ─────────────────────────────────────────────────────────────────

class MCPClient:
    """
    Cliente HTTP para o MCP ClickMassa.

    Comunicação via HTTP Streamable Transport (protocolo MCP moderno).
    Cada chamada envia uma requisição JSON-RPC POST ao endpoint /mcp.

    Uso:
        client = MCPClient()
        result = await client.call_tool("buscar_contato_por_numero",
                                        {"numero": "5527999990000"},
                                        credentials={"apiUrl": "...", "userToken": "..."})
    """

    def __init__(self, base_url: str = MCP_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._endpoint = f"{self.base_url}/mcp"

    def _build_headers(self, credentials: dict) -> dict:
        """
        Constrói cabeçalhos HTTP para autenticação no MCP.
        Suporta userToken (Bearer) ou apiUrl+email+password (fallback).
        """
        headers = {
            "Content-Type": "application/json",
            # MCP SDK exige AMBOS os tipos — responde em SSE, parseado abaixo
            "Accept": "application/json, text/event-stream",
        }
        user_token = credentials.get("userToken", "").strip()
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        # Passa metadados do workspace como cabeçalhos customizados
        api_url = credentials.get("apiUrl", "").strip()
        waba_id = credentials.get("wabaId", "").strip()
        if api_url:
            headers["X-CRM-Api-Url"] = api_url
        if waba_id:
            headers["X-CRM-Waba-Id"] = waba_id

        return headers

    async def list_tools(self, credentials: Optional[dict] = None) -> List[dict]:
        """
        Lista ferramentas disponíveis no MCP.
        Resultado é cacheado por 5 minutos para reduzir latência.
        """
        cache_key = self.base_url
        cached = _tools_cache.get(cache_key)
        if cached is not None:
            return cached

        headers = self._build_headers(credentials or {})
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(self._endpoint, json=payload, headers=headers)
                data = resp.json()
                tools = data.get("result", {}).get("tools", [])
                if tools:
                    _tools_cache.set(cache_key, tools)
                return tools
        except Exception as e:
            logger.warning(f"MCPClient.list_tools falhou ({self.base_url}): {e}")
            return []

    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        credentials: dict,
    ) -> dict:
        """
        Chama uma ferramenta no MCP ClickMassa via JSON-RPC.

        Parâmetros:
            tool_name: Nome da ferramenta (ex: "buscar_contato_por_numero")
            params: Argumentos da ferramenta
            credentials: Credenciais do workspace (apiUrl, userToken, wabaId)

        Retorna:
            dict com o resultado da ferramenta ou {"error": "..."} em caso de falha.
        """
        headers = self._build_headers(credentials)
        payload = {
            "jsonrpc": "2.0",
            "id": f"gaphub-{tool_name}-{int(time.time())}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=MCP_TOOL_CALL_TIMEOUT) as client:
                resp = await client.post(self._endpoint, json=payload, headers=headers)

                if resp.status_code == 401:
                    return {
                        "error": "Autenticação MCP falhou (401). "
                                 "Verifique userToken nas credenciais do agente.",
                        "http_status": 401,
                    }

                if resp.status_code == 404:
                    return {
                        "error": f"Ferramenta '{tool_name}' não encontrada no MCP.",
                        "http_status": 404,
                    }

                if resp.status_code >= 500:
                    return {
                        "error": f"Erro interno do servidor MCP (HTTP {resp.status_code}).",
                        "http_status": resp.status_code,
                    }

                try:
                    data = resp.json()
                except Exception:
                    # StreamableHTTPServerTransport pode responder no formato SSE:
                    # "event: message\ndata: {...json...}\n\n"
                    # Tentamos extrair o JSON da linha "data: ..."
                    raw = resp.text
                    data = None
                    for line in raw.splitlines():
                        line = line.strip()
                        if line.startswith("data:"):
                            candidate = line[5:].strip()
                            try:
                                data = json.loads(candidate)
                                break
                            except Exception:
                                continue
                    if data is None:
                        return {"error": f"Resposta MCP inválida (não-JSON): {raw[:500]}"}

                # JSON-RPC error
                if "error" in data:
                    rpc_err = data["error"]
                    return {
                        "error": rpc_err.get("message", str(rpc_err)),
                        "code": rpc_err.get("code"),
                    }

                # Resultado bem-sucedido
                result = data.get("result", {})

                # Desempacota content array (padrão MCP)
                if isinstance(result, dict) and "content" in result:
                    content_list = result["content"]
                    if isinstance(content_list, list):
                        texts = [
                            c.get("text", "") for c in content_list
                            if isinstance(c, dict) and c.get("type") == "text"
                        ]
                        combined = "\n".join(texts)
                        try:
                            return json.loads(combined)
                        except Exception:
                            return {"output": combined}

                return result if isinstance(result, dict) else {"output": result}

        except httpx.TimeoutException:
            return {
                "error": f"Timeout ao chamar ferramenta '{tool_name}' no MCP "
                         f"(>{MCP_TOOL_CALL_TIMEOUT}s). Tente novamente.",
            }
        except httpx.ConnectError:
            return {
                "error": f"Não foi possível conectar ao MCP em {self.base_url}. "
                         "Verifique conectividade.",
            }
        except Exception as e:
            logger.error(f"MCPClient.call_tool({tool_name}) erro inesperado: {e}")
            return {"error": str(e)}

    async def ping(self) -> bool:
        """Verifica se o MCP está acessível. Retorna True se OK."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code < 500
        except Exception:
            return False


# ── Instância global singleton ────────────────────────────────────────────────
# Reutilizada por todos os agentes para evitar overhead de criação repetida.

default_mcp_client = MCPClient(base_url=MCP_BASE_URL)


# ── Helpers para integração com agents.py ─────────────────────────────────────

async def execute_via_mcp(tool_name: str, params: dict, mcp_credentials: dict) -> dict:
    """
    Wrapper conveniente para chamar o MCP ClickMassa a partir dos agentes.
    Usado em agents.py como substituto às chamadas diretas à API CRM.

    mcp_credentials deve ter: apiUrl, userToken, wabaId (opcional)
    """
    return await default_mcp_client.call_tool(
        tool_name=tool_name,
        params=params,
        credentials=mcp_credentials,
    )


def extract_mcp_credentials(workspace_creds: dict) -> dict:
    """
    Extrai e normaliza credenciais MCP de um workspace_creds dict.
    Suporta tanto o formato legado (base_url/token/email) quanto o novo (apiUrl/userToken).
    """
    clickmassa_creds = workspace_creds.get("clickmassa", {})

    # Formato novo (preferido)
    api_url = clickmassa_creds.get("apiUrl", "").strip()
    user_token = clickmassa_creds.get("userToken", "").strip()
    waba_id = clickmassa_creds.get("wabaId", "").strip()

    # Fallback: formato legado
    if not api_url:
        api_url = clickmassa_creds.get("base_url", "").strip()
    if not user_token:
        user_token = clickmassa_creds.get("token", "").strip()

    return {
        "apiUrl": api_url,
        "userToken": user_token,
        "wabaId": waba_id,
        # Mantém campos legados para compatibilidade com tools.py
        "base_url": api_url,
        "token": user_token,
        "workspace_id": clickmassa_creds.get("workspace_id", ""),
    }

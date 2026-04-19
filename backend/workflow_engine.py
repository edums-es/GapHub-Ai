"""
backend/workflow_engine.py — Engine de workflow determinística para agentes GapHub.

Objetivo: substituir a "LLM solta decide sozinha" por um grafo de nós que o
operador desenha visualmente. O LLM ainda é usado, mas só para tarefas
específicas (classificar intenção, gerar texto), cada uma encapsulada num nó.

────────────────────────────────────────────────────────────────────────────
Tipos de nó
────────────────────────────────────────────────────────────────────────────

• trigger          — ponto de entrada (webhook, schedule, manual). Não executa.
• classify_intent  — LLM classifica a mensagem em uma das intents configuradas.
                     Salva em context.variables[config.variable] (default: "intent").
• branch           — roteia para outro nó baseado numa variável do contexto.
                     Cases: [{when: <valor>, to: <node_id>}]. Fallback: default.
• tool_call        — executa uma tool do MCP com params. Params aceitam
                     templating {{var}} → context.variables[var] ou campo do
                     contexto (ticket_id, contact_number, etc).
• llm_reply        — LLM gera texto livre com system prompt e contexto.
                     Salva em context.variables[config.output] (default: "reply").
• set_variable     — seta variáveis fixas no contexto (sem chamar LLM).
• send_message     — atalho: chama enviar_mensagem com {{output}} ou texto fixo.
                     Escrito à parte pq é a ação mais comum.
• end              — encerra o workflow.

────────────────────────────────────────────────────────────────────────────
Schema de workflow (MongoDB)
────────────────────────────────────────────────────────────────────────────

{
    "workflow_id": "wf_xxx",
    "workspace_id": "...",
    "name": "Atendimento WhatsApp",
    "description": "...",
    "trigger_type": "webhook" | "schedule" | "manual",
    "nodes": [
        {
            "id": "n1",
            "type": "trigger" | "classify_intent" | "branch" | "tool_call"
                    | "llm_reply" | "set_variable" | "send_message" | "end",
            "label": "texto amigável pro usuário",
            "position": {"x": 0, "y": 0},   # só pra UI
            "config": { ... },               # específico do tipo
            "next": "<node_id>"              # próximo nó (exceto branch)
        },
        ...
    ],
    "created_at": ...,
    "updated_at": ...,
}

Branch usa `config.cases` e `config.default` em vez de `next`.

────────────────────────────────────────────────────────────────────────────
Contexto de execução
────────────────────────────────────────────────────────────────────────────

{
    "input": "mensagem do lead",
    "ticket_id": "66397",
    "contact_id": "...",
    "contact_number": "5511987654321",
    "contact_name": "João",
    "workspace_id": "...",
    "variables": {},       # classify_intent, llm_reply, set_variable escrevem aqui
    "steps": [],           # trace de execução (auditoria)
    "output": "",          # texto final enviado ao lead (se houver)
    "errors": [],          # erros não-fatais
}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import litellm

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Tipos
# ═════════════════════════════════════════════════════════════════════════

NODE_TYPES = {
    "trigger",
    "classify_intent",
    "branch",
    "tool_call",
    "llm_reply",
    "set_variable",
    "send_message",
    "end",
}

# Máximo de nós executados por run (evita loop)
MAX_STEPS_PER_RUN = 30


# ═════════════════════════════════════════════════════════════════════════
# Template rendering: {{var}} → context.variables[var] ou campo do contexto
# ═════════════════════════════════════════════════════════════════════════

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def render_template(template: Any, context: Dict[str, Any]) -> Any:
    """
    Renderiza strings com placeholders {{nome}}:
      1. busca em context.variables (nível raso)
      2. busca em campos top-level do contexto (ticket_id, contact_number, etc)
      3. suporta acesso aninhado com ponto: {{lead.nome}} → context['lead']['nome']

    Se o template for dict/list, recursa. Outros tipos passam inalterados.
    """
    if isinstance(template, str):
        def replace(match: "re.Match[str]") -> str:
            path = match.group(1)
            value = _resolve_path(path, context)
            return "" if value is None else str(value)
        return _TEMPLATE_RE.sub(replace, template)
    if isinstance(template, dict):
        return {k: render_template(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(v, context) for v in template]
    return template


def _resolve_path(path: str, context: Dict[str, Any]) -> Any:
    parts = path.split(".")
    variables = context.get("variables") or {}
    # Primeiro procura em variables
    if parts[0] in variables:
        cursor = variables[parts[0]]
        for p in parts[1:]:
            if isinstance(cursor, dict):
                cursor = cursor.get(p)
            else:
                return None
        return cursor
    # Depois em campos do contexto raiz
    if parts[0] in context:
        cursor = context[parts[0]]
        for p in parts[1:]:
            if isinstance(cursor, dict):
                cursor = cursor.get(p)
            else:
                return None
        return cursor
    return None


# ═════════════════════════════════════════════════════════════════════════
# Executores de nó
# ═════════════════════════════════════════════════════════════════════════


async def _exec_trigger(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger é só marcador — não executa nada."""
    return {"status": "ok", "message": "trigger ativo"}


async def _exec_set_variable(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """Seta variáveis estáticas no contexto. config.variables = {nome: valor}."""
    config = node.get("config") or {}
    vars_to_set = config.get("variables") or {}
    rendered = render_template(vars_to_set, context)
    if not isinstance(rendered, dict):
        return {"status": "error", "error": "config.variables deve ser dict"}
    for k, v in rendered.items():
        context["variables"][k] = v
    return {"status": "ok", "set": list(rendered.keys())}


async def _exec_classify_intent(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Usa LLM para classificar a última mensagem do lead em uma das intents
    configuradas. Salva resultado em context.variables[output_var].

    config:
      intents: [{id: "agendar", description: "..."}, ...]
      output: "intent"  (nome da variável, default)
      model:  "openai/gpt-4o-mini" (opcional, default do agente)
      input_var: "input" (qual campo do contexto classificar, default)
    """
    config = node.get("config") or {}
    intents = config.get("intents") or []
    if not intents:
        return {"status": "error", "error": "intents vazia"}

    output_var = config.get("output") or "intent"
    input_field = config.get("input_var") or "input"
    text = context.get(input_field) or context.get("variables", {}).get(input_field) or ""

    model = config.get("model") or deps.get("default_model") or "openai/gpt-4o-mini"
    llm_kwargs = deps.get("llm_kwargs") or {}

    intent_lines = "\n".join(
        f"- {i['id']}: {i.get('description', '')}" for i in intents
    )
    valid_ids = [i["id"] for i in intents]

    system = (
        "Você classifica a intenção de mensagens de leads em UMA das categorias abaixo.\n"
        "Responda APENAS em JSON válido no formato: {\"intent\": \"<id>\", \"confidence\": 0.0-1.0}\n\n"
        f"Categorias disponíveis:\n{intent_lines}\n\n"
        "Se nenhuma casar perfeitamente, escolha a mais próxima e use confidence baixa."
    )
    user_msg = f"Mensagem do lead:\n\"\"\"\n{text}\n\"\"\""

    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            **llm_kwargs,
        )
        raw = resp["choices"][0]["message"]["content"] or "{}"
        parsed = json.loads(raw)
    except Exception as e:
        logger.warning(f"[workflow classify_intent] LLM falhou: {e}")
        parsed = {"intent": valid_ids[0] if valid_ids else "", "confidence": 0.0}

    intent_val = parsed.get("intent") or ""
    if intent_val not in valid_ids:
        # Fallback: usa o primeiro id como default para não travar a engine
        intent_val = valid_ids[0] if valid_ids else ""

    context["variables"][output_var] = intent_val
    context["variables"][f"{output_var}_confidence"] = float(parsed.get("confidence", 0.0) or 0.0)

    return {
        "status": "ok",
        "intent": intent_val,
        "confidence": context["variables"][f"{output_var}_confidence"],
    }


async def _exec_branch(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Roteia baseado numa variável do contexto.
    config:
      on: "intent"  (nome da variável)
      cases: [{when: "agendar", to: "n_agendar"}, ...]
      default: "n_default"  (id do nó fallback)
    """
    config = node.get("config") or {}
    on_var = config.get("on") or "intent"
    cases = config.get("cases") or []
    default_to = config.get("default")

    current_value = context.get("variables", {}).get(on_var)
    if current_value is None:
        current_value = context.get(on_var)

    for case in cases:
        if str(case.get("when")) == str(current_value):
            return {"status": "ok", "matched": case.get("when"), "next_override": case.get("to")}

    return {"status": "ok", "matched": None, "next_override": default_to}


async def _exec_tool_call(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executa uma tool via deps['execute_tool'](mcp_id, tool_name, params, creds).
    config:
      mcp_id:    "clickmassa"
      tool_name: "criar_tarefa"
      params:    {campo: valor ou "{{var}}"}
      save_as:   "result"  (opcional — salva resultado em variables[save_as])
    """
    config = node.get("config") or {}
    mcp_id = config.get("mcp_id") or "clickmassa"
    tool_name = config.get("tool_name") or ""
    raw_params = config.get("params") or {}
    save_as = config.get("save_as")

    if not tool_name:
        return {"status": "error", "error": "tool_name vazio"}

    params = render_template(raw_params, context)
    creds = (deps.get("workspace_creds") or {}).get(mcp_id, {})

    execute_tool = deps.get("execute_tool")
    if not execute_tool:
        return {"status": "error", "error": "execute_tool não provida à engine"}

    try:
        result = await execute_tool(mcp_id, tool_name, params, creds)
    except Exception as e:
        logger.error(f"[workflow tool_call] {tool_name} falhou: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "tool": tool_name}

    if save_as:
        context["variables"][save_as] = result

    # Se for enviar_mensagem bem-sucedido, propaga no output
    if "enviar_mensagem" in tool_name and params.get("mensagem"):
        context["output"] = params["mensagem"]

    return {"status": "ok", "tool": tool_name, "params": params, "result_preview": _truncate(result)}


async def _exec_llm_reply(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gera texto livre com o LLM. Salva em variables[output].
    config:
      system: "Você é um assistente..."  (template-expandido)
      user:   "Pergunta do lead: {{input}}"  (opcional — default é {{input}})
      model:  "openai/gpt-4o-mini"
      output: "reply"  (default)
      temperature: 0.3
    """
    config = node.get("config") or {}
    system = render_template(config.get("system") or "Você é um assistente útil.", context)
    user = render_template(config.get("user") or "{{input}}", context)
    model = config.get("model") or deps.get("default_model") or "openai/gpt-4o-mini"
    output_var = config.get("output") or "reply"
    temperature = config.get("temperature", 0.3)
    llm_kwargs = deps.get("llm_kwargs") or {}

    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            **llm_kwargs,
        )
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        logger.error(f"[workflow llm_reply] LLM falhou: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

    context["variables"][output_var] = text
    context["output"] = text  # última resposta do LLM vira o output padrão
    return {"status": "ok", "text_preview": text[:200]}


async def _exec_send_message(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atalho: chama enviar_mensagem com a mensagem do config ou {{reply}}/{{output}}.
    config:
      message: "texto ou {{reply}} (default)"
      use_push_api: True (default — garante que aparece como empresa no CRM)
    """
    config = node.get("config") or {}
    template = config.get("message") or "{{reply}}" if context.get("variables", {}).get("reply") else "{{output}}"
    mensagem = render_template(template, context)
    if not mensagem:
        return {"status": "skipped", "reason": "mensagem vazia"}

    numero = context.get("contact_number") or ""
    ticket_id = context.get("ticket_id") or ""

    execute_tool = deps.get("execute_tool")
    creds = (deps.get("workspace_creds") or {}).get("clickmassa", {})

    if not execute_tool:
        return {"status": "error", "error": "execute_tool não provida"}

    if numero:
        params = {"numero": numero, "mensagem": mensagem}
        tool = "enviar_mensagem"
    elif ticket_id:
        params = {"ticket_id": ticket_id, "mensagem": mensagem}
        tool = "enviar_mensagem_direta"
    else:
        return {"status": "error", "error": "sem contact_number nem ticket_id"}

    try:
        result = await execute_tool("clickmassa", tool, params, creds)
    except Exception as e:
        logger.error(f"[workflow send_message] falhou: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

    context["output"] = mensagem
    return {"status": "ok", "tool": tool, "mensagem": mensagem, "result_preview": _truncate(result)}


async def _exec_end(node: Dict[str, Any], context: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "terminated": True}


NODE_EXECUTORS: Dict[str, Callable] = {
    "trigger": _exec_trigger,
    "classify_intent": _exec_classify_intent,
    "branch": _exec_branch,
    "tool_call": _exec_tool_call,
    "llm_reply": _exec_llm_reply,
    "set_variable": _exec_set_variable,
    "send_message": _exec_send_message,
    "end": _exec_end,
}


# ═════════════════════════════════════════════════════════════════════════
# Engine principal
# ═════════════════════════════════════════════════════════════════════════


def _truncate(obj: Any, limit: int = 500) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + "…"


def _find_node(workflow: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    for n in workflow.get("nodes") or []:
        if n.get("id") == node_id:
            return n
    return None


def _find_trigger(workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for n in workflow.get("nodes") or []:
        if n.get("type") == "trigger":
            return n
    # Se não houver trigger explícito, usa o primeiro nó
    nodes = workflow.get("nodes") or []
    return nodes[0] if nodes else None


def _next_node_id(node: Dict[str, Any], step_result: Dict[str, Any]) -> Optional[str]:
    """Determina para qual nó ir em seguida."""
    # Branch retorna o override
    if node.get("type") == "branch":
        return step_result.get("next_override")
    # Demais nós: usa node.next
    return node.get("next")


def validate_workflow(workflow: Dict[str, Any]) -> List[str]:
    """Valida o workflow. Retorna lista de erros (vazia se ok)."""
    errors: List[str] = []
    nodes = workflow.get("nodes") or []
    if not nodes:
        errors.append("Workflow sem nós.")
        return errors

    ids = set()
    for n in nodes:
        nid = n.get("id")
        ntype = n.get("type")
        if not nid:
            errors.append(f"Nó sem id: {n}")
            continue
        if nid in ids:
            errors.append(f"Id duplicado: {nid}")
        ids.add(nid)
        if ntype not in NODE_TYPES:
            errors.append(f"Nó {nid}: tipo inválido '{ntype}'")

    # Validar que os 'next' apontam para ids existentes
    for n in nodes:
        nid = n.get("id")
        ntype = n.get("type")
        if ntype == "end":
            continue
        if ntype == "branch":
            for case in (n.get("config") or {}).get("cases") or []:
                to = case.get("to")
                if to and to not in ids:
                    errors.append(f"Nó {nid}: case aponta para id inexistente '{to}'")
            default = (n.get("config") or {}).get("default")
            if default and default not in ids:
                errors.append(f"Nó {nid}: default aponta para id inexistente '{default}'")
        else:
            nxt = n.get("next")
            if nxt and nxt not in ids:
                errors.append(f"Nó {nid}: next aponta para id inexistente '{nxt}'")

    # Exige um nó do tipo trigger explícito (não usa o fallback do _find_trigger)
    has_trigger = any(n.get("type") == "trigger" for n in nodes)
    if not has_trigger:
        errors.append("Workflow sem nó trigger.")

    return errors


async def execute_workflow(
    workflow: Dict[str, Any],
    context: Dict[str, Any],
    deps: Dict[str, Any],
    *,
    start_node_id: Optional[str] = None,
    max_steps: int = MAX_STEPS_PER_RUN,
) -> Dict[str, Any]:
    """
    Executa o workflow. Retorna o contexto atualizado + lista de steps.

    deps: dict com dependências injetadas:
      - execute_tool: async Callable(mcp_id, tool_name, params, creds) → result
      - workspace_creds: dict[mcp_id, creds]
      - default_model: str (fallback para LLM em classify_intent/llm_reply)
      - llm_kwargs: dict (api_base, api_key, etc)

    context esperado (pelo menos):
      - input: str (mensagem do lead)
      - ticket_id, contact_number, contact_id, contact_name (opcional)
      - variables: dict (será preenchido)
      - steps: list (será preenchido)
    """
    # Inicializa campos obrigatórios do contexto
    context.setdefault("variables", {})
    context.setdefault("steps", [])
    context.setdefault("output", "")
    context.setdefault("errors", [])
    context.setdefault("workflow_id", workflow.get("workflow_id"))

    # Determina ponto de partida
    if start_node_id:
        current = _find_node(workflow, start_node_id)
    else:
        current = _find_trigger(workflow)

    if current is None:
        context["errors"].append("Workflow sem nó de entrada.")
        return context

    run_id = f"wfrun_{uuid.uuid4().hex[:12]}"
    context["run_id"] = run_id
    started_at = time.time()

    for step_idx in range(max_steps):
        ntype = current.get("type")
        executor = NODE_EXECUTORS.get(ntype)
        if executor is None:
            context["errors"].append(f"Tipo de nó desconhecido: {ntype}")
            break

        t0 = time.time()
        try:
            result = await executor(current, context, deps)
        except Exception as e:
            logger.error(f"[workflow {run_id}] nó {current.get('id')} explodiu: {e}", exc_info=True)
            result = {"status": "error", "error": str(e)}
            context["errors"].append(f"{current.get('id')}: {e}")

        step_record = {
            "node_id": current.get("id"),
            "node_type": ntype,
            "node_label": current.get("label", ""),
            "duration_ms": int((time.time() - t0) * 1000),
            "result": result,
        }
        context["steps"].append(step_record)

        # Se o executor falhou hard, abortamos
        if result.get("status") == "error" and ntype in ("tool_call", "send_message", "llm_reply"):
            # Erros em ação são fatais só se não houver fallback — por enquanto, abortamos
            logger.warning(f"[workflow {run_id}] abortando em {current.get('id')}: {result}")
            break

        # End node encerra o workflow
        if ntype == "end":
            break

        next_id = _next_node_id(current, result)
        if not next_id:
            # Sem próximo — fim do caminho
            break

        next_node = _find_node(workflow, next_id)
        if next_node is None:
            context["errors"].append(f"Nó '{next_id}' não encontrado.")
            break
        current = next_node
    else:
        # Loop estourou
        context["errors"].append(f"MAX_STEPS ({max_steps}) atingido — possível loop.")

    context["duration_ms"] = int((time.time() - started_at) * 1000)
    context["finished_at"] = datetime.now(timezone.utc).isoformat()
    return context

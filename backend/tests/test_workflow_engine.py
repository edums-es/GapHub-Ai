"""
Tests para backend/workflow_engine.py — cobre render_template, validate_workflow
e execute_workflow com LLM e tools mockados.
"""

import pytest
from unittest.mock import AsyncMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# render_template
# ─────────────────────────────────────────────────────────────────────────────


def test_render_template_strings():
    from workflow_engine import render_template
    ctx = {"ticket_id": "123", "variables": {"intent": "agendar"}}
    assert render_template("ticket={{ticket_id}}", ctx) == "ticket=123"
    assert render_template("intent={{intent}}", ctx) == "intent=agendar"


def test_render_template_missing_returns_empty():
    from workflow_engine import render_template
    ctx = {"variables": {}}
    assert render_template("ola {{nome}}", ctx) == "ola "


def test_render_template_nested():
    from workflow_engine import render_template
    ctx = {"variables": {"lead": {"nome": "Joao", "tel": "5511"}}}
    assert render_template("oi {{lead.nome}}", ctx) == "oi Joao"


def test_render_template_dict_recursive():
    from workflow_engine import render_template
    ctx = {"ticket_id": "77", "variables": {"reply": "olá"}}
    template = {"ticket_id": "{{ticket_id}}", "body": "{{reply}}"}
    assert render_template(template, ctx) == {"ticket_id": "77", "body": "olá"}


def test_render_template_passthrough_non_string():
    from workflow_engine import render_template
    assert render_template(42, {}) == 42
    assert render_template(True, {}) is True
    assert render_template(None, {}) is None


# ─────────────────────────────────────────────────────────────────────────────
# validate_workflow
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_workflow_empty():
    from workflow_engine import validate_workflow
    errors = validate_workflow({"nodes": []})
    assert any("sem nós" in e.lower() for e in errors)


def test_validate_workflow_missing_trigger():
    from workflow_engine import validate_workflow
    wf = {"nodes": [{"id": "a", "type": "end", "config": {}}]}
    errors = validate_workflow(wf)
    assert any("trigger" in e.lower() for e in errors)


def test_validate_workflow_invalid_next():
    from workflow_engine import validate_workflow
    wf = {
        "nodes": [
            {"id": "a", "type": "trigger", "next": "inexistente", "config": {}},
        ]
    }
    errors = validate_workflow(wf)
    assert any("inexistente" in e for e in errors)


def test_validate_workflow_valid():
    from workflow_engine import validate_workflow
    wf = {
        "nodes": [
            {"id": "a", "type": "trigger", "next": "b", "config": {}},
            {"id": "b", "type": "end", "config": {}},
        ]
    }
    errors = validate_workflow(wf)
    assert errors == []


def test_validate_workflow_branch_cases():
    from workflow_engine import validate_workflow
    wf = {
        "nodes": [
            {"id": "a", "type": "trigger", "next": "b", "config": {}},
            {"id": "b", "type": "branch", "config": {
                "on": "intent",
                "cases": [{"when": "x", "to": "nao_existe"}],
                "default": "c",
            }},
            {"id": "c", "type": "end", "config": {}},
        ]
    }
    errors = validate_workflow(wf)
    assert any("nao_existe" in e for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# execute_workflow — branch + tool_call (sem LLM)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_workflow_simple_tool_call():
    from workflow_engine import execute_workflow

    tool_mock = AsyncMock(return_value={"ok": True, "id": 999})

    wf = {
        "workflow_id": "t1",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "t", "config": {}},
            {
                "id": "t",
                "type": "tool_call",
                "next": "end",
                "config": {
                    "mcp_id": "clickmassa",
                    "tool_name": "criar_tarefa",
                    "params": {"titulo": "Call com {{contact_name}}", "ticket_id": "{{ticket_id}}"},
                    "save_as": "tarefa",
                },
            },
            {"id": "end", "type": "end", "config": {}},
        ],
    }
    context = {
        "input": "marca call",
        "ticket_id": "77",
        "contact_name": "Eduardo",
        "variables": {},
        "steps": [],
    }
    deps = {"execute_tool": tool_mock, "workspace_creds": {"clickmassa": {}}}

    result = await execute_workflow(wf, context, deps)

    assert result["variables"]["tarefa"] == {"ok": True, "id": 999}
    assert len(result["steps"]) == 3  # trigger + tool + end
    # params foram renderizados
    tool_mock.assert_called_once()
    args = tool_mock.call_args[0]
    assert args[0] == "clickmassa"
    assert args[1] == "criar_tarefa"
    assert args[2] == {"titulo": "Call com Eduardo", "ticket_id": "77"}


@pytest.mark.asyncio
async def test_execute_workflow_branch_routes_by_variable():
    from workflow_engine import execute_workflow

    tool_mock = AsyncMock(return_value={"ok": True})

    wf = {
        "workflow_id": "t2",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "setvar", "config": {}},
            {
                "id": "setvar",
                "type": "set_variable",
                "next": "b",
                "config": {"variables": {"intent": "agendar"}},
            },
            {
                "id": "b",
                "type": "branch",
                "config": {
                    "on": "intent",
                    "cases": [
                        {"when": "agendar", "to": "path_agendar"},
                        {"when": "email", "to": "path_email"},
                    ],
                    "default": "path_default",
                },
            },
            {
                "id": "path_agendar",
                "type": "tool_call",
                "next": "end",
                "config": {"mcp_id": "x", "tool_name": "criar_tarefa", "params": {}},
            },
            {
                "id": "path_email",
                "type": "tool_call",
                "next": "end",
                "config": {"mcp_id": "x", "tool_name": "atualizar_contato", "params": {}},
            },
            {
                "id": "path_default",
                "type": "tool_call",
                "next": "end",
                "config": {"mcp_id": "x", "tool_name": "nada", "params": {}},
            },
            {"id": "end", "type": "end", "config": {}},
        ],
    }
    context = {"input": "x", "variables": {}, "steps": []}
    deps = {"execute_tool": tool_mock, "workspace_creds": {"x": {}}}

    result = await execute_workflow(wf, context, deps)

    # Deve ter chamado criar_tarefa (path_agendar) e NÃO os outros
    tools_called = [c.args[1] for c in tool_mock.call_args_list]
    assert "criar_tarefa" in tools_called
    assert "atualizar_contato" not in tools_called
    assert "nada" not in tools_called
    # Passou pelo set_variable
    assert result["variables"]["intent"] == "agendar"


@pytest.mark.asyncio
async def test_execute_workflow_branch_default_when_no_match():
    from workflow_engine import execute_workflow

    tool_mock = AsyncMock(return_value={"ok": True})

    wf = {
        "workflow_id": "t3",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "setvar", "config": {}},
            {"id": "setvar", "type": "set_variable", "next": "b", "config": {"variables": {"intent": "xxx_desconhecido"}}},
            {"id": "b", "type": "branch", "config": {
                "on": "intent",
                "cases": [{"when": "agendar", "to": "path_a"}],
                "default": "path_default",
            }},
            {"id": "path_a", "type": "tool_call", "next": "end", "config": {"mcp_id": "x", "tool_name": "agendar", "params": {}}},
            {"id": "path_default", "type": "tool_call", "next": "end", "config": {"mcp_id": "x", "tool_name": "fallback", "params": {}}},
            {"id": "end", "type": "end", "config": {}},
        ],
    }
    context = {"input": "x", "variables": {}, "steps": []}
    deps = {"execute_tool": tool_mock, "workspace_creds": {"x": {}}}

    await execute_workflow(wf, context, deps)

    called = [c.args[1] for c in tool_mock.call_args_list]
    assert "fallback" in called
    assert "agendar" not in called


@pytest.mark.asyncio
async def test_execute_workflow_max_steps_prevents_loop():
    """Se o workflow tiver ciclo infinito, abortamos em MAX_STEPS."""
    from workflow_engine import execute_workflow

    wf = {
        "workflow_id": "loop",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "a", "config": {}},
            {"id": "a", "type": "set_variable", "next": "b", "config": {"variables": {"x": 1}}},
            {"id": "b", "type": "set_variable", "next": "a", "config": {"variables": {"y": 1}}},  # volta pra a
        ],
    }
    context = {"input": "", "variables": {}, "steps": []}
    deps = {"execute_tool": AsyncMock(), "workspace_creds": {}}

    result = await execute_workflow(wf, context, deps, max_steps=10)
    assert any("MAX_STEPS" in e or "loop" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_execute_workflow_send_message_uses_push_api():
    """send_message deve chamar enviar_mensagem (Push API) com número do contato."""
    from workflow_engine import execute_workflow

    tool_mock = AsyncMock(return_value={"ok": True})

    wf = {
        "workflow_id": "send",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "setreply", "config": {}},
            {"id": "setreply", "type": "set_variable", "next": "send", "config": {"variables": {"reply": "olá!"}}},
            {"id": "send", "type": "send_message", "next": "end", "config": {"message": "{{reply}}"}},
            {"id": "end", "type": "end", "config": {}},
        ],
    }
    context = {
        "input": "oi",
        "ticket_id": "77",
        "contact_number": "5511999887766",
        "variables": {},
        "steps": [],
    }
    deps = {"execute_tool": tool_mock, "workspace_creds": {"clickmassa": {}}}

    result = await execute_workflow(wf, context, deps)

    tool_mock.assert_called_once()
    args = tool_mock.call_args[0]
    assert args[0] == "clickmassa"
    assert args[1] == "enviar_mensagem"  # Push API (não enviar_mensagem_direta)
    assert args[2]["numero"] == "5511999887766"
    assert args[2]["mensagem"] == "olá!"
    assert result["output"] == "olá!"


# ─────────────────────────────────────────────────────────────────────────────
# classify_intent — com LLM mockado
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_sets_variable():
    from workflow_engine import execute_workflow

    # Mock litellm.acompletion
    mock_resp = {
        "choices": [{"message": {"content": '{"intent": "agendar", "confidence": 0.9}'}}]
    }

    wf = {
        "workflow_id": "cls",
        "nodes": [
            {"id": "start", "type": "trigger", "next": "c", "config": {}},
            {"id": "c", "type": "classify_intent", "next": "end", "config": {
                "output": "intent",
                "intents": [
                    {"id": "agendar", "description": "marcar reuniao"},
                    {"id": "saudacao", "description": "oi/bom dia"},
                ],
            }},
            {"id": "end", "type": "end", "config": {}},
        ],
    }
    context = {"input": "quero marcar uma call", "variables": {}, "steps": []}
    deps = {"execute_tool": AsyncMock(), "workspace_creds": {}, "default_model": "openai/gpt-4o-mini"}

    with patch("workflow_engine.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
        result = await execute_workflow(wf, context, deps)

    assert result["variables"]["intent"] == "agendar"
    assert result["variables"]["intent_confidence"] == 0.9


@pytest.mark.asyncio
async def test_classify_intent_fallback_on_invalid_response():
    """Se LLM retornar intent fora da lista, engine cai no primeiro id."""
    from workflow_engine import execute_workflow

    mock_resp = {
        "choices": [{"message": {"content": '{"intent": "xyz_invalido", "confidence": 0.5}'}}]
    }

    wf = {
        "workflow_id": "cls2",
        "nodes": [
            {"id": "s", "type": "trigger", "next": "c", "config": {}},
            {"id": "c", "type": "classify_intent", "next": "e", "config": {
                "intents": [
                    {"id": "agendar", "description": "x"},
                    {"id": "saudacao", "description": "y"},
                ],
            }},
            {"id": "e", "type": "end", "config": {}},
        ],
    }
    context = {"input": "msg", "variables": {}, "steps": []}
    deps = {"execute_tool": AsyncMock(), "workspace_creds": {}}

    with patch("workflow_engine.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
        result = await execute_workflow(wf, context, deps)

    # Fallback: primeiro id da lista
    assert result["variables"]["intent"] == "agendar"


# ─────────────────────────────────────────────────────────────────────────────
# Templates built-in
# ─────────────────────────────────────────────────────────────────────────────


def test_all_templates_validate():
    from workflow_engine import validate_workflow
    from workflow_templates import WORKFLOW_TEMPLATES
    for tmpl in WORKFLOW_TEMPLATES:
        errors = validate_workflow(tmpl)
        assert errors == [], f"Template '{tmpl['template_id']}' inválido: {errors}"


def test_template_atendimento_has_all_expected_branches():
    from workflow_templates import get_template
    t = get_template("atendimento_whatsapp")
    assert t
    node_ids = {n["id"] for n in t["nodes"]}
    for expected in ("classify", "route", "agendar_tarefa", "transferir_humano",
                      "responder_saudacao", "responder_duvida", "atualizar_contato"):
        assert expected in node_ids, f"Template atendimento sem nó {expected}"

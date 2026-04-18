"""
Testes unitários dos helpers anti-loop e do catálogo de skill packs.

Foco: garantir que os mecanismos cirúrgicos de proteção contra loops do LLM
continuam funcionando em caso de refactor. Todos os testes são determinísticos
e rodam offline (sem DB, sem LLM, sem rede).
"""
import os
import sys

# Garante que o backend/ está no path para importar os módulos em teste.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Evita inicialização de Fernet durante o import (não queremos gerar chave em teste)
os.environ.setdefault("ENCRYPTION_KEY", "BUnQzvxcWw6w1Owg271R_iz_H1J9jCLBUE4T-kI8tjo=")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "gaphub_test")
# JWT_SECRET é requerido pelo auth.py no import-time
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-used-in-tests")

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# _sanitize_agent_text — corta hallucinated dialogue
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    # Caso simples: LLM responde apenas texto legítimo
    ("Olá João, tudo bem por aqui!", "Olá João, tudo bem por aqui!"),
    # LLM hallucina diálogo com "Lead:" — cortar no marcador
    (
        "Olá João!\n\nLead: tudo bem?\nAgente: sim!",
        "Olá João!",
    ),
    # Variação com [LEAD]: (prefixo do formatador de tickets)
    (
        "Claro, posso ajudar.\n[LEAD]: obrigado",
        "Claro, posso ajudar.",
    ),
    # Variação com "Cliente:"
    (
        "Vou verificar e te retorno.\nCliente: beleza",
        "Vou verificar e te retorno.",
    ),
    # Marcador no meio de uma linha não deve cortar (só em início de linha)
    (
        "O Cliente: João pediu desconto",
        "O Cliente: João pediu desconto",
    ),
    # String vazia / None
    ("", ""),
    (None, ""),
    # Só markers (resposta hallucinada do início ao fim) → vazio
    ("Lead: hi\nAgente: ok", ""),
])
def test_sanitize_agent_text(raw, expected):
    from agents import _sanitize_agent_text
    assert _sanitize_agent_text(raw) == expected


# ─────────────────────────────────────────────────────────────────────────────
# _is_send_tool — identifica corretamente ferramentas de envio
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn_name,expected", [
    # Envios visíveis ao lead → True
    ("enviar_mensagem", True),
    ("enviar_mensagem_direta", True),
    ("enviar_midia", True),
    ("clickmassa__enviar_mensagem", True),
    ("clickmassa__enviar_mensagem_direta", True),
    # Nota interna NÃO é envio visível → False
    ("enviar_nota_interna", False),
    ("clickmassa__enviar_nota_interna", False),
    # Outras tools → False
    ("buscar_contato_por_numero", False),
    ("listar_tickets_pendentes", False),
    ("", False),
    (None, False),
])
def test_is_send_tool(fn_name, expected):
    from agents import _is_send_tool
    assert _is_send_tool(fn_name) is expected


# ─────────────────────────────────────────────────────────────────────────────
# _extract_clean_user_input — remove envelope do webhook
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_clean_user_input_from_webhook():
    from agents import _extract_clean_user_input
    raw = (
        '[WEBHOOK AUTOMÁTICO — RESPOSTA OBRIGATÓRIA]\n'
        'Mensagem recebida do lead via CRM:\n'
        '"Olá, queria saber o preço"\n'
        'Ticket ID: 123\n'
        'Contato: João (+5511987654321)\n\n'
        'INSTRUÇÃO OBRIGATÓRIA: Use a ferramenta enviar_mensagem_direta...'
    )
    assert _extract_clean_user_input(raw) == "Olá, queria saber o preço"


def test_extract_clean_user_input_passthrough():
    """Se não for payload de webhook, retorna como veio."""
    from agents import _extract_clean_user_input
    assert _extract_clean_user_input("  mensagem normal do chat  ") == "mensagem normal do chat"
    assert _extract_clean_user_input("") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Skill packs — catálogo, expansão e prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_skill_packs_catalog_has_minimum_packs():
    from skill_packs import SKILL_PACKS
    ids = {p["id"] for p in SKILL_PACKS}
    # Os packs que a proposta comercial exige
    required = {"responder_mensagens", "qualificacao", "followup"}
    assert required.issubset(ids), f"Faltando packs obrigatórios: {required - ids}"


def test_skill_packs_each_has_required_fields():
    from skill_packs import SKILL_PACKS
    required_keys = {"id", "name", "description", "category", "mcp_id", "tools", "prompt"}
    for pack in SKILL_PACKS:
        missing = required_keys - set(pack.keys())
        assert not missing, f"Pack {pack.get('id')} sem campos: {missing}"


def test_expand_packs_to_tool_refs_dedupes():
    from skill_packs import expand_packs_to_tool_refs, get_pack
    # responder_mensagens e handoff compartilham enviar_nota_interna → dedup esperado
    pack_a = get_pack("responder_mensagens")
    pack_b = get_pack("handoff")
    shared = set(pack_a["tools"]) & set(pack_b["tools"])
    assert shared, "Esperava overlap entre responder_mensagens e handoff para testar dedup"

    refs = expand_packs_to_tool_refs(["responder_mensagens", "handoff"])
    tool_names = [r["tool_name"] for r in refs]
    # Cada tool deve aparecer NO MÁXIMO uma vez
    for tn in tool_names:
        assert tool_names.count(tn) == 1, f"Tool {tn} duplicada na expansão"


def test_expand_packs_unknown_pack_is_ignored():
    from skill_packs import expand_packs_to_tool_refs
    refs = expand_packs_to_tool_refs(["pack_inexistente", "responder_mensagens"])
    assert len(refs) > 0
    # Todas as tools expandidas pertencem ao pack válido
    assert all(r["mcp_id"] for r in refs)


def test_compose_packs_prompt_concatenates():
    from skill_packs import compose_packs_prompt
    out = compose_packs_prompt(["responder_mensagens", "qualificacao"])
    assert "RESPONDER MENSAGENS" in out
    assert "QUALIFICAÇÃO" in out
    # Ordem do catálogo é estável
    assert out.index("RESPONDER MENSAGENS") < out.index("QUALIFICAÇÃO")


def test_compose_packs_prompt_empty():
    from skill_packs import compose_packs_prompt
    assert compose_packs_prompt([]) == ""
    assert compose_packs_prompt(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# build_tool_definitions — integração com skill packs
# ─────────────────────────────────────────────────────────────────────────────

def test_build_tool_definitions_from_skill_packs_only():
    """Agente sem nodes mas com enabled_skill_packs deve expor as tools dos packs."""
    from tools import build_tool_definitions
    agent = {
        "agent_id": "a1",
        "nodes": [],
        "enabled_skill_packs": ["responder_mensagens"],
    }
    defs = build_tool_definitions([], agent=agent)
    tool_names = [d["function"]["name"] for d in defs]
    # enviar_mensagem_direta está em responder_mensagens
    assert any("enviar_mensagem_direta" in n for n in tool_names)


def test_build_tool_definitions_nodes_and_packs_union():
    """Se o agente tem nodes E packs, a união é exposta (com dedup)."""
    from tools import build_tool_definitions
    agent = {
        "agent_id": "a1",
        "nodes": [
            {"type": "tool", "config": {"mcp_id": "clickmassa", "tool_name": "fechar_ticket"}},
        ],
        "enabled_skill_packs": ["responder_mensagens"],
    }
    defs = build_tool_definitions(agent["nodes"], agent=agent)
    tool_names = [d["function"]["name"] for d in defs]
    # fechar_ticket (do node) + tools do pack responder_mensagens
    assert any("fechar_ticket" in n for n in tool_names)
    assert any("enviar_mensagem_direta" in n for n in tool_names)


def test_build_tool_definitions_backwards_compat_no_agent():
    """Chamadas legadas sem param agent continuam funcionando."""
    from tools import build_tool_definitions
    nodes = [{"type": "tool", "config": {"mcp_id": "clickmassa", "tool_name": "fechar_ticket"}}]
    defs = build_tool_definitions(nodes)  # sem agent kwarg
    assert len(defs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK_BLOCKED_TOOLS — checa cobertura
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_blocks_history_search_tools():
    from agents import WEBHOOK_BLOCKED_TOOLS
    assert "buscar_mensagens_ticket" in WEBHOOK_BLOCKED_TOOLS
    assert "clickmassa__buscar_mensagens_ticket" in WEBHOOK_BLOCKED_TOOLS

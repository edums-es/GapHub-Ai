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


def test_webhook_blocks_ticket_listing_tools():
    """Tools que fazem o agente ver OUTROS tickets devem estar bloqueadas."""
    from agents import WEBHOOK_BLOCKED_TOOLS
    for t in [
        "listar_tickets_abertos", "listar_tickets_pendentes", "listar_tickets",
        "buscar_tickets", "buscar_ticket_por_id",
        "buscar_contato_por_numero", "buscar_contato_por_id", "listar_contatos",
    ]:
        assert t in WEBHOOK_BLOCKED_TOOLS, f"{t} deveria estar bloqueada em webhook"
        assert f"clickmassa__{t}" in WEBHOOK_BLOCKED_TOOLS, f"clickmassa__{t} deveria estar bloqueada"


# ─────────────────────────────────────────────────────────────────────────────
# _enforce_ticket_scope — rejeita envio para ticket/número errado
# ─────────────────────────────────────────────────────────────────────────────

def test_enforce_ticket_scope_accepts_matching_ticket():
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "enviar_mensagem_direta",
        {"ticket_id": "66378", "numero": "5511988887777", "mensagem": "oi"},
        allowed_ticket_id="66378", allowed_numero="5511988887777",
    )
    assert err is None
    assert params["ticket_id"] == "66378"
    assert fn == "enviar_mensagem_direta"  # não reescreve — número está presente


def test_enforce_ticket_scope_rejects_mismatched_ticket():
    from agents import _enforce_ticket_scope
    _, _, err = _enforce_ticket_scope(
        "enviar_mensagem_direta",
        {"ticket_id": "99999", "numero": "5511988887777", "mensagem": "oi"},
        allowed_ticket_id="66378", allowed_numero="",
    )
    assert err is not None
    assert err.get("blocked") is True
    assert err.get("scope_violation") is True


def test_enforce_ticket_scope_rejects_mismatched_numero():
    from agents import _enforce_ticket_scope
    _, _, err = _enforce_ticket_scope(
        "enviar_mensagem",
        {"numero": "5511000000000", "mensagem": "oi"},
        allowed_ticket_id="", allowed_numero="5511988887777",
    )
    assert err is not None
    assert err.get("blocked") is True


def test_enforce_ticket_scope_injects_missing_ticket_id():
    """Se o LLM esquecer o ticket_id, o scope lock injeta o correto."""
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "enviar_nota_interna",
        {"mensagem": "oi"},  # sem ticket_id
        allowed_ticket_id="66378", allowed_numero="",
    )
    assert err is None
    assert params["ticket_id"] == "66378"
    assert fn == "enviar_nota_interna"


def test_enforce_ticket_scope_injects_missing_numero():
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "enviar_mensagem",
        {"mensagem": "oi"},  # sem numero
        allowed_ticket_id="", allowed_numero="5511988887777",
    )
    assert err is None
    assert params["numero"] == "5511988887777"
    assert fn == "enviar_mensagem"


def test_enforce_ticket_scope_passes_through_non_scoped_tools():
    """Tools que não são de envio passam inalteradas."""
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "buscar_mensagens_ticket",
        {"ticket_id": "99999"},
        allowed_ticket_id="66378", allowed_numero="",
    )
    assert err is None
    assert params["ticket_id"] == "99999"  # não alterado
    assert fn == "buscar_mensagens_ticket"


def test_enforce_ticket_scope_mcp_namespaced():
    """Prefixo clickmassa__ deve ser reconhecido."""
    from agents import _enforce_ticket_scope
    _, _, err = _enforce_ticket_scope(
        "clickmassa__enviar_mensagem_direta",
        {"ticket_id": "99999", "numero": "5511988887777"},
        allowed_ticket_id="66378", allowed_numero="",
    )
    assert err is not None
    assert err.get("scope_violation") is True


def test_enforce_ticket_scope_rewrites_enviar_mensagem_direta_without_numero():
    """
    REGRESSION: O ClickMassa respondeu "Olá! Tudo bem?..." mas não chegou no
    WhatsApp do lead porque o LLM chamou enviar_mensagem_direta com numero="".
    Agora o scope lock converte essa chamada para enviar_mensagem (usa ticket_id),
    garantindo que a mensagem chegue no WhatsApp.
    """
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "enviar_mensagem_direta",
        {"numero": "", "ticket_id": "66397", "mensagem": "Olá"},
        allowed_ticket_id="66397", allowed_numero="",
    )
    assert err is None
    assert fn == "enviar_mensagem", f"esperado reescrita para enviar_mensagem, veio '{fn}'"
    assert params["ticket_id"] == "66397"
    assert "numero" not in params  # número vazio foi removido
    assert params["mensagem"] == "Olá"


def test_enforce_ticket_scope_rewrites_mcp_namespaced_direta():
    """Idem acima, com prefixo clickmassa__."""
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "clickmassa__enviar_mensagem_direta",
        {"numero": "", "ticket_id": "66397", "mensagem": "Olá"},
        allowed_ticket_id="66397", allowed_numero="",
    )
    assert err is None
    assert fn == "clickmassa__enviar_mensagem"
    assert params["ticket_id"] == "66397"


def test_enforce_ticket_scope_keeps_direta_when_numero_valid():
    """Se o número é válido e bate com allowed_numero, não reescreve."""
    from agents import _enforce_ticket_scope
    fn, params, err = _enforce_ticket_scope(
        "enviar_mensagem_direta",
        {"numero": "5511988887777", "mensagem": "oi"},
        allowed_ticket_id="66397", allowed_numero="5511988887777",
    )
    assert err is None
    assert fn == "enviar_mensagem_direta"
    assert params["numero"] == "5511988887777"


# ─────────────────────────────────────────────────────────────────────────────
# MANDATORY_CRM_RULES_WEBHOOK — versão enxuta, consistente com tools permitidas
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_rules_do_not_mention_blocked_tools():
    """O prompt de webhook NÃO pode mandar chamar tools bloqueadas."""
    from agents import MANDATORY_CRM_RULES_WEBHOOK, WEBHOOK_BLOCKED_TOOLS
    for tool in ("buscar_mensagens_ticket", "listar_tickets_pendentes", "listar_tickets_abertos"):
        assert tool in WEBHOOK_BLOCKED_TOOLS  # sanity
        assert tool not in MANDATORY_CRM_RULES_WEBHOOK, (
            f"O prompt de webhook menciona '{tool}' que está bloqueada — contradição"
        )


def test_webhook_rules_emphasize_scope():
    """O prompt de webhook precisa deixar explícito que o ticket_id é imutável."""
    from agents import MANDATORY_CRM_RULES_WEBHOOK
    txt = MANDATORY_CRM_RULES_WEBHOOK.lower()
    assert "escopo" in txt or "único" in txt
    assert "ticket_id" in txt


# ─────────────────────────────────────────────────────────────────────────────
# _extract_webhook_fields — normalização entre formatos de CRM
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_webhook_fields_clickmassa_real_payload():
    """
    REGRESSION: o ClickMassa aninha ticketId/contactId dentro de payload["message"].
    Antes da correção, o extrator só olhava em payload.ticketId (root) e em
    ticket_obj.id — ambos None no payload real — resultando em ticket_id=''
    e o agente recusando silenciosamente a responder.

    Payload abaixo é cópia fiel do log de produção (Railway, 2026-04-18).
    """
    from agents import _extract_webhook_fields

    payload = {
        "message": {
            "mediaName": None,
            "mediaUrl": "",
            "msgCreatedAt": "2026-04-18T20:08:57.776Z",
            "id": "c94dafc1-3ea3-45b4-ada2-c3543ca2989e",
            "ack": 0,
            "wabaMediaId": None,
            "isDownload": True,
            "userId": None,
            "body": "Oi",
            "fromMe": False,
            "tenantId": 27,
            "ticketId": 66397,          # ← aninhado em message
            "contactId": 71890,         # ← aninhado em message
            "read": False,
            "messageId": "AC3F7F2C706C5F5AC232110FDF93A31B",
            "mediaType": "text",
            "status": "received",
            "tenantUid": "4f803c5f-c501-4b0e-8348-5933e9d9b671",
            "isDeleted": False,
        },
        "tenantId": 27,
        "sessionId": "some-session",
        "event": "message.new",
    }

    fields = _extract_webhook_fields(payload)

    assert fields["user_input"] == "Oi"
    assert fields["ticket_id"] == "66397", (
        f"ticket_id deveria ser '66397' mas veio '{fields['ticket_id']}'"
    )
    assert fields["contact_id"] == "71890"
    assert fields["from_me"] is False
    assert fields["is_private"] is False
    assert fields["msg_id"] == "c94dafc1-3ea3-45b4-ada2-c3543ca2989e"


def test_extract_webhook_fields_clickmassa_from_me():
    """Mensagem enviada pela empresa (fromMe=True) deve ser identificada."""
    from agents import _extract_webhook_fields

    payload = {
        "message": {
            "body": "Vai querer oq?",
            "fromMe": True,
            "ticketId": 66541,
            "contactId": 72051,
        },
    }
    fields = _extract_webhook_fields(payload)
    assert fields["from_me"] is True
    assert fields["ticket_id"] == "66541"


def test_extract_webhook_fields_chatwoot_style():
    """Formato Chatwoot: dados em payload['data'] com conversation/sender."""
    from agents import _extract_webhook_fields

    payload = {
        "event": "message_created",
        "data": {
            "content": "Olá, tudo bem?",
            "message_type": "incoming",
            "id": "msg-123",
            "conversation": {"id": 555, "status": "open"},
            "sender": {"name": "João", "phone_number": "+5511999999999"},
        },
    }
    fields = _extract_webhook_fields(payload)
    assert fields["user_input"] == "Olá, tudo bem?"
    assert fields["ticket_id"] == "555"
    assert fields["contact_number"] == "+5511999999999"
    assert fields["contact_name"] == "João"
    assert fields["from_me"] is False


def test_extract_webhook_fields_chatwoot_outgoing_is_from_me():
    """Chatwoot message_type=outgoing deve marcar from_me=True."""
    from agents import _extract_webhook_fields

    payload = {
        "data": {
            "content": "Resposta do bot",
            "message_type": "outgoing",
            "conversation": {"id": 555},
        },
    }
    fields = _extract_webhook_fields(payload)
    assert fields["from_me"] is True


def test_extract_webhook_fields_empty_payload():
    """Payload vazio não deve crashar; retorna campos vazios."""
    from agents import _extract_webhook_fields

    fields = _extract_webhook_fields({})
    assert fields["user_input"] == ""
    assert fields["ticket_id"] == ""
    assert fields["contact_id"] == ""
    assert fields["from_me"] is False


def test_extract_webhook_fields_none_string_coerced_to_empty():
    """ticketId='None' ou 'null' ou '0' devem ser tratados como vazio."""
    from agents import _extract_webhook_fields

    for bad in ("None", "null", "0", 0):
        payload = {"message": {"body": "x", "ticketId": bad}}
        fields = _extract_webhook_fields(payload)
        assert fields["ticket_id"] == "", f"ticketId={bad!r} deveria virar '' mas ficou {fields['ticket_id']!r}"


def test_extract_webhook_fields_notification_is_private():
    """messageType=notification deve marcar is_private=True."""
    from agents import _extract_webhook_fields

    payload = {"message": {"body": "status update"}, "messageType": "notification"}
    fields = _extract_webhook_fields(payload)
    assert fields["is_private"] is True


def test_extract_webhook_fields_clickmassa_nested_ticket():
    """
    REGRESSION: O ClickMassa aninha o TICKET COMPLETO (com contact.number,
    status, etc.) dentro de payload.message.ticket. Sem esse path, o número
    do lead nunca é extraído e a mensagem vai pro limbo.

    Payload abaixo é recorte fiel do log de produção 2026-04-18 20:25.
    """
    from agents import _extract_webhook_fields

    payload = {
        "message": {
            "body": "Oi",
            "fromMe": False,
            "ticketId": 66397,
            "contactId": 71890,
            "id": "4899563a-2acb-491c-b0b6-30708dbb36e1",
            "ticket": {
                "id": 66397,
                "status": "pending",
                "userId": None,
                "contactId": 71890,
                "contact": {
                    "id": 71890,
                    "name": "Yago Rodrigues",
                    "number": "553196827334",
                    "channel": "whatsapp",
                },
                "user": None,
            },
        },
        "tenantId": 27,
        "event": "NewMessage",
    }

    fields = _extract_webhook_fields(payload)

    assert fields["user_input"] == "Oi"
    assert fields["ticket_id"] == "66397"
    assert fields["contact_number"] == "553196827334", (
        f"contact_number deveria vir de ticket.contact.number, veio '{fields['contact_number']}'"
    )
    assert fields["contact_name"] == "Yago Rodrigues"
    assert fields["contact_id"] == "71890"
    assert fields["ticket_status"] == "pending"
    assert fields["from_me"] is False

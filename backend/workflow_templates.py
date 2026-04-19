"""
backend/workflow_templates.py — Workflows prontos que o usuário pode instalar
com 1 clique. Linguagem em português e nomes que o operador de CRM entende.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ═════════════════════════════════════════════════════════════════════════
# Template 1 — Atendimento WhatsApp (clássico)
# Quando o lead manda uma mensagem, o workflow:
#   1. Classifica a intenção (agendar / passar dado / falar com humano / dúvida / saudação)
#   2. Roteia para o ramo certo
#   3. Executa a ação da rotina (criar_tarefa, atualizar_contato, devolver_para_fila)
#   4. Gera uma resposta natural com LLM
#   5. Envia a resposta via Push API (aparece como empresa)
# ═════════════════════════════════════════════════════════════════════════

TEMPLATE_ATENDIMENTO_WHATSAPP: Dict[str, Any] = {
    "template_id": "atendimento_whatsapp",
    "name": "Atendimento WhatsApp inteligente",
    "description": (
        "Ideal para pré-venda e suporte inicial. Classifica o que o lead quer, "
        "executa a ação no CRM (agendar, atualizar contato, transferir para humano) "
        "e responde de forma natural."
    ),
    "trigger_type": "webhook",
    "nodes": [
        {
            "id": "start",
            "type": "trigger",
            "label": "Mensagem recebida do lead",
            "position": {"x": 40, "y": 40},
            "config": {"source": "webhook"},
            "next": "classify",
        },
        {
            "id": "classify",
            "type": "classify_intent",
            "label": "Entender o que o lead quer",
            "position": {"x": 40, "y": 180},
            "config": {
                "output": "intent",
                "intents": [
                    {"id": "agendar", "description": "Lead quer marcar call, reunião, visita ou demonstração"},
                    {"id": "dado_contato", "description": "Lead está passando email, telefone, nome da empresa, CNPJ ou outro dado de cadastro"},
                    {"id": "humano", "description": "Lead pede para falar com humano, gerente, atendente, vendedor ou diz que não está conseguindo resolver"},
                    {"id": "saudacao", "description": "Lead só cumprimentou (oi, bom dia, tudo bem, olá) sem pedir nada específico"},
                    {"id": "duvida", "description": "Lead está perguntando algo sobre produto, preço, prazo, cobertura, política, ou pedindo informação"},
                    {"id": "outro", "description": "Qualquer outra coisa que não encaixa nas categorias acima"},
                ],
            },
            "next": "route",
        },
        {
            "id": "route",
            "type": "branch",
            "label": "Rotear por intenção",
            "position": {"x": 40, "y": 320},
            "config": {
                "on": "intent",
                "cases": [
                    {"when": "agendar", "to": "agendar_tarefa"},
                    {"when": "dado_contato", "to": "atualizar_contato"},
                    {"when": "humano", "to": "transferir_humano"},
                    {"when": "saudacao", "to": "responder_saudacao"},
                    {"when": "duvida", "to": "responder_duvida"},
                ],
                "default": "responder_duvida",
            },
        },
        # ─── Ramo: agendar ──────────────────────────────────────────────
        {
            "id": "agendar_tarefa",
            "type": "tool_call",
            "label": "Criar tarefa no CRM",
            "position": {"x": 360, "y": 120},
            "config": {
                "mcp_id": "clickmassa",
                "tool_name": "criar_tarefa",
                "params": {
                    "tipo": "C",
                    "titulo": "Call solicitada por {{contact_name}}",
                    "contato_id": "{{contact_id}}",
                },
                "save_as": "tarefa_criada",
            },
            "next": "mensagem_agendar",
        },
        {
            "id": "mensagem_agendar",
            "type": "llm_reply",
            "label": "Redigir confirmação do agendamento",
            "position": {"x": 360, "y": 260},
            "config": {
                "system": (
                    "Você é um atendente brasileiro cordial. O lead acabou de pedir "
                    "para agendar uma call/reunião. A tarefa já foi criada no CRM. "
                    "Redija uma resposta curta (máximo 2 frases), confirmando o pedido "
                    "e avisando que um atendente humano vai entrar em contato para "
                    "acertar o horário. Não invente data/hora."
                ),
                "user": "Mensagem do lead: {{input}}",
                "output": "reply",
                "temperature": 0.3,
            },
            "next": "enviar_agendar",
        },
        {
            "id": "enviar_agendar",
            "type": "send_message",
            "label": "Enviar resposta ao lead",
            "position": {"x": 360, "y": 400},
            "config": {"message": "{{reply}}"},
            "next": "fim_agendar",
        },
        {"id": "fim_agendar", "type": "end", "label": "Fim", "position": {"x": 360, "y": 520}, "config": {}},
        # ─── Ramo: atualizar contato ────────────────────────────────────
        {
            "id": "atualizar_contato",
            "type": "llm_reply",
            "label": "Extrair dado do contato",
            "position": {"x": 680, "y": 120},
            "config": {
                "system": (
                    "O lead enviou um dado de contato (email, telefone, nome, empresa, CNPJ). "
                    "Responda APENAS em JSON: {\"campo\": \"email|telefone|nome|empresa|cnpj|outro\", \"valor\": \"<valor>\"}. "
                    "Se o texto não contiver um dado claro, retorne campo=\"outro\" e valor=\"\"."
                ),
                "user": "Texto do lead: {{input}}",
                "output": "dado_extraido",
                "temperature": 0,
            },
            "next": "confirmar_dado",
        },
        {
            "id": "confirmar_dado",
            "type": "llm_reply",
            "label": "Confirmar recebimento do dado",
            "position": {"x": 680, "y": 260},
            "config": {
                "system": (
                    "Confirme para o lead que o dado foi recebido e anotado. Máximo 1 frase. "
                    "Seja natural e não repita o dado inteiro."
                ),
                "user": "O lead mandou: {{input}}",
                "output": "reply",
                "temperature": 0.3,
            },
            "next": "enviar_dado",
        },
        {
            "id": "enviar_dado",
            "type": "send_message",
            "label": "Enviar confirmação",
            "position": {"x": 680, "y": 400},
            "config": {"message": "{{reply}}"},
            "next": "fim_dado",
        },
        {"id": "fim_dado", "type": "end", "label": "Fim", "position": {"x": 680, "y": 520}, "config": {}},
        # ─── Ramo: transferir humano ────────────────────────────────────
        {
            "id": "transferir_humano",
            "type": "tool_call",
            "label": "Devolver para a fila de humanos",
            "position": {"x": 1000, "y": 120},
            "config": {
                "mcp_id": "clickmassa",
                "tool_name": "devolver_para_fila",
                "params": {"ticket_id": "{{ticket_id}}"},
                "save_as": "transferencia",
            },
            "next": "mensagem_transferido",
        },
        {
            "id": "mensagem_transferido",
            "type": "send_message",
            "label": "Avisar lead",
            "position": {"x": 1000, "y": 260},
            "config": {"message": "Entendi! Já passei sua conversa para um atendente humano. Em instantes ele vai te responder por aqui."},
            "next": "fim_transferir",
        },
        {"id": "fim_transferir", "type": "end", "label": "Fim", "position": {"x": 1000, "y": 400}, "config": {}},
        # ─── Ramo: saudação ─────────────────────────────────────────────
        {
            "id": "responder_saudacao",
            "type": "llm_reply",
            "label": "Redigir saudação + pergunta aberta",
            "position": {"x": 1320, "y": 120},
            "config": {
                "system": (
                    "Você é um atendente brasileiro, cordial, objetivo. O lead só cumprimentou. "
                    "Responda com uma saudação curta + pergunta aberta do tipo "
                    "\"em que posso ajudar?\". Máximo 2 frases."
                ),
                "user": "{{input}}",
                "output": "reply",
                "temperature": 0.4,
            },
            "next": "enviar_saudacao",
        },
        {
            "id": "enviar_saudacao",
            "type": "send_message",
            "label": "Enviar saudação",
            "position": {"x": 1320, "y": 260},
            "config": {"message": "{{reply}}"},
            "next": "fim_saudacao",
        },
        {"id": "fim_saudacao", "type": "end", "label": "Fim", "position": {"x": 1320, "y": 400}, "config": {}},
        # ─── Ramo: dúvida / info ────────────────────────────────────────
        {
            "id": "responder_duvida",
            "type": "llm_reply",
            "label": "Responder dúvida",
            "position": {"x": 1640, "y": 120},
            "config": {
                "system": (
                    "Você é um atendente brasileiro. O lead fez uma pergunta. "
                    "Responda de forma objetiva e cordial. "
                    "NUNCA invente preço, prazo, condição ou política — se não souber, "
                    "diga que vai consultar e já transfira para um atendente humano. "
                    "Máximo 3 frases."
                ),
                "user": "Pergunta do lead: {{input}}",
                "output": "reply",
                "temperature": 0.3,
            },
            "next": "enviar_duvida",
        },
        {
            "id": "enviar_duvida",
            "type": "send_message",
            "label": "Enviar resposta",
            "position": {"x": 1640, "y": 260},
            "config": {"message": "{{reply}}"},
            "next": "fim_duvida",
        },
        {"id": "fim_duvida", "type": "end", "label": "Fim", "position": {"x": 1640, "y": 400}, "config": {}},
    ],
}


# ═════════════════════════════════════════════════════════════════════════
# Template 2 — Qualificação de lead
# ═════════════════════════════════════════════════════════════════════════

TEMPLATE_QUALIFICACAO: Dict[str, Any] = {
    "template_id": "qualificacao_lead",
    "name": "Qualificação automática de lead",
    "description": (
        "Faz 3 perguntas simples pro lead, registra as respostas em notas internas "
        "e encaminha para o vendedor certo. Ideal pra reduzir lead frio no pipeline."
    ),
    "trigger_type": "webhook",
    "nodes": [
        {"id": "start", "type": "trigger", "label": "Mensagem do lead", "position": {"x": 40, "y": 40}, "config": {}, "next": "extract"},
        {
            "id": "extract",
            "type": "llm_reply",
            "label": "Extrair dados de qualificação",
            "position": {"x": 40, "y": 180},
            "config": {
                "system": (
                    "Extraia do texto do lead: (a) cargo/função, (b) porte/tamanho da empresa, "
                    "(c) urgência (alta/media/baixa). Retorne APENAS JSON: "
                    "{\"cargo\": \"\", \"porte\": \"\", \"urgencia\": \"\"}. Se faltar algum, deixe string vazia."
                ),
                "user": "{{input}}",
                "output": "dados_qual",
                "temperature": 0,
            },
            "next": "registrar",
        },
        {
            "id": "registrar",
            "type": "tool_call",
            "label": "Registrar em nota interna",
            "position": {"x": 40, "y": 320},
            "config": {
                "mcp_id": "clickmassa",
                "tool_name": "enviar_nota_interna",
                "params": {"ticket_id": "{{ticket_id}}", "nota": "Qualificação automática: {{dados_qual}}"},
            },
            "next": "responder",
        },
        {
            "id": "responder",
            "type": "llm_reply",
            "label": "Próxima pergunta de qualificação",
            "position": {"x": 40, "y": 460},
            "config": {
                "system": (
                    "Você está qualificando um lead. Faça a próxima pergunta que falta entre: "
                    "cargo, porte da empresa, urgência. Se já tem os 3, agradeça e diga que "
                    "um especialista vai entrar em contato. Máximo 2 frases."
                ),
                "user": "Dados já coletados: {{dados_qual}}. Lead escreveu: {{input}}",
                "output": "reply",
                "temperature": 0.3,
            },
            "next": "enviar",
        },
        {"id": "enviar", "type": "send_message", "label": "Enviar", "position": {"x": 40, "y": 600}, "config": {"message": "{{reply}}"}, "next": "fim"},
        {"id": "fim", "type": "end", "label": "Fim", "position": {"x": 40, "y": 740}, "config": {}},
    ],
}


# ═════════════════════════════════════════════════════════════════════════
# Template 3 — FAQ simples com fallback humano
# ═════════════════════════════════════════════════════════════════════════

TEMPLATE_FAQ: Dict[str, Any] = {
    "template_id": "faq_simples",
    "name": "FAQ com transferência humana",
    "description": (
        "Responde perguntas frequentes com base em uma base de conhecimento (no prompt). "
        "Se não souber, transfere automaticamente para humano. Ideal para WhatsApp de suporte."
    ),
    "trigger_type": "webhook",
    "nodes": [
        {"id": "start", "type": "trigger", "label": "Mensagem", "position": {"x": 40, "y": 40}, "config": {}, "next": "classify"},
        {
            "id": "classify",
            "type": "classify_intent",
            "label": "Categorizar pergunta",
            "position": {"x": 40, "y": 180},
            "config": {
                "output": "intent",
                "intents": [
                    {"id": "faq_conhecido", "description": "Pergunta está coberta na FAQ (horário, endereço, preço publicado, como funciona)"},
                    {"id": "nao_sei", "description": "Pergunta especifica demais, caso particular, negociação, ou qualquer coisa fora da FAQ"},
                ],
            },
            "next": "route",
        },
        {
            "id": "route",
            "type": "branch",
            "label": "Rotear",
            "position": {"x": 40, "y": 320},
            "config": {
                "on": "intent",
                "cases": [
                    {"when": "faq_conhecido", "to": "responder_faq"},
                    {"when": "nao_sei", "to": "transferir"},
                ],
                "default": "transferir",
            },
        },
        {
            "id": "responder_faq",
            "type": "llm_reply",
            "label": "Responder com base na FAQ",
            "position": {"x": 360, "y": 120},
            "config": {
                "system": (
                    "Você é um atendente. Responda com base na FAQ abaixo. "
                    "Se não tiver certeza, diga \"vou consultar um especialista\".\n\n"
                    "FAQ (edite isso no Builder):\n"
                    "- Horário: seg-sex 9h às 18h\n"
                    "- Prazo de entrega: 3 a 5 dias úteis\n"
                    "- Formas de pagamento: pix, cartão, boleto\n"
                ),
                "user": "{{input}}",
                "output": "reply",
                "temperature": 0.2,
            },
            "next": "enviar_faq",
        },
        {"id": "enviar_faq", "type": "send_message", "label": "Enviar", "position": {"x": 360, "y": 260}, "config": {"message": "{{reply}}"}, "next": "fim_faq"},
        {"id": "fim_faq", "type": "end", "label": "Fim", "position": {"x": 360, "y": 400}, "config": {}},
        {
            "id": "transferir",
            "type": "tool_call",
            "label": "Transferir para humano",
            "position": {"x": 680, "y": 120},
            "config": {
                "mcp_id": "clickmassa",
                "tool_name": "devolver_para_fila",
                "params": {"ticket_id": "{{ticket_id}}"},
            },
            "next": "aviso_transferencia",
        },
        {
            "id": "aviso_transferencia",
            "type": "send_message",
            "label": "Avisar lead",
            "position": {"x": 680, "y": 260},
            "config": {"message": "Vou passar sua pergunta para um atendente humano. Em instantes ele te responde aqui!"},
            "next": "fim_transfer",
        },
        {"id": "fim_transfer", "type": "end", "label": "Fim", "position": {"x": 680, "y": 400}, "config": {}},
    ],
}


WORKFLOW_TEMPLATES: List[Dict[str, Any]] = [
    TEMPLATE_ATENDIMENTO_WHATSAPP,
    TEMPLATE_QUALIFICACAO,
    TEMPLATE_FAQ,
]


def get_template(template_id: str) -> Dict[str, Any]:
    """Retorna um template pelo id ou {} se não existir."""
    for t in WORKFLOW_TEMPLATES:
        if t.get("template_id") == template_id:
            return t
    return {}

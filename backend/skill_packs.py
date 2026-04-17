"""
skill_packs.py — Catálogo de "skill packs" (nós condicionados) do GapHub.

Um Skill Pack é um conjunto curado de tools do MCP + um fragmento de system
prompt + uma categoria de negócio. O cliente escolhe quais packs o agente
tem habilitado; isso determina EXATAMENTE quais tools o LLM enxerga e que
comportamento ele adota.

Motivação: o MCP ClickMassa expõe ~24 tools. Jogar todas na cara do LLM
piora tremendamente a qualidade das decisões ("paradoxo da escolha" em tools).
Agrupar em 6-8 packs funcionais melhora precisão e dá ao cliente um modelo
mental claro ("meu agente faz Qualificação + Follow-up, não faz Venda").

Formato de cada pack:
  id:           identificador estável (slug)
  name:         nome humano
  description:  o que o agente passa a fazer ao habilitar este pack
  category:     classificação para filtros na UI
  icon/color:   dicas visuais para o frontend
  mcp_id:       MCP ao qual as tools pertencem (atualmente "clickmassa")
  tools:        lista de nomes de tools (sem prefixo mcp_id__)
  prompt:       fragmento de instrução injetado no system prompt quando ativo
  recommended:  true para os packs que sugerimos por padrão

Novos packs podem ser adicionados aqui sem tocar em banco. Para overrides por
workspace (ex: um cliente quer um pack customizado), use a coleção
`skill_packs_override` no MongoDB (futuro — não bloqueia o MVP).
"""

from typing import List, Dict, Set


SKILL_PACKS: List[Dict] = [
    # ── PACK 1: Responder Mensagens (núcleo do atendimento) ─────────────────
    {
        "id": "responder_mensagens",
        "name": "Responder Mensagens",
        "description": (
            "O agente lê o que o lead acabou de dizer e responde de forma "
            "cordial, clara e breve. Não toma iniciativa de campanhas — só "
            "reage ao que chega."
        ),
        "category": "communication",
        "icon": "message-square",
        "color": "#10B981",
        "mcp_id": "clickmassa",
        "tools": [
            "enviar_mensagem_direta",
            "enviar_mensagem",
            "enviar_nota_interna",
        ],
        "prompt": (
            "\n[SKILL: RESPONDER MENSAGENS]\n"
            "Seu papel principal é responder o lead com mensagens diretas, "
            "curtas e humanas. Uma resposta = uma mensagem. Nunca dispare "
            "duas mensagens seguidas sem o lead responder no meio.\n"
        ),
        "recommended": True,
    },

    # ── PACK 2: Qualificação de Leads ───────────────────────────────────────
    {
        "id": "qualificacao",
        "name": "Qualificação de Leads",
        "description": (
            "O agente faz perguntas de descoberta, registra objeções e move "
            "o lead pelas etapas do funil. Usa NOTA INTERNA para documentar "
            "o raciocínio; nunca expõe o scoring para o lead."
        ),
        "category": "sales",
        "icon": "target",
        "color": "#F59E0B",
        "mcp_id": "clickmassa",
        "tools": [
            "buscar_contato_por_numero",
            "buscar_contato_por_id",
            "atualizar_contato",
            "adicionar_etiquetas",
            "listar_status_lead",
            "listar_origens_lead",
            "enviar_nota_interna",
        ],
        "prompt": (
            "\n[SKILL: QUALIFICAÇÃO]\n"
            "Conduza a conversa buscando: (1) dor/necessidade, (2) autoridade "
            "de decisão, (3) urgência, (4) orçamento. Após cada resposta "
            "relevante do lead, use enviar_nota_interna para registrar o "
            "achado — invisível ao lead, visível ao time. Se confirmar "
            "qualificação forte, atualize etiquetas/status do contato.\n"
        ),
        "recommended": True,
    },

    # ── PACK 3: Follow-up & Nutrição ────────────────────────────────────────
    {
        "id": "followup",
        "name": "Follow-up & Nutrição",
        "description": (
            "O agente programa lembretes, atribui o contato a funis de "
            "follow-up e escalona quando percebe fadiga da cadência. Respeita "
            "horário comercial e não faz spam."
        ),
        "category": "sales",
        "icon": "repeat",
        "color": "#3B82F6",
        "mcp_id": "clickmassa",
        "tools": [
            "listar_funis",
            "atribuir_funil_contato",
            "criar_tarefa",
            "listar_tarefas",
            "listar_tickets_abertos",
            "devolver_para_fila",
        ],
        "prompt": (
            "\n[SKILL: FOLLOW-UP]\n"
            "Quando o lead pedir 'me manda depois', 'semana que vem', etc., "
            "agende tarefa/ativador de funil em vez de prometer lembrete "
            "manualmente. Se o lead parar de responder por mais de 2 "
            "tentativas seguidas, devolva para a fila humana — não insista.\n"
        ),
        "recommended": True,
    },

    # ── PACK 4: Agendamento & Operação de Fila ──────────────────────────────
    {
        "id": "agendamento",
        "name": "Agendamento & Fila",
        "description": (
            "O agente cria compromissos, distribui tickets entre atendentes "
            "e devolve para fila quando necessário. Não toma decisão "
            "comercial; só organiza operação."
        ),
        "category": "operations",
        "icon": "calendar",
        "color": "#8B5CF6",
        "mcp_id": "clickmassa",
        "tools": [
            "criar_tarefa",
            "listar_tarefas",
            "listar_tickets_pendentes",
            "listar_tickets_abertos",
            "devolver_para_fila",
            "fechar_ticket",
            "atribuir_fluxo_chat",
        ],
        "prompt": (
            "\n[SKILL: AGENDAMENTO]\n"
            "Você pode criar tarefas/compromissos e roteá-los entre fila "
            "pendente e atendentes específicos. Sempre informe no chat quem "
            "ficou responsável e quando a ação vai acontecer.\n"
        ),
        "recommended": False,
    },

    # ── PACK 5: Transferência / Handoff ─────────────────────────────────────
    {
        "id": "handoff",
        "name": "Transferência Humana",
        "description": (
            "O agente reconhece quando a conversa passou do seu escopo (preço "
            "travado, reclamação séria, negociação avançada) e entrega o "
            "ticket para um humano com um resumo de contexto na nota interna."
        ),
        "category": "operations",
        "icon": "user-check",
        "color": "#EF4444",
        "mcp_id": "clickmassa",
        "tools": [
            "enviar_nota_interna",
            "devolver_para_fila",
            "fechar_ticket",
        ],
        "prompt": (
            "\n[SKILL: HANDOFF]\n"
            "Antes de devolver_para_fila, SEMPRE deixe uma nota interna com: "
            "(1) o resumo da conversa até aqui, (2) o motivo do handoff, "
            "(3) o próximo passo sugerido. Avise o lead que um humano assume.\n"
        ),
        "recommended": True,
    },

    # ── PACK 6: Consulta & Enriquecimento ───────────────────────────────────
    {
        "id": "consulta",
        "name": "Consulta & Enriquecimento",
        "description": (
            "Leitura e busca apenas. Bom para o agente consultar dados do CRM "
            "e pesquisar informações externas sem risco de escrita. Perfil "
            "conservador."
        ),
        "category": "data",
        "icon": "search",
        "color": "#06B6D4",
        "mcp_id": "clickmassa",
        "tools": [
            "buscar_contato_por_numero",
            "buscar_contato_por_id",
            "listar_contatos",
            "listar_tickets_abertos",
            "listar_tickets_pendentes",
            "buscar_mensagens_ticket",
            "listar_conexoes_whatsapp",
            "listar_fluxos_chat",
        ],
        "prompt": (
            "\n[SKILL: CONSULTA]\n"
            "Você tem acesso APENAS a operações de leitura do CRM. Não "
            "modifique dados; se precisar, peça para o time humano.\n"
        ),
        "recommended": False,
    },

    # ── PACK 7: Integrações (web + HTTP) ────────────────────────────────────
    {
        "id": "integracoes",
        "name": "Integrações Externas",
        "description": (
            "Permite o agente pesquisar na web e chamar APIs externas para "
            "enriquecer respostas (ex: consultar CEP, validar CNPJ, buscar "
            "informações públicas)."
        ),
        "category": "developer",
        "icon": "globe",
        "color": "#6366F1",
        "mcp_id": "web_search",  # primário
        "tools": ["buscar_web"],
        "extra_mcps": [
            {"mcp_id": "http_request", "tools": ["http_get", "http_post"]},
        ],
        "prompt": (
            "\n[SKILL: INTEGRAÇÕES]\n"
            "Você pode pesquisar na web (buscar_web) e fazer chamadas HTTP "
            "(http_get/http_post) para enriquecer a conversa. Use com "
            "parcimônia — não faça mais de 2 buscas por turno.\n"
        ),
        "recommended": False,
    },
]


def get_pack(pack_id: str) -> Dict:
    """Retorna o dict de um pack pelo id, ou None."""
    return next((p for p in SKILL_PACKS if p["id"] == pack_id), None)


def expand_packs_to_tool_refs(pack_ids: List[str]) -> List[Dict]:
    """
    Converte uma lista de pack_ids em referências (mcp_id, tool_name) que o
    build_tool_definitions consegue consumir. Deduplica automaticamente.

    Retorna: [{"mcp_id": "clickmassa", "tool_name": "enviar_mensagem"}, ...]
    """
    seen: Set[tuple] = set()
    refs: List[Dict] = []
    for pid in pack_ids or []:
        pack = get_pack(pid)
        if not pack:
            continue
        for tool_name in pack.get("tools", []):
            key = (pack["mcp_id"], tool_name)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"mcp_id": pack["mcp_id"], "tool_name": tool_name})
        for extra in pack.get("extra_mcps", []):
            for tool_name in extra.get("tools", []):
                key = (extra["mcp_id"], tool_name)
                if key in seen:
                    continue
                seen.add(key)
                refs.append({"mcp_id": extra["mcp_id"], "tool_name": tool_name})
    return refs


def compose_packs_prompt(pack_ids: List[str]) -> str:
    """Concatena os prompt fragments dos packs ativos, na ordem do catálogo."""
    if not pack_ids:
        return ""
    fragments = []
    ordered_ids = [p["id"] for p in SKILL_PACKS if p["id"] in set(pack_ids)]
    for pid in ordered_ids:
        pack = get_pack(pid)
        if pack and pack.get("prompt"):
            fragments.append(pack["prompt"])
    return "\n".join(fragments)


def list_packs_public() -> List[Dict]:
    """View pública — sem o prompt interno, só metadata para o frontend."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["category"],
            "icon": p["icon"],
            "color": p["color"],
            "mcp_id": p["mcp_id"],
            "tools": p["tools"],
            "recommended": p.get("recommended", False),
        }
        for p in SKILL_PACKS
    ]

import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Save, Play, Plus, Trash2, ArrowLeft, Settings, X, ChevronDown, SendHorizontal, Bot, Zap, Database, Globe, Search, Layers } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";
import SkillPackSelector from "@/components/SkillPackSelector";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const NODE_WIDTH = 180;
const NODE_HEIGHT = 80;

const NODE_COLORS = {
  trigger: { bg: "rgba(249,115,22,0.15)", border: "#F97316", icon: "#F97316", label: "Trigger" },
  llm:     { bg: "rgba(59,130,246,0.15)",  border: "#3B82F6", icon: "#3B82F6", label: "LLM Core" },
  tool:    { bg: "rgba(16,185,129,0.15)",  border: "#10B981", icon: "#10B981", label: "MCP Tool" },
  output:  { bg: "rgba(115,115,115,0.15)", border: "#737373", icon: "#737373", label: "Output" },
};

const LLM_PROVIDERS = [
  { value: "openai",    label: "OpenAI",    models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"] },
  { value: "anthropic", label: "Anthropic", models: ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"] },
  { value: "gemini",    label: "Gemini",    models: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"] },
];

const AVAILABLE_MCPS = [
  { id: "clickmassa", label: "ClickMassa CRM", color: "#F97316", icon: Database, tools: ["buscar_contato_por_numero","criar_contato","enviar_mensagem","listar_tickets_pendentes","fechar_ticket","atualizar_contato"] },
  { id: "web_search", label: "Busca na Web",   color: "#3B82F6", icon: Search, tools: ["buscar_web"] },
  { id: "http_request", label: "HTTP Request", color: "#8B5CF6", icon: Globe, tools: ["http_get","http_post"] },
];

const AGENT_TEMPLATES = [
  {
    id: "respondedor_leads",
    name: "Respondedor de Leads",
    description: "Responde automaticamente a novos leads recebidos no CRM, verifica duplicatas e envia boas-vindas personalizadas.",
    emoji: "👥",
    category: "CRM",
    nodes: [
      { node_id: "trigger_1",        type: "trigger", position: { x: 140, y: 240 }, config: { label: "Novo Lead" } },
      { node_id: "llm_core",         type: "llm",     position: { x: 420, y: 240 }, config: { label: "Agente de Leads" } },
      { node_id: "output_1",         type: "output",  position: { x: 700, y: 240 }, config: { label: "Resultado" } },
      { node_id: "tool_clickmassa_1",type: "tool",    position: { x: 420, y: 390 }, config: { mcp_id: "clickmassa", tool_name: "*", label: "ClickMassa CRM" } },
    ],
    edges: [
      { id: "e1", source: "trigger_1",        target: "llm_core" },
      { id: "e2", source: "llm_core",         target: "output_1" },
      { id: "e3", source: "tool_clickmassa_1", target: "llm_core" },
    ],
    llm_config: {
      provider: "openai", model: "gpt-4o-mini", api_key: "",
      system_prompt: "Você é um especialista em atendimento de leads. Ao receber informações sobre um novo lead: 1) Verifique se já existe no CRM pelo número ou e-mail, 2) Se não existir, crie o contato, 3) Envie uma mensagem de boas-vindas personalizada e profissional. Responda sempre em português brasileiro.",
      temperature: 0.7, max_tokens: 4096,
    },
  },
  {
    id: "gestor_tickets",
    name: "Gestor de Tickets Pendentes",
    description: "Lista e prioriza tickets pendentes no CRM, gerando um relatório de ações recomendadas.",
    emoji: "🎫",
    category: "Suporte",
    nodes: [
      { node_id: "trigger_1",        type: "trigger", position: { x: 140, y: 240 }, config: { label: "Iniciar Gestão" } },
      { node_id: "llm_core",         type: "llm",     position: { x: 420, y: 240 }, config: { label: "Gestor de Suporte" } },
      { node_id: "output_1",         type: "output",  position: { x: 700, y: 240 }, config: { label: "Relatório" } },
      { node_id: "tool_clickmassa_1",type: "tool",    position: { x: 420, y: 390 }, config: { mcp_id: "clickmassa", tool_name: "listar_tickets_pendentes", label: "Tickets Pendentes" } },
    ],
    edges: [
      { id: "e1", source: "trigger_1",        target: "llm_core" },
      { id: "e2", source: "llm_core",         target: "output_1" },
      { id: "e3", source: "tool_clickmassa_1", target: "llm_core" },
    ],
    llm_config: {
      provider: "openai", model: "gpt-4o-mini", api_key: "",
      system_prompt: "Você é um gestor de suporte ao cliente. Quando acionado: 1) Liste todos os tickets pendentes, 2) Priorize por urgência (data de criação e tipo), 3) Sugira as próximas ações para cada ticket, 4) Feche tickets resolvidos se solicitado. Seja conciso e objetivo. Responda em português brasileiro.",
      temperature: 0.3, max_tokens: 4096,
    },
  },
  {
    id: "followup_automatico",
    name: "Follow-up Automático",
    description: "Realiza follow-up automático com clientes que não responderam, enviando mensagens personalizadas.",
    emoji: "📩",
    category: "Vendas",
    nodes: [
      { node_id: "trigger_1",        type: "trigger", position: { x: 140, y: 240 }, config: { label: "Iniciar Follow-up" } },
      { node_id: "llm_core",         type: "llm",     position: { x: 420, y: 240 }, config: { label: "Agente de Vendas" } },
      { node_id: "output_1",         type: "output",  position: { x: 700, y: 240 }, config: { label: "Relatório" } },
      { node_id: "tool_clickmassa_1",type: "tool",    position: { x: 300, y: 390 }, config: { mcp_id: "clickmassa", tool_name: "*", label: "ClickMassa CRM" } },
      { node_id: "tool_web_1",       type: "tool",    position: { x: 540, y: 390 }, config: { mcp_id: "web_search", tool_name: "buscar_web", label: "Busca na Web" } },
    ],
    edges: [
      { id: "e1", source: "trigger_1",        target: "llm_core" },
      { id: "e2", source: "llm_core",         target: "output_1" },
      { id: "e3", source: "tool_clickmassa_1", target: "llm_core" },
      { id: "e4", source: "tool_web_1",        target: "llm_core" },
    ],
    llm_config: {
      provider: "openai", model: "gpt-4o-mini", api_key: "",
      system_prompt: "Você é um especialista em vendas responsável por follow-up. Quando acionado: 1) Busque contatos que precisam de acompanhamento, 2) Crie mensagens personalizadas para cada contato, 3) Envie as mensagens via CRM. Seja persuasivo mas não invasivo. Responda em português brasileiro.",
      temperature: 0.8, max_tokens: 4096,
    },
  },
];

function NodeComponent({ node, selected, onSelect, onDragStart, onDelete }) {
  const colors = NODE_COLORS[node.type] || NODE_COLORS.tool;
  const Icon = node.type === "llm" ? Bot : node.type === "trigger" ? Zap : node.type === "tool" ? Database : Play;
  return (
    <div
      data-testid={`node-${node.node_id}`}
      onMouseDown={(e) => { e.stopPropagation(); onDragStart(e, node.node_id); onSelect(node); }}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute",
        left: node.position.x - NODE_WIDTH / 2,
        top: node.position.y - NODE_HEIGHT / 2,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        background: colors.bg,
        border: `2px solid ${selected ? colors.border : "rgba(255,255,255,0.1)"}`,
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "0 14px",
        cursor: "grab",
        userSelect: "none",
        transition: "border-color 0.15s, box-shadow 0.15s",
        boxShadow: selected ? `0 0 16px ${colors.border}40` : "none",
        zIndex: selected ? 10 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Icon size={16} color={colors.icon} />
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: colors.icon, textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "Outfit, sans-serif" }}>{colors.label}</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "white", marginTop: 1, fontFamily: "IBM Plex Sans, sans-serif" }}>{node.config?.label || node.node_id}</div>
        </div>
      </div>
      {node.type === "tool" && node.config?.mcp_id && (
        <div style={{ fontSize: 10, color: "#A3A3A3", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{node.config.mcp_id}</div>
      )}
      {node.type !== "trigger" && node.type !== "output" && (
        <button
          onMouseDown={e => e.stopPropagation()}
          onClick={e => { e.stopPropagation(); onDelete(node.node_id); }}
          style={{ position: "absolute", top: 4, right: 4, width: 18, height: 18, background: "rgba(239,68,68,0.2)", border: "none", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", opacity: 0.7 }}
          onMouseEnter={e => e.currentTarget.style.opacity = "1"}
          onMouseLeave={e => e.currentTarget.style.opacity = "0.7"}
        >
          <X size={10} color="#EF4444" />
        </button>
      )}
      {/* Output handle */}
      <div style={{ position: "absolute", right: -6, top: "50%", transform: "translateY(-50%)", width: 12, height: 12, background: colors.border, borderRadius: "50%", border: "2px solid #0A0A0A" }} />
      {/* Input handle */}
      {node.type !== "trigger" && (
        <div style={{ position: "absolute", left: -6, top: "50%", transform: "translateY(-50%)", width: 12, height: 12, background: colors.border, borderRadius: "50%", border: "2px solid #0A0A0A" }} />
      )}
    </div>
  );
}

function EdgeSVG({ nodes, edges }) {
  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", overflow: "visible" }}>
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#F97316" opacity="0.8" />
        </marker>
      </defs>
      {edges.map(edge => {
        const src = nodes.find(n => n.node_id === edge.source);
        const tgt = nodes.find(n => n.node_id === edge.target);
        if (!src || !tgt) return null;
        const x1 = src.position.x + NODE_WIDTH / 2 - 6;
        const y1 = src.position.y;
        const x2 = tgt.position.x - NODE_WIDTH / 2 + 6;
        const y2 = tgt.position.y;
        const cx = (x1 + x2) / 2;
        return (
          <path key={edge.id}
            d={`M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`}
            stroke="#F97316" strokeWidth="2" fill="none" opacity="0.7"
            markerEnd="url(#arrow)"
          />
        );
      })}
    </svg>
  );
}

function TemplatesModal({ onApply, onClose }) {
  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 250, padding: 20 }}
      onClick={onClose}
    >
      <div
        style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, width: "100%", maxWidth: 680, maxHeight: "80vh", display: "flex", flexDirection: "column", animation: "fadeIn 0.2s ease-out" }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ padding: "18px 22px", borderBottom: "1px solid #27272A", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 18, fontWeight: 700, color: "white", margin: 0 }}>Templates de Agentes</h3>
            <p style={{ fontSize: 12, color: "#737373", margin: "4px 0 0" }}>Comece mais rápido com um template pré-configurado</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer" }}><X size={18} /></button>
        </div>
        <div style={{ padding: 20, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 14, overflow: "auto" }}>
          {AGENT_TEMPLATES.map(tpl => (
            <div
              key={tpl.id}
              onClick={() => onApply(tpl)}
              style={{ background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 12, padding: 16, cursor: "pointer", transition: "all 0.2s", display: "flex", flexDirection: "column", gap: 8 }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.background = "#333"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.background = "#2A2A2A"; }}
            >
              <div style={{ fontSize: 28 }}>{tpl.emoji}</div>
              <div>
                <div style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, color: "white", fontSize: 14, marginBottom: 4 }}>{tpl.name}</div>
                <div style={{ fontSize: 11, color: "#A3A3A3", lineHeight: 1.5 }}>{tpl.description}</div>
              </div>
              <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 10, color: "#F97316", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }}>{tpl.category}</span>
                <span style={{ fontSize: 10, color: "#737373" }}>{tpl.nodes.length} nós</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConfigPanel({ node, agent, onUpdate, onClose }) {
  const [config, setConfig] = useState({ ...node.config });
  const [llm, setLlm] = useState({ ...agent.llm_config });

  const handleSave = () => {
    onUpdate(node.node_id, config, node.type === "llm" ? llm : null);
  };

  const curProvider = LLM_PROVIDERS.find(p => p.value === llm.provider) || LLM_PROVIDERS[0];

  return (
    <div style={{ width: 300, background: "#1A1A1A", borderLeft: "1px solid #27272A", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "16px 18px", borderBottom: "1px solid #27272A", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>
          {NODE_COLORS[node.type]?.label || "Nó"}: {node.config?.label}
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer" }}><X size={16} /></button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Common: label */}
        <div>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>Label</label>
          <input
            value={config.label || ""}
            onChange={e => setConfig(c => ({ ...c, label: e.target.value }))}
            style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
            onFocus={e => e.target.style.borderColor = "#F97316"}
            onBlur={e => e.target.style.borderColor = "#27272A"}
          />
        </div>

        {/* LLM node config */}
        {node.type === "llm" && (
          <>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>Provider</label>
              <select
                data-testid="llm-provider-select"
                value={llm.provider || "openai"}
                onChange={e => setLlm(l => ({ ...l, provider: e.target.value, model: LLM_PROVIDERS.find(p => p.value === e.target.value)?.models[0] || "" }))}
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none" }}
              >
                {LLM_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>Modelo</label>
              <select
                data-testid="llm-model-select"
                value={llm.model || ""}
                onChange={e => setLlm(l => ({ ...l, model: e.target.value }))}
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none" }}
              >
                {curProvider.models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>API Key</label>
              <input
                data-testid="llm-api-key"
                type="password"
                placeholder="sk-... (deixe vazio para usar chave padrão)"
                value={llm.api_key || ""}
                onChange={e => setLlm(l => ({ ...l, api_key: e.target.value }))}
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>System Prompt</label>
              <textarea
                data-testid="llm-system-prompt"
                value={llm.system_prompt || ""}
                onChange={e => setLlm(l => ({ ...l, system_prompt: e.target.value }))}
                rows={4}
                placeholder="Você é um assistente especialista em CRM..."
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", resize: "vertical", boxSizing: "border-box", lineHeight: 1.5 }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                Temperature: {llm.temperature || 0.7}
              </label>
              <input
                type="range" min="0" max="2" step="0.1"
                value={llm.temperature || 0.7}
                onChange={e => setLlm(l => ({ ...l, temperature: parseFloat(e.target.value) }))}
                style={{ width: "100%", accentColor: "#F97316" }}
              />
            </div>
          </>
        )}

        {/* Tool node config */}
        {node.type === "tool" && (
          <>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>MCP / Ferramenta</label>
              <select
                data-testid="tool-mcp-select"
                value={config.mcp_id || "clickmassa"}
                onChange={e => setConfig(c => ({ ...c, mcp_id: e.target.value, tool_name: "*" }))}
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none" }}
              >
                {AVAILABLE_MCPS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" }}>Tool específica (ou todas)</label>
              <select
                data-testid="tool-name-select"
                value={config.tool_name || "*"}
                onChange={e => setConfig(c => ({ ...c, tool_name: e.target.value }))}
                style={{ width: "100%", padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none" }}
              >
                <option value="*">Todas as ferramentas</option>
                {(AVAILABLE_MCPS.find(m => m.id === (config.mcp_id || "clickmassa"))?.tools || []).map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </>
        )}

        <button
          onClick={handleSave}
          data-testid="save-node-btn"
          style={{ marginTop: "auto", padding: "10px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
        >
          <Save size={13} /> Aplicar
        </button>
      </div>
    </div>
  );
}

function RunModal({ agent, onClose }) {
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleRun = async () => {
    if (!input.trim()) return;
    setRunning(true);
    setResult(null);
    setError("");
    try {
      const { data } = await axios.post(`${API}/agents/${agent.agent_id}/run`, { input }, { withCredentials: true });
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro na execução");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 300, padding: 20 }} onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, width: "100%", maxWidth: 600, maxHeight: "85vh", display: "flex", flexDirection: "column", animation: "fadeIn 0.2s ease-out" }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: "18px 22px", borderBottom: "1px solid #27272A", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 18, fontWeight: 700, color: "white", margin: 0 }}>Executar: {agent.name}</h3>
            <p style={{ fontSize: 12, color: "#737373", margin: "4px 0 0" }}>Envie um comando para o agente processar</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer" }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "18px 22px" }}>
          {result && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ background: "#2A2A2A", borderRadius: 10, padding: 16, marginBottom: 10 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#A3A3A3", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
                  Resultado
                </div>
                <div style={{ fontSize: 14, color: "white", lineHeight: 1.6, fontFamily: "IBM Plex Sans, sans-serif", whiteSpace: "pre-wrap" }}>
                  {result.output}
                </div>
              </div>
              {result.steps?.length > 0 && (
                <div style={{ background: "rgba(249,115,22,0.05)", border: "1px solid rgba(249,115,22,0.15)", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#F97316", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                    {result.steps.length} ferramenta{result.steps.length !== 1 ? "s" : ""} utilizada{result.steps.length !== 1 ? "s" : ""}
                  </div>
                  {result.steps.map((s, i) => (
                    <div key={i} style={{ fontSize: 12, color: "#A3A3A3", padding: "3px 0", fontFamily: "JetBrains Mono, monospace" }}>
                      {i + 1}. {s.tool}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {error && (
            <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8, padding: "12px 14px", marginBottom: 14, color: "#EF4444", fontSize: 13 }}>
              {error}
            </div>
          )}
        </div>

        <div style={{ padding: "14px 22px", borderTop: "1px solid #27272A", display: "flex", gap: 10 }}>
          <textarea
            data-testid="agent-run-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleRun(); } }}
            placeholder="Digite o comando para o agente... (Ex: Listar tickets pendentes)"
            rows={2}
            style={{ flex: 1, padding: "10px 14px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", resize: "none", lineHeight: 1.5 }}
            onFocus={e => e.target.style.borderColor = "#F97316"}
            onBlur={e => e.target.style.borderColor = "#27272A"}
          />
          <button
            onClick={handleRun}
            data-testid="agent-run-submit-btn"
            disabled={running || !input.trim()}
            style={{ padding: "10px 16px", background: running ? "#404040" : "#F97316", color: "white", border: "none", borderRadius: 8, cursor: running ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 6, fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, transition: "all 0.2s", boxShadow: running ? "none" : "0 0 12px rgba(249,115,22,0.3)" }}
          >
            {running ? (
              <div style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
            ) : (
              <SendHorizontal size={16} />
            )}
            {running ? "Processando..." : "Executar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Bug Fix #5 — Validação do agente antes de salvar
function validateAgent(agentName, nodes, llmConfig) {
  const errors = [];
  if (!agentName.trim()) errors.push("O agente precisa de um nome.");
  const hasTrigger = nodes.some(n => n.type === "trigger");
  const hasLLM = nodes.some(n => n.type === "llm");
  const hasOutput = nodes.some(n => n.type === "output");
  if (!hasTrigger) errors.push("É necessário pelo menos um nó Trigger.");
  if (!hasLLM) errors.push("É necessário pelo menos um nó LLM.");
  if (!hasOutput) errors.push("É necessário pelo menos um nó Output.");
  if (!llmConfig.api_key?.trim()) errors.push("Configure a API Key do LLM no painel de configuração.");
  return errors;
}

export default function AgentBuilder() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const isNew = !agentId;
  const canvasRef = useRef(null);

  const [agent, setAgent] = useState(null);
  const [agentName, setAgentName] = useState("Meu Agente");
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [llmConfig, setLlmConfig] = useState({ provider: "openai", model: "gpt-4o-mini", api_key: "", system_prompt: "Você é um assistente especialista em CRM. Responda sempre em português brasileiro.", temperature: 0.7, max_tokens: 4096 });
  const [selectedNode, setSelectedNode] = useState(null);
  const [draggingId, setDraggingId] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showRunModal, setShowRunModal] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [validationErrors, setValidationErrors] = useState([]);
  // Webhook state
  const [webhookInfo, setWebhookInfo] = useState(null);
  const [webhookSecret, setWebhookSecret] = useState(null); // exibido apenas após geração
  const [generatingWebhook, setGeneratingWebhook] = useState(false);
  // Per-agent MCP credentials state
  const [mcpCredsInfo, setMcpCredsInfo] = useState(null); // {configured, apiUrl, userToken, wabaId}
  const [showMcpCredsForm, setShowMcpCredsForm] = useState(false);
  const [mcpCredsForm, setMcpCredsForm] = useState({ apiUrl: "", userToken: "", wabaId: "" });
  const [savingMcpCreds, setSavingMcpCreds] = useState(false);
  // Skill packs habilitados no agente (nós condicionados)
  const [enabledSkillPacks, setEnabledSkillPacks] = useState([]);

  // Bug Fix #5 — Zoom/Pan: controles de zoom e pan no canvas via CSS transform
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef(null);

  const ZOOM_MIN = 0.3;
  const ZOOM_MAX = 2.0;

  const handleZoomIn = () => setZoom(z => Math.min(ZOOM_MAX, Math.round((z + 0.1) * 10) / 10));
  const handleZoomOut = () => setZoom(z => Math.max(ZOOM_MIN, Math.round((z - 0.1) * 10) / 10));
  const handleZoomReset = () => { setZoom(1.0); setPan({ x: 0, y: 0 }); };

  // Wheel zoom no canvas
  const handleWheel = useCallback((e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoom(z => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round((z + delta) * 10) / 10)));
  }, [ZOOM_MAX, ZOOM_MIN]);

  // Middle-click pan
  const handleCanvasMouseDown = useCallback((e) => {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      e.preventDefault();
      setIsPanning(true);
      panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    }
  }, [pan]);

  const handleCanvasMouseMove = useCallback((e) => {
    if (isPanning && panStartRef.current) {
      setPan({ x: e.clientX - panStartRef.current.x, y: e.clientY - panStartRef.current.y });
    }
  }, [isPanning]);

  const handleCanvasMouseUp = useCallback((e) => {
    if (e.button === 1 || isPanning) setIsPanning(false);
  }, [isPanning]);

  useEffect(() => {
    if (!isNew) {
      axios.get(`${API}/agents/${agentId}`, { withCredentials: true })
        .then(r => {
          const a = r.data;
          setAgent(a);
          setAgentName(a.name);
          setNodes(a.nodes || []);
          setEdges(a.edges || []);
          setLlmConfig(a.llm_config || {});
          setEnabledSkillPacks(a.enabled_skill_packs || []);
        })
        .finally(() => setLoading(false));
      // Carrega info de webhook (sem exibir o secret)
      axios.get(`${API}/agents/${agentId}/webhook-info`, { withCredentials: true })
        .then(r => setWebhookInfo(r.data))
        .catch(() => {});
      // Carrega credenciais MCP por agente (campos sensíveis mascarados)
      axios.get(`${API}/agents/${agentId}/mcp-credentials`, { withCredentials: true })
        .then(r => { setMcpCredsInfo(r.data); if (r.data.configured) setMcpCredsForm({ apiUrl: r.data.apiUrl || "", userToken: "", wabaId: r.data.wabaId || "" }); })
        .catch(() => {});
    } else {
      const defaultNodes = [
        { node_id: "trigger_1", type: "trigger", position: { x: 140, y: 240 }, config: { label: "Iniciar" } },
        { node_id: "llm_core",  type: "llm",     position: { x: 420, y: 240 }, config: { label: "Agente IA" } },
        { node_id: "output_1",  type: "output",  position: { x: 700, y: 240 }, config: { label: "Resultado" } },
      ];
      const defaultEdges = [
        { id: "e1", source: "trigger_1", target: "llm_core" },
        { id: "e2", source: "llm_core",  target: "output_1" },
      ];
      setNodes(defaultNodes);
      setEdges(defaultEdges);
      setLoading(false);
    }
  }, [agentId, isNew]);

  const handleDragStart = useCallback((e, nodeId) => {
    if (isPanning) return;
    const node = nodes.find(n => n.node_id === nodeId);
    if (!node) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDraggingId(nodeId);
    // Ajusta offset pelo zoom e pan do canvas
    setDragOffset({
      x: (e.clientX - rect.left - pan.x) / zoom - node.position.x,
      y: (e.clientY - rect.top  - pan.y) / zoom - node.position.y,
    });
  }, [nodes, zoom, pan, isPanning]);

  const handleMouseMove = useCallback((e) => {
    if (isPanning && panStartRef.current) {
      setPan({ x: e.clientX - panStartRef.current.x, y: e.clientY - panStartRef.current.y });
      return;
    }
    if (!draggingId) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    // Converte posição do mouse para coordenadas do canvas (considerando zoom e pan)
    const x = (e.clientX - rect.left - pan.x) / zoom - dragOffset.x;
    const y = (e.clientY - rect.top  - pan.y) / zoom - dragOffset.y;
    setNodes(ns => ns.map(n => n.node_id === draggingId ? { ...n, position: { x: Math.max(NODE_WIDTH / 2, x), y: Math.max(NODE_HEIGHT / 2, y) } } : n));
  }, [draggingId, dragOffset, zoom, pan, isPanning]);

  const handleMouseUp = useCallback((e) => {
    setDraggingId(null);
    setIsPanning(false);
  }, []);

  const applyTemplate = useCallback((template) => {
    setNodes(template.nodes);
    setEdges(template.edges);
    setLlmConfig(template.llm_config);
    setAgentName(template.name);
    setSelectedNode(null);
    setShowTemplates(false);
  }, []);

  const addToolNode = (mcp) => {
    const nodeId = `tool_${mcp.id}_${Date.now()}`;
    const toolCount = nodes.filter(n => n.type === "tool").length;
    const llmNode = nodes.find(n => n.type === "llm");
    const x = llmNode ? llmNode.position.x : 420;
    const y = 380 + toolCount * 110;
    const newNode = { node_id: nodeId, type: "tool", position: { x, y }, config: { mcp_id: mcp.id, tool_name: "*", label: mcp.label } };
    setNodes(ns => [...ns, newNode]);
    const newEdge = { id: `e_tool_${Date.now()}`, source: nodeId, target: "llm_core" };
    setEdges(es => [...es, newEdge]);
  };

  const deleteNode = (nodeId) => {
    setNodes(ns => ns.filter(n => n.node_id !== nodeId));
    setEdges(es => es.filter(e => e.source !== nodeId && e.target !== nodeId));
    if (selectedNode?.node_id === nodeId) setSelectedNode(null);
  };

  const updateNode = (nodeId, config, newLlm) => {
    setNodes(ns => ns.map(n => n.node_id === nodeId ? { ...n, config: { ...n.config, ...config } } : n));
    if (newLlm) setLlmConfig(newLlm);
    if (selectedNode?.node_id === nodeId) setSelectedNode(n => ({ ...n, config: { ...n.config, ...config } }));
  };

  const handleSave = async () => {
    // Bug Fix #5 — Valida nós obrigatórios antes de salvar
    const errors = validateAgent(agentName, nodes, llmConfig);
    if (errors.length > 0) {
      setValidationErrors(errors);
      setTimeout(() => setValidationErrors([]), 5000);
      return;
    }
    setValidationErrors([]);
    setSaving(true);
    try {
      const payload = { name: agentName, nodes, edges, llm_config: llmConfig, enabled_skill_packs: enabledSkillPacks };
      if (isNew) {
        const { data } = await axios.post(`${API}/agents`, payload, { withCredentials: true });
        setAgent(data);
        navigate(`/agents/${data.agent_id}`, { replace: true });
      } else {
        const { data } = await axios.put(`${API}/agents/${agentId}`, payload, { withCredentials: true });
        setAgent(data);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
          <div style={{ width: 36, height: 36, border: "3px solid #F97316", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)", animation: "fadeIn 0.3s ease-out" }}>
        {/* Top bar */}
        {/* Erros de validação — Bug Fix #5 */}
        {validationErrors.length > 0 && (
          <div style={{ marginBottom: 8, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#EF4444", marginBottom: 2 }}>Corrija antes de salvar:</div>
            {validationErrors.map((err, i) => (
              <div key={i} style={{ fontSize: 12, color: "#F87171" }}>• {err}</div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
          <button onClick={() => navigate("/agents")} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 13 }}>
            <ArrowLeft size={16} /> Voltar
          </button>
          <input
            data-testid="agent-name-input"
            value={agentName}
            onChange={e => setAgentName(e.target.value)}
            style={{ flex: 1, minWidth: 200, padding: "8px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 15, fontFamily: "Outfit, sans-serif", fontWeight: 700, outline: "none" }}
            onFocus={e => e.target.style.borderColor = "#F97316"}
            onBlur={e => e.target.style.borderColor = "#27272A"}
          />
          <div style={{ display: "flex", gap: 8 }}>
            {agent && (
              <button
                onClick={() => setShowRunModal(true)}
                data-testid="run-agent-btn"
                style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 18px", background: "rgba(16,185,129,0.1)", color: "#10B981", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13, transition: "all 0.2s" }}
                onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.2)"}
                onMouseLeave={e => e.currentTarget.style.background = "rgba(16,185,129,0.1)"}
              >
                <Play size={14} /> Executar
              </button>
            )}
            <button
              onClick={handleSave}
              data-testid="save-agent-btn"
              disabled={saving}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 18px", background: saved ? "#10B981" : "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13, boxShadow: "0 0 10px rgba(249,115,22,0.3)", transition: "all 0.2s" }}
            >
              <Save size={14} /> {saved ? "Salvo!" : saving ? "Salvando..." : "Salvar"}
            </button>
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", gap: 0, minHeight: 0, background: "#0A0A0A", borderRadius: 12, border: "1px solid #27272A", overflow: "hidden" }}>
          {/* Left palette */}
          <div style={{ width: 180, background: "#1A1A1A", borderRight: "1px solid #27272A", display: "flex", flexDirection: "column", flexShrink: 0 }}>
            <div style={{ padding: "12px 14px", borderBottom: "1px solid #27272A" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em" }}>Adicionar Tool</div>
            </div>
            <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              {AVAILABLE_MCPS.map(mcp => {
                const Icon = mcp.icon;
                return (
                  <button
                    key={mcp.id}
                    onClick={() => addToolNode(mcp)}
                    data-testid={`add-tool-${mcp.id}`}
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, cursor: "pointer", color: "white", fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.2s", textAlign: "left" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = `${mcp.color}60`; e.currentTarget.style.background = "#333"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.background = "#2A2A2A"; }}
                  >
                    <div style={{ width: 24, height: 24, background: `${mcp.color}20`, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <Icon size={13} color={mcp.color} />
                    </div>
                    <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{mcp.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Templates button */}
            <div style={{ padding: "8px 8px 0", borderTop: "1px solid #27272A", marginTop: 6 }}>
              <button
                onClick={() => setShowTemplates(true)}
                style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", background: "rgba(249,115,22,0.08)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, cursor: "pointer", color: "#F97316", fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.2s" }}
                onMouseEnter={e => { e.currentTarget.style.background = "rgba(249,115,22,0.15)"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "rgba(249,115,22,0.08)"; }}
              >
                <Layers size={13} />
                <span style={{ fontWeight: 600 }}>Templates</span>
              </button>
            </div>

            {/* Skill Packs — nós condicionados (braços funcionais do agente) */}
            <div style={{ overflowY: "auto", maxHeight: 320 }}>
              <SkillPackSelector
                agentId={agent?.agent_id}
                initialEnabled={enabledSkillPacks}
                onChange={setEnabledSkillPacks}
                disabled={!agent}
              />
            </div>

            {/* Webhook section — apenas para agentes já salvos */}
            {agent && (
              <div style={{ padding: "8px 8px 0", borderTop: "1px solid #27272A", marginTop: 6 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em", padding: "0 2px 6px" }}>Webhook</div>
                {webhookSecret ? (
                  // Secret acabou de ser gerado — mostrar e alertar para copiar
                  <div style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.25)", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ fontSize: 10, color: "#10B981", marginBottom: 4, fontWeight: 600 }}>✅ Secret gerado — copie agora!</div>
                    <div style={{ fontSize: 9, fontFamily: "monospace", color: "#A3A3A3", wordBreak: "break-all", background: "#0A0A0A", padding: "4px 6px", borderRadius: 4, marginBottom: 6 }}>
                      {webhookSecret}
                    </div>
                    <div style={{ fontSize: 9, color: "#737373", marginBottom: 2 }}>URL do Webhook:</div>
                    <div style={{ fontSize: 9, fontFamily: "monospace", color: "#A3A3A3", wordBreak: "break-all", background: "#0A0A0A", padding: "4px 6px", borderRadius: 4, marginBottom: 6 }}>
                      {process.env.REACT_APP_BACKEND_URL}/api/webhook/{agent.agent_id}
                    </div>
                    <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                      <button
                        onClick={() => navigator.clipboard?.writeText(`${process.env.REACT_APP_BACKEND_URL}/api/webhook/${agent.agent_id}`)}
                        style={{ flex: 1, padding: "5px", background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.3)", borderRadius: 6, color: "#3B82F6", fontSize: 10, cursor: "pointer", fontWeight: 600 }}
                      >Copiar URL</button>
                      <button
                        onClick={() => { navigator.clipboard?.writeText(webhookSecret); setWebhookSecret(null); }}
                        style={{ flex: 1, padding: "5px", background: "rgba(16,185,129,0.15)", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 6, color: "#10B981", fontSize: 10, cursor: "pointer", fontWeight: 600 }}
                      >Copiar Secret e fechar</button>
                    </div>
                  </div>
                ) : webhookInfo?.has_webhook ? (
                  // Webhook já configurado
                  <div style={{ background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                      <div style={{ width: 6, height: 6, background: "#10B981", borderRadius: "50%" }} />
                      <span style={{ fontSize: 10, color: "#10B981", fontWeight: 600 }}>Webhook ativo</span>
                    </div>
                    <div style={{ fontSize: 9, fontFamily: "monospace", color: "#A3A3A3", wordBreak: "break-all", background: "#0A0A0A", padding: "4px 6px", borderRadius: 4, marginBottom: 6 }}>
                      {process.env.REACT_APP_BACKEND_URL}/api/webhook/{agent.agent_id}
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        onClick={() => navigator.clipboard?.writeText(`${process.env.REACT_APP_BACKEND_URL}/api/webhook/${agent.agent_id}`)}
                        style={{ flex: 1, padding: "5px", background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 6, color: "#3B82F6", fontSize: 10, cursor: "pointer", fontWeight: 600 }}
                      >Copiar URL</button>
                      <button
                        onClick={async () => {
                          setGeneratingWebhook(true);
                          try {
                            const { data } = await axios.post(`${API}/agents/${agent.agent_id}/webhook-secret`, {}, { withCredentials: true });
                            setWebhookSecret(data.webhook_secret);
                            setWebhookInfo(i => ({ ...i, has_webhook: true }));
                          } catch (e) { alert(e.response?.data?.detail || "Erro ao rotacionar"); }
                          setGeneratingWebhook(false);
                        }}
                        disabled={generatingWebhook}
                        style={{ flex: 1, padding: "5px", background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#737373", fontSize: 10, cursor: "pointer" }}
                      >{generatingWebhook ? "..." : "Rotacionar secret"}</button>
                    </div>
                  </div>
                ) : (
                  // Sem webhook ainda
                  <button
                    onClick={async () => {
                      setGeneratingWebhook(true);
                      try {
                        const { data } = await axios.post(`${API}/agents/${agent.agent_id}/webhook-secret`, {}, { withCredentials: true });
                        setWebhookSecret(data.webhook_secret);
                        setWebhookInfo({ has_webhook: true, webhook_url: data.webhook_url });
                      } catch (e) { alert(e.response?.data?.detail || "Erro ao gerar webhook"); }
                      setGeneratingWebhook(false);
                    }}
                    disabled={generatingWebhook}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: 6, padding: "8px 10px", background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 8, cursor: "pointer", color: "#3B82F6", fontSize: 11, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.2s" }}
                  >
                    <Zap size={12} />
                    <span style={{ fontWeight: 600 }}>{generatingWebhook ? "Gerando..." : "Gerar Webhook URL"}</span>
                  </button>
                )}
              </div>
            )}

            {/* Per-agent MCP credentials — apenas para agentes já salvos */}
            {agent && (
              <div style={{ padding: "8px 8px 0", borderTop: "1px solid #27272A", marginTop: 6 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 2px 6px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em" }}>Credenciais MCP</div>
                  {mcpCredsInfo?.configured && !showMcpCredsForm && (
                    <button onClick={() => setShowMcpCredsForm(true)} style={{ fontSize: 9, color: "#F97316", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", padding: 0 }}>editar</button>
                  )}
                </div>
                {showMcpCredsForm ? (
                  <div style={{ background: "#0A0A0A", border: "1px solid #27272A", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ fontSize: 9, color: "#737373", marginBottom: 6, lineHeight: 1.4 }}>
                      Credenciais específicas para este agente. Sobrepõe as credenciais do workspace.
                    </div>
                    {[
                      { key: "apiUrl", label: "API URL", placeholder: "https://seu-crm.clickmassa.com.br", type: "text" },
                      { key: "userToken", label: "User Token", placeholder: mcpCredsInfo?.configured ? "••••••• (deixe em branco para manter)" : "token_aqui", type: "password" },
                      { key: "wabaId", label: "WABA ID (opcional)", placeholder: "id do número WhatsApp", type: "text" },
                    ].map(({ key, label, placeholder, type }) => (
                      <div key={key} style={{ marginBottom: 6 }}>
                        <label style={{ display: "block", fontSize: 9, color: "#A3A3A3", marginBottom: 2, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</label>
                        <input
                          type={type}
                          value={mcpCredsForm[key] || ""}
                          onChange={e => setMcpCredsForm(f => ({ ...f, [key]: e.target.value }))}
                          placeholder={placeholder}
                          style={{ width: "100%", padding: "4px 6px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 5, color: "white", fontSize: 10, fontFamily: "IBM Plex Mono, monospace", outline: "none", boxSizing: "border-box" }}
                          onFocus={e => e.target.style.borderColor = "#F97316"}
                          onBlur={e => e.target.style.borderColor = "#27272A"}
                        />
                      </div>
                    ))}
                    <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
                      <button
                        onClick={async () => {
                          setSavingMcpCreds(true);
                          try {
                            await axios.put(`${API}/agents/${agent.agent_id}/mcp-credentials`, mcpCredsForm, { withCredentials: true });
                            const r = await axios.get(`${API}/agents/${agent.agent_id}/mcp-credentials`, { withCredentials: true });
                            setMcpCredsInfo(r.data);
                            setShowMcpCredsForm(false);
                          } catch (e) { alert(e.response?.data?.detail || "Erro ao salvar credenciais"); }
                          setSavingMcpCreds(false);
                        }}
                        disabled={savingMcpCreds || !mcpCredsForm.apiUrl}
                        style={{ flex: 1, padding: "5px", background: "rgba(249,115,22,0.15)", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 6, color: "#F97316", fontSize: 10, cursor: savingMcpCreds ? "wait" : "pointer", fontWeight: 600 }}
                      >{savingMcpCreds ? "Salvando..." : "Salvar"}</button>
                      <button
                        onClick={() => setShowMcpCredsForm(false)}
                        style={{ padding: "5px 8px", background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#737373", fontSize: 10, cursor: "pointer" }}
                      >Cancelar</button>
                    </div>
                    {mcpCredsInfo?.configured && (
                      <button
                        onClick={async () => {
                          if (!window.confirm("Remover credenciais MCP específicas deste agente?")) return;
                          try {
                            await axios.delete(`${API}/agents/${agent.agent_id}/mcp-credentials`, { withCredentials: true });
                            setMcpCredsInfo({ configured: false });
                            setMcpCredsForm({ apiUrl: "", userToken: "", wabaId: "" });
                            setShowMcpCredsForm(false);
                          } catch (e) { alert(e.response?.data?.detail || "Erro ao remover"); }
                        }}
                        style={{ width: "100%", marginTop: 4, padding: "4px", background: "transparent", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, color: "rgba(239,68,68,0.6)", fontSize: 9, cursor: "pointer" }}
                      >Remover credenciais</button>
                    )}
                  </div>
                ) : mcpCredsInfo?.configured ? (
                  <div style={{ background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                      <div style={{ width: 6, height: 6, background: "#10B981", borderRadius: "50%" }} />
                      <span style={{ fontSize: 10, color: "#10B981", fontWeight: 600 }}>Credenciais configuradas</span>
                    </div>
                    <div style={{ fontSize: 9, color: "#737373", wordBreak: "break-all", lineHeight: 1.4 }}>
                      {mcpCredsInfo.apiUrl || "URL não definida"}
                    </div>
                    {mcpCredsInfo.updated_at && (
                      <div style={{ fontSize: 9, color: "#404040", marginTop: 2 }}>
                        Atualizado: {new Date(mcpCredsInfo.updated_at).toLocaleDateString("pt-BR")}
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    onClick={() => setShowMcpCredsForm(true)}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: 6, padding: "8px 10px", background: "rgba(16,185,129,0.06)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 8, cursor: "pointer", color: "#10B981", fontSize: 11, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.2s" }}
                  >
                    <Database size={12} />
                    <span style={{ fontWeight: 600 }}>Configurar credenciais CRM</span>
                  </button>
                )}
              </div>
            )}

            <div style={{ padding: "10px 14px", borderTop: "1px solid #27272A", marginTop: "auto" }}>
              <div style={{ fontSize: 10, color: "#737373", lineHeight: 1.5 }}>
                Clique para adicionar.<br />Arraste para mover.
              </div>
            </div>
          </div>

          {/* Canvas — Bug Fix #5: zoom/pan com CSS transform */}
          <div
            ref={canvasRef}
            className="canvas-bg"
            style={{ flex: 1, position: "relative", overflow: "hidden", cursor: isPanning ? "grabbing" : draggingId ? "grabbing" : "default" }}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onMouseDown={handleCanvasMouseDown}
            onWheel={handleWheel}
            onClick={() => { if (!isPanning) setSelectedNode(null); }}
          >
            {/* Camada transformada pelo zoom/pan */}
            <div style={{
              position: "absolute",
              inset: 0,
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: "0 0",
            }}>
              <EdgeSVG nodes={nodes} edges={edges} />
              {nodes.map(node => (
                <NodeComponent
                  key={node.node_id}
                  node={node}
                  selected={selectedNode?.node_id === node.node_id}
                  onSelect={setSelectedNode}
                  onDragStart={handleDragStart}
                  onDelete={deleteNode}
                />
              ))}
            </div>

            {/* Controles de Zoom — posicionados fixo no canto do canvas */}
            <div style={{ position: "absolute", bottom: 14, right: 14, display: "flex", alignItems: "center", gap: 6, zIndex: 20 }}>
              <button
                onClick={handleZoomOut}
                title="Reduzir zoom (Ctrl + scroll)"
                style={{ width: 28, height: 28, background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", cursor: "pointer", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}
              >−</button>
              <button
                onClick={handleZoomReset}
                title="Resetar zoom e posição"
                style={{ padding: "4px 8px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", cursor: "pointer", fontSize: 11, fontFamily: "IBM Plex Mono, monospace" }}
              >{Math.round(zoom * 100)}%</button>
              <button
                onClick={handleZoomIn}
                title="Aumentar zoom (Ctrl + scroll)"
                style={{ width: 28, height: 28, background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", cursor: "pointer", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}
              >+</button>
              <span style={{ fontSize: 10, color: "#404040", marginLeft: 4 }}>Alt+drag para pan</span>
            </div>

            {/* Hint */}
            {nodes.length <= 3 && (
              <div style={{ position: "absolute", bottom: 50, left: "50%", transform: "translateX(-50%)", background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, padding: "6px 14px", fontSize: 12, color: "#F97316", pointerEvents: "none", whiteSpace: "nowrap" }}>
                Adicione ferramentas na barra esquerda e clique nos nós para configurar
              </div>
            )}
          </div>

          {/* Right config panel */}
          {selectedNode && (
            <ConfigPanel
              node={selectedNode}
              agent={{ llm_config: llmConfig }}
              onUpdate={updateNode}
              onClose={() => setSelectedNode(null)}
            />
          )}
        </div>
      </div>

      {showRunModal && agent && (
        <RunModal agent={agent} onClose={() => setShowRunModal(false)} />
      )}

      {showTemplates && (
        <TemplatesModal
          onApply={applyTemplate}
          onClose={() => setShowTemplates(false)}
        />
      )}
    </Layout>
  );
}

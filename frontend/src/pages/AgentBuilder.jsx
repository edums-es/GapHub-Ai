import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Save, Play, Plus, Trash2, ArrowLeft, Settings, X, ChevronDown, SendHorizontal, Bot, Zap, Database, Globe, Search } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";

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

function NodeComponent({ node, selected, onSelect, onDragStart, onDelete }) {
  const colors = NODE_COLORS[node.type] || NODE_COLORS.tool;
  const Icon = node.type === "llm" ? Bot : node.type === "trigger" ? Zap : node.type === "tool" ? Database : Play;
  return (
    <div
      data-testid={`node-${node.node_id}`}
      onMouseDown={(e) => { e.stopPropagation(); onDragStart(e, node.node_id); onSelect(node); }}
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
  const [loading, setLoading] = useState(!isNew);

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
        })
        .finally(() => setLoading(false));
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
    const node = nodes.find(n => n.node_id === nodeId);
    if (!node) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDraggingId(nodeId);
    setDragOffset({
      x: (e.clientX - rect.left) - node.position.x,
      y: (e.clientY - rect.top)  - node.position.y,
    });
  }, [nodes]);

  const handleMouseMove = useCallback((e) => {
    if (!draggingId) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left - dragOffset.x;
    const y = e.clientY - rect.top  - dragOffset.y;
    setNodes(ns => ns.map(n => n.node_id === draggingId ? { ...n, position: { x: Math.max(NODE_WIDTH / 2, x), y: Math.max(NODE_HEIGHT / 2, y) } } : n));
  }, [draggingId, dragOffset]);

  const handleMouseUp = useCallback(() => setDraggingId(null), []);

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
    setSaving(true);
    try {
      const payload = { name: agentName, nodes, edges, llm_config: llmConfig };
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

            <div style={{ padding: "10px 14px", borderTop: "1px solid #27272A", marginTop: "auto" }}>
              <div style={{ fontSize: 10, color: "#737373", lineHeight: 1.5 }}>
                Clique para adicionar.<br />Arraste para mover.
              </div>
            </div>
          </div>

          {/* Canvas */}
          <div
            ref={canvasRef}
            className="canvas-bg"
            style={{ flex: 1, position: "relative", overflow: "hidden", cursor: draggingId ? "grabbing" : "default" }}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onClick={() => setSelectedNode(null)}
          >
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

            {/* Hint */}
            {nodes.length <= 3 && (
              <div style={{ position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)", background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, padding: "6px 14px", fontSize: 12, color: "#F97316", pointerEvents: "none" }}>
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
    </Layout>
  );
}

// Play imported from lucide-react above

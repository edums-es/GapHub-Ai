import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Plus, Play, Edit3, Trash2, ToggleLeft, ToggleRight, Clock, CheckCircle } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function StatusBadge({ status }) {
  const map = { active: ["Ativo", "#10B981"], inactive: ["Inativo", "#737373"] };
  const [label, color] = map[status] || [status, "#737373"];
  return <span style={{ fontSize: 11, fontWeight: 600, color, background: `${color}15`, border: `1px solid ${color}30`, borderRadius: 100, padding: "3px 10px" }}>{label}</span>;
}

export default function MyAgents() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null);
  const navigate = useNavigate();

  const fetchAgents = () => {
    setLoading(true);
    axios.get(`${API}/agents`, { withCredentials: true })
      .then(r => setAgents(r.data.agents || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchAgents(); }, []);

  const toggleStatus = async (agent) => {
    const newStatus = agent.status === "active" ? "inactive" : "active";
    await axios.put(`${API}/agents/${agent.agent_id}`, { status: newStatus }, { withCredentials: true });
    fetchAgents();
  };

  const deleteAgent = async (agentId) => {
    if (!window.confirm("Excluir este agente? Esta ação não pode ser desfeita.")) return;
    setDeleting(agentId);
    try {
      await axios.delete(`${API}/agents/${agentId}`, { withCredentials: true });
      setAgents(a => a.filter(x => x.agent_id !== agentId));
    } finally {
      setDeleting(null);
    }
  };

  const relativeTime = (dt) => {
    if (!dt) return "—";
    const diff = Date.now() - new Date(dt).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "agora";
    if (m < 60) return `${m}m atrás`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h atrás`;
    return `${Math.floor(h / 24)}d atrás`;
  };

  const getLLMBadge = (provider) => {
    const map = { openai: ["OpenAI", "#10A37F"], anthropic: ["Anthropic", "#CF5542"], gemini: ["Gemini", "#4285F4"] };
    const [label, color] = map[provider] || [provider, "#737373"];
    return <span style={{ fontSize: 11, fontWeight: 600, color, background: `${color}15`, border: `1px solid ${color}30`, borderRadius: 4, padding: "2px 6px" }}>{label}</span>;
  };

  return (
    <Layout>
      <div style={{ animation: "fadeIn 0.3s ease-out" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
          <div>
            <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 28, color: "white", letterSpacing: "-0.03em", marginBottom: 4 }}>Meus Agentes</h1>
            <p style={{ fontSize: 14, color: "#737373" }}>{agents.length} agente{agents.length !== 1 ? "s" : ""} no workspace</p>
          </div>
          <button
            onClick={() => navigate("/agents/new")}
            data-testid="create-agent-btn"
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, cursor: "pointer", boxShadow: "0 0 12px rgba(249,115,22,0.3)", transition: "all 0.2s" }}
            onMouseEnter={e => e.currentTarget.style.transform = "translateY(-1px)"}
            onMouseLeave={e => e.currentTarget.style.transform = ""}
          >
            <Plus size={16} /> Novo Agente
          </button>
        </div>

        {loading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {[1, 2, 3].map(i => <div key={i} style={{ height: 160, background: "#1A1A1A", borderRadius: 12, border: "1px solid #27272A" }} />)}
          </div>
        ) : agents.length === 0 ? (
          <div style={{ textAlign: "center", padding: "80px 20px" }}>
            <div style={{ width: 72, height: 72, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 16, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
              <Bot size={36} color="#F97316" />
            </div>
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 22, fontWeight: 700, color: "white", marginBottom: 10 }}>Nenhum agente criado</h3>
            <p style={{ color: "#737373", fontSize: 15, marginBottom: 24 }}>Crie seu primeiro agente de IA autônomo para começar a automatizar o CRM.</p>
            <button onClick={() => navigate("/agents/new")} style={{ padding: "12px 28px", background: "#F97316", color: "white", border: "none", borderRadius: 8, fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 15, cursor: "pointer", boxShadow: "0 0 16px rgba(249,115,22,0.3)" }}>
              Criar primeiro agente
            </button>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {agents.map(agent => (
              <div
                key={agent.agent_id}
                data-testid={`agent-card-${agent.agent_id}`}
                style={{ background: "#1A1A1A", border: `1px solid ${agent.status === "active" ? "rgba(249,115,22,0.2)" : "#27272A"}`, borderRadius: 12, padding: 20, transition: "all 0.2s", display: "flex", flexDirection: "column", gap: 14 }}
                onMouseEnter={e => e.currentTarget.style.transform = "translateY(-2px)"}
                onMouseLeave={e => e.currentTarget.style.transform = ""}
              >
                {/* Top */}
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 38, height: 38, background: agent.status === "active" ? "rgba(249,115,22,0.15)" : "rgba(115,115,115,0.1)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <Bot size={20} color={agent.status === "active" ? "#F97316" : "#737373"} />
                    </div>
                    <div>
                      <div style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 15, color: "white" }}>{agent.name}</div>
                      <div style={{ fontSize: 11, color: "#737373", marginTop: 2 }}>{agent.description || "Sem descrição"}</div>
                    </div>
                  </div>
                  <StatusBadge status={agent.status} />
                </div>

                {/* Meta */}
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {getLLMBadge(agent.llm_config?.provider)}
                  <span style={{ fontSize: 11, color: "#737373", background: "#2A2A2A", borderRadius: 4, padding: "2px 6px" }}>{agent.llm_config?.model || "—"}</span>
                  <span style={{ fontSize: 11, color: "#737373" }}>
                    {agent.nodes?.filter(n => n.type === "tool").length || 0} tools
                  </span>
                </div>

                {/* Footer */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid #27272A" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Clock size={12} color="#737373" />
                    <span style={{ fontSize: 11, color: "#737373" }}>{relativeTime(agent.updated_at)}</span>
                    <span style={{ fontSize: 11, color: "#737373" }}>•</span>
                    <span style={{ fontSize: 11, color: "#737373" }}>{agent.run_count || 0} runs</span>
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      onClick={() => toggleStatus(agent)}
                      data-testid={`toggle-agent-${agent.agent_id}`}
                      title={agent.status === "active" ? "Desativar" : "Ativar"}
                      style={{ width: 30, height: 30, background: "transparent", border: "1px solid #27272A", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#A3A3A3", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "#2A2A2A"; e.currentTarget.style.color = "#F97316"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#A3A3A3"; }}
                    >
                      {agent.status === "active" ? <ToggleRight size={14} /> : <ToggleLeft size={14} />}
                    </button>
                    <button
                      onClick={() => navigate(`/agents/${agent.agent_id}`)}
                      data-testid={`edit-agent-${agent.agent_id}`}
                      title="Editar"
                      style={{ width: 30, height: 30, background: "transparent", border: "1px solid #27272A", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#A3A3A3", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "#2A2A2A"; e.currentTarget.style.color = "white"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#A3A3A3"; }}
                    >
                      <Edit3 size={14} />
                    </button>
                    <button
                      onClick={() => deleteAgent(agent.agent_id)}
                      data-testid={`delete-agent-${agent.agent_id}`}
                      disabled={deleting === agent.agent_id}
                      title="Excluir"
                      style={{ width: 30, height: 30, background: "transparent", border: "1px solid #27272A", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#A3A3A3", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.1)"; e.currentTarget.style.borderColor = "rgba(239,68,68,0.3)"; e.currentTarget.style.color = "#EF4444"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}

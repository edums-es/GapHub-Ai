import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Play, Zap, TrendingUp, Clock, CheckCircle, XCircle, Plus, ArrowRight } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function StatCard({ icon: Icon, label, value, color = "#F97316", sub }) {
  return (
    <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: "20px 24px", transition: "all 0.2s" }}
      onMouseEnter={e => e.currentTarget.style.borderColor = "rgba(249,115,22,0.3)"}
      onMouseLeave={e => e.currentTarget.style.borderColor = "#27272A"}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <p style={{ fontSize: 13, color: "#737373", marginBottom: 8, fontFamily: "IBM Plex Sans, sans-serif" }}>{label}</p>
          <p data-testid={`stat-${label.toLowerCase().replace(/\s/g, "-")}`} style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 32, color: "white", lineHeight: 1 }}>{value ?? "—"}</p>
          {sub && <p style={{ fontSize: 12, color: "#737373", marginTop: 6 }}>{sub}</p>}
        </div>
        <div style={{ width: 42, height: 42, background: `${color}15`, border: `1px solid ${color}30`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon size={20} color={color} />
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = { running: ["Executando", "#3B82F6"], completed: ["Concluído", "#10B981"], failed: ["Falhou", "#EF4444"], active: ["Ativo", "#10B981"], inactive: ["Inativo", "#737373"] };
  const [label, color] = map[status] || [status, "#737373"];
  return <span style={{ fontSize: 11, fontWeight: 600, color, background: `${color}15`, border: `1px solid ${color}30`, borderRadius: 100, padding: "2px 8px" }}>{label}</span>;
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    axios.get(`${API}/dashboard/stats`, { withCredentials: true })
      .then(r => setStats(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <Layout>
      <div style={{ animation: "fadeIn 0.3s ease-out" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
          <div>
            <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 28, color: "white", letterSpacing: "-0.03em", marginBottom: 6 }}>
              Olá, {user?.name?.split(" ")[0] || "usuário"} 
            </h1>
            <p style={{ fontSize: 14, color: "#737373" }}>Aqui está um resumo do seu workspace</p>
          </div>
          <button
            onClick={() => navigate("/agents/new")}
            data-testid="new-agent-btn"
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, cursor: "pointer", boxShadow: "0 0 12px rgba(249,115,22,0.3)", transition: "all 0.2s" }}
            onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 0 20px rgba(249,115,22,0.4)"; }}
            onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "0 0 12px rgba(249,115,22,0.3)"; }}
          >
            <Plus size={16} /> Novo Agente
          </button>
        </div>

        {/* Stats Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 28 }}>
          <StatCard icon={Bot} label="Total de Agentes" value={stats?.total_agents} color="#F97316" sub={`${stats?.active_agents ?? 0} ativos`} />
          <StatCard icon={Play} label="Execuções" value={stats?.total_runs} color="#3B82F6" sub="Total de runs" />
          <StatCard icon={CheckCircle} label="Concluídas" value={stats?.completed_runs} color="#10B981" sub="Com sucesso" />
          <StatCard icon={TrendingUp} label="Taxa de Sucesso" value={stats?.success_rate != null ? `${stats.success_rate}%` : "—"} color="#F59E0B" sub="Últimas execuções" />
        </div>

        {/* Two column layout */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          {/* Recent Agents */}
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, color: "white" }}>Agentes Recentes</h3>
              <button onClick={() => navigate("/agents")} style={{ background: "none", border: "none", color: "#F97316", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
                Ver todos <ArrowRight size={13} />
              </button>
            </div>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[1, 2, 3].map(i => <div key={i} style={{ height: 52, background: "#2A2A2A", borderRadius: 8, animation: "pulse-glow 1.5s infinite" }} />)}
              </div>
            ) : stats?.recent_agents?.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {stats.recent_agents.map(agent => (
                  <div
                    key={agent.agent_id}
                    data-testid={`agent-row-${agent.agent_id}`}
                    onClick={() => navigate(`/agents/${agent.agent_id}`)}
                    style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", background: "#2A2A2A", borderRadius: 8, cursor: "pointer", transition: "all 0.2s", border: "1px solid transparent" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.3)"; e.currentTarget.style.background = "#333"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "transparent"; e.currentTarget.style.background = "#2A2A2A"; }}
                  >
                    <div style={{ width: 32, height: 32, background: "rgba(249,115,22,0.1)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <Bot size={16} color="#F97316" />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "white", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{agent.name}</div>
                      <div style={{ fontSize: 11, color: "#737373" }}>{agent.run_count || 0} execuções</div>
                    </div>
                    <StatusBadge status={agent.status} />
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "32px 0" }}>
                <Bot size={32} color="#404040" style={{ margin: "0 auto 12px" }} />
                <p style={{ fontSize: 13, color: "#737373" }}>Nenhum agente criado ainda</p>
                <button onClick={() => navigate("/agents/new")} style={{ marginTop: 12, padding: "8px 16px", background: "rgba(249,115,22,0.1)", color: "#F97316", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
                  Criar primeiro agente
                </button>
              </div>
            )}
          </div>

          {/* Recent Runs */}
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, color: "white" }}>Últimas Execuções</h3>
              <button onClick={() => navigate("/runs")} style={{ background: "none", border: "none", color: "#F97316", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
                Ver todas <ArrowRight size={13} />
              </button>
            </div>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[1, 2, 3].map(i => <div key={i} style={{ height: 52, background: "#2A2A2A", borderRadius: 8 }} />)}
              </div>
            ) : stats?.recent_runs?.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {stats.recent_runs.map(run => (
                  <div
                    key={run.run_id}
                    data-testid={`run-row-${run.run_id}`}
                    onClick={() => navigate("/runs")}
                    style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", background: "#2A2A2A", borderRadius: 8, cursor: "pointer", transition: "all 0.2s", border: "1px solid transparent" }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = "rgba(249,115,22,0.2)"}
                    onMouseLeave={e => e.currentTarget.style.borderColor = "transparent"}
                  >
                    <div style={{ width: 32, height: 32, background: run.status === "completed" ? "rgba(16,185,129,0.1)" : run.status === "failed" ? "rgba(239,68,68,0.1)" : "rgba(59,130,246,0.1)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {run.status === "completed" ? <CheckCircle size={16} color="#10B981" /> : run.status === "failed" ? <XCircle size={16} color="#EF4444" /> : <Play size={16} color="#3B82F6" />}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "white", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{run.agent_name}</div>
                      <div style={{ fontSize: 11, color: "#737373", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{run.input?.slice(0, 40)}...</div>
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      <StatusBadge status={run.status} />
                      <div style={{ fontSize: 10, color: "#737373", marginTop: 4 }}>{relativeTime(run.started_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "32px 0" }}>
                <Clock size={32} color="#404040" style={{ margin: "0 auto 12px" }} />
                <p style={{ fontSize: 13, color: "#737373" }}>Nenhuma execução ainda</p>
              </div>
            )}
          </div>
        </div>

        {/* Per-Agent Metrics Table */}
        {stats?.agent_metrics?.length > 0 && (
          <div style={{ marginTop: 20, background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 20 }}>
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, color: "white", marginBottom: 16 }}>Métricas por Agente</h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #27272A" }}>
                    {["Agente", "Status", "Total Runs", "Concluídas", "Falhas", "Taxa Sucesso", "Último Run"].map(h => (
                      <th key={h} style={{ textAlign: "left", fontSize: 11, color: "#737373", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", padding: "8px 12px" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stats.agent_metrics.map(m => (
                    <tr key={m.agent_id} style={{ borderBottom: "1px solid #1F1F1F", transition: "background 0.15s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "#2A2A2A"}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                      <td style={{ padding: "10px 12px", fontSize: 13, fontWeight: 600, color: "white" }}>{m.name}</td>
                      <td style={{ padding: "10px 12px" }}><StatusBadge status={m.status} /></td>
                      <td style={{ padding: "10px 12px", fontSize: 13, color: "#A3A3A3" }}>{m.total_runs}</td>
                      <td style={{ padding: "10px 12px", fontSize: 13, color: "#10B981" }}>{m.completed_runs}</td>
                      <td style={{ padding: "10px 12px", fontSize: 13, color: m.failed_runs > 0 ? "#EF4444" : "#737373" }}>{m.failed_runs}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ flex: 1, height: 4, background: "#2A2A2A", borderRadius: 2, minWidth: 60 }}>
                            <div style={{ height: "100%", width: `${m.success_rate}%`, background: m.success_rate >= 80 ? "#10B981" : m.success_rate >= 50 ? "#F59E0B" : "#EF4444", borderRadius: 2 }} />
                          </div>
                          <span style={{ fontSize: 12, color: "#A3A3A3", whiteSpace: "nowrap" }}>{m.success_rate}%</span>
                        </div>
                      </td>
                      <td style={{ padding: "10px 12px", fontSize: 12, color: "#737373" }}>{m.last_run ? relativeTime(m.last_run) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
          {[
            { label: "Explorar Marketplace", desc: "Instalar novos MCPs e tools", path: "/marketplace", icon: Zap, color: "#F97316" },
            { label: "Ver Execuções", desc: "Histórico de runs dos agentes", path: "/runs", icon: Play, color: "#3B82F6" },
            { label: "Configurações", desc: "Credenciais e workspace", path: "/settings", icon: Bot, color: "#10B981" },
          ].map(({ label, desc, path, icon: Icon, color }) => (
            <div
              key={path}
              onClick={() => navigate(path)}
              style={{ display: "flex", gap: 12, alignItems: "center", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, padding: "14px 16px", cursor: "pointer", transition: "all 0.2s" }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = `${color}40`; e.currentTarget.style.transform = "translateY(-2px)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.transform = ""; }}
            >
              <div style={{ width: 36, height: 36, background: `${color}15`, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon size={18} color={color} />
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "white", fontFamily: "Outfit, sans-serif" }}>{label}</div>
                <div style={{ fontSize: 12, color: "#737373" }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}

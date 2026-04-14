import React, { useEffect, useState } from "react";
import { Play, Clock, CheckCircle, XCircle, ChevronDown, ChevronUp, Bot } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function StatusBadge({ status }) {
  const map = {
    running: ["Executando", "#3B82F6"],
    completed: ["Concluído", "#10B981"],
    failed: ["Falhou", "#EF4444"],
  };
  const [label, color] = map[status] || [status, "#737373"];
  return <span className={`badge-${status}`} style={{ fontSize: 11, fontWeight: 600, color, background: `${color}15`, border: `1px solid ${color}30`, borderRadius: 100, padding: "3px 10px" }}>{label}</span>;
}

function RunRow({ run }) {
  const [expanded, setExpanded] = useState(false);

  const formatDate = (dt) => {
    if (!dt) return "—";
    return new Date(dt).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  };

  const duration = () => {
    if (!run.started_at || !run.completed_at) return "—";
    const ms = new Date(run.completed_at) - new Date(run.started_at);
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div data-testid={`run-${run.run_id}`} style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, overflow: "hidden", transition: "all 0.2s" }}>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", cursor: "pointer", transition: "background 0.15s" }}
        onMouseEnter={e => e.currentTarget.style.background = "#222"}
        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      >
        <div style={{ width: 34, height: 34, background: run.status === "completed" ? "rgba(16,185,129,0.1)" : run.status === "failed" ? "rgba(239,68,68,0.1)" : "rgba(59,130,246,0.1)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {run.status === "completed" ? <CheckCircle size={16} color="#10B981" /> : run.status === "failed" ? <XCircle size={16} color="#EF4444" /> : <Play size={16} color="#3B82F6" />}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, color: "white" }}>{run.agent_name}</span>
            <StatusBadge status={run.status} />
          </div>
          <div style={{ fontSize: 12, color: "#737373", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {run.input?.slice(0, 80)}{run.input?.length > 80 ? "..." : ""}
          </div>
        </div>

        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 12, color: "#A3A3A3" }}>{duration()}</div>
          <div style={{ fontSize: 11, color: "#737373" }}>{formatDate(run.started_at)}</div>
        </div>
        <div style={{ color: "#737373", flexShrink: 0 }}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {expanded && (
        <div style={{ borderTop: "1px solid #27272A", padding: "16px 18px", animation: "fadeIn 0.2s ease-out" }}>
          {/* Input */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Input</div>
            <div style={{ background: "#2A2A2A", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#A3A3A3", fontFamily: "IBM Plex Sans, sans-serif", lineHeight: 1.5 }}>{run.input}</div>
          </div>

          {/* Steps */}
          {run.steps?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>Ferramentas Utilizadas ({run.steps.length})</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {run.steps.map((step, i) => (
                  <div key={i} style={{ background: "#2A2A2A", borderRadius: 8, padding: "8px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "#F97316", fontFamily: "JetBrains Mono, monospace" }}>{step.tool}</span>
                      <span style={{ fontSize: 10, color: "#737373" }}>iter {step.iteration + 1}</span>
                    </div>
                    {step.params && Object.keys(step.params).length > 0 && (
                      <div style={{ fontSize: 11, color: "#737373", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
                        {JSON.stringify(step.params).slice(0, 120)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Output */}
          {run.output && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Resposta do Agente</div>
              <div style={{ background: "#2A2A2A", borderRadius: 8, padding: "12px 14px", fontSize: 13, color: "#A3A3A3", lineHeight: 1.6, fontFamily: "IBM Plex Sans, sans-serif", whiteSpace: "pre-wrap" }}>{run.output}</div>
            </div>
          )}

          {run.error && (
            <div style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#EF4444" }}>
              Erro: {run.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function RunHistory() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      axios.get(`${API}/runs`, { withCredentials: true })
        .then(r => setRuns(r.data.runs || []))
        .catch(console.error)
        .finally(() => setLoading(false));

    load().then(() => {
      // Auto-cleanup stuck runs (> 10 min in "running")
      axios.post(`${API}/runs/cleanup-stale`, {}, { withCredentials: true })
        .then(r => { if (r.data.cleaned > 0) load(); })
        .catch(() => {});
    });
  }, []);

  const stats = {
    total: runs.length,
    completed: runs.filter(r => r.status === "completed").length,
    failed: runs.filter(r => r.status === "failed").length,
    running: runs.filter(r => r.status === "running").length,
  };

  return (
    <Layout>
      <div style={{ animation: "fadeIn 0.3s ease-out" }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 28, color: "white", letterSpacing: "-0.03em", marginBottom: 6 }}>Histórico de Execuções</h1>
          <p style={{ fontSize: 14, color: "#737373" }}>Todas as execuções dos seus agentes</p>
        </div>

        {/* Quick Stats */}
        <div style={{ display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            { label: "Total", value: stats.total, color: "#A3A3A3" },
            { label: "Concluídas", value: stats.completed, color: "#10B981" },
            { label: "Falhas", value: stats.failed, color: "#EF4444" },
            { label: "Em execução", value: stats.running, color: "#3B82F6" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, padding: "12px 20px", display: "flex", gap: 10, alignItems: "center" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
              <span style={{ fontSize: 13, color: "#737373" }}>{label}:</span>
              <span style={{ fontSize: 15, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Runs list */}
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[1, 2, 3].map(i => <div key={i} style={{ height: 68, background: "#1A1A1A", borderRadius: 10, border: "1px solid #27272A" }} />)}
          </div>
        ) : runs.length === 0 ? (
          <div style={{ textAlign: "center", padding: "80px 20px" }}>
            <Clock size={40} color="#404040" style={{ margin: "0 auto 16px" }} />
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 20, fontWeight: 700, color: "white", marginBottom: 10 }}>Nenhuma execução ainda</h3>
            <p style={{ color: "#737373", fontSize: 14 }}>Execute um agente para ver o histórico aqui.</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {runs.map(run => <RunRow key={run.run_id} run={run} />)}
          </div>
        )}
      </div>
    </Layout>
  );
}

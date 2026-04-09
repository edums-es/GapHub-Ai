import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Calendar, Plus, Trash2, ToggleLeft, ToggleRight, RefreshCw, X, Save, Bot, Clock, CheckCircle, AlertCircle, Info, Edit2, Zap, FileText, Users } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const CRON_PRESETS = [
  { label: "A cada hora", value: "0 * * * *" },
  { label: "A cada 30 minutos", value: "*/30 * * * *" },
  { label: "A cada 6 horas", value: "0 */6 * * *" },
  { label: "Todo dia às 8h (UTC)", value: "0 8 * * *" },
  { label: "Todo dia às 9h (UTC)", value: "0 9 * * *" },
  { label: "Todo dia ao meio-dia (UTC)", value: "0 12 * * *" },
  { label: "Dias úteis às 8h (UTC)", value: "0 8 * * 1-5" },
  { label: "Dias úteis às 9h (UTC)", value: "0 9 * * 1-5" },
  { label: "Toda segunda-feira às 9h (UTC)", value: "0 9 * * 1" },
  { label: "Personalizado", value: "custom" },
];

function describeCron(expr) {
  const map = {
    "0 * * * *": "A cada hora",
    "*/30 * * * *": "A cada 30 min",
    "0 */6 * * *": "A cada 6 horas",
    "0 8 * * *": "Todo dia às 8h",
    "0 9 * * *": "Todo dia às 9h",
    "0 12 * * *": "Todo dia 12h",
    "0 8 * * 1-5": "Dias úteis 8h",
    "0 9 * * 1-5": "Dias úteis 9h",
    "0 9 * * 1": "Segunda 9h",
  };
  return map[expr] || expr;
}

function ScheduleModal({ schedule, agents, onSave, onClose }) {
  const isEdit = !!schedule;
  const [form, setForm] = useState({
    name: schedule?.name || "",
    agent_id: schedule?.agent_id || (agents[0]?.agent_id || ""),
    cron_expression: schedule?.cron_expression || "0 9 * * *",
    input_message: schedule?.input_message || "",
    active: schedule?.active !== undefined ? schedule.active : true,
  });
  const [cronMode, setCronMode] = useState(
    CRON_PRESETS.find(p => p.value === (schedule?.cron_expression || "0 9 * * *")) ? schedule?.cron_expression || "0 9 * * *" : "custom"
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handlePresetChange = (val) => {
    setCronMode(val);
    if (val !== "custom") setForm(f => ({ ...f, cron_expression: val }));
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError("Nome obrigatório"); return; }
    if (!form.agent_id) { setError("Selecione um agente"); return; }
    if (!form.input_message.trim()) { setError("Mensagem de entrada obrigatória"); return; }
    setError("");
    setSaving(true);
    try {
      await onSave(form);
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width: "100%", padding: "9px 12px", background: "#2A2A2A", border: "1px solid #27272A",
    borderRadius: 8, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif",
    outline: "none", boxSizing: "border-box",
  };
  const labelStyle = { display: "block", fontSize: 11, fontWeight: 600, color: "#A3A3A3", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.1em" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 300, padding: 20 }} onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, width: "100%", maxWidth: 520, maxHeight: "90vh", display: "flex", flexDirection: "column", animation: "fadeIn 0.2s ease-out" }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: "18px 22px", borderBottom: "1px solid #27272A", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 16, fontWeight: 700, color: "white", margin: 0 }}>{isEdit ? "Editar Agendamento" : "Novo Agendamento"}</h3>
            <p style={{ fontSize: 12, color: "#737373", margin: "3px 0 0" }}>Configure quando o agente será executado automaticamente</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer" }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 16 }}>
          {error && (
            <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", color: "#EF4444", fontSize: 13 }}>{error}</div>
          )}

          <div>
            <label style={labelStyle}>Nome do agendamento</label>
            <input
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Ex: Triagem diária de tickets"
              style={inputStyle}
              onFocus={e => e.target.style.borderColor = "#F97316"}
              onBlur={e => e.target.style.borderColor = "#27272A"}
            />
          </div>

          <div>
            <label style={labelStyle}>Agente</label>
            <select
              value={form.agent_id}
              onChange={e => setForm(f => ({ ...f, agent_id: e.target.value }))}
              style={{ ...inputStyle, cursor: "pointer" }}
            >
              {agents.map(a => <option key={a.agent_id} value={a.agent_id}>{a.name}</option>)}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Frequência</label>
            <select
              value={cronMode}
              onChange={e => handlePresetChange(e.target.value)}
              style={{ ...inputStyle, marginBottom: 8, cursor: "pointer" }}
            >
              {CRON_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            {cronMode === "custom" && (
              <div>
                <input
                  value={form.cron_expression}
                  onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))}
                  placeholder="Ex: 0 9 * * 1-5"
                  style={inputStyle}
                  onFocus={e => e.target.style.borderColor = "#F97316"}
                  onBlur={e => e.target.style.borderColor = "#27272A"}
                />
                <div style={{ fontSize: 11, color: "#737373", marginTop: 5 }}>Formato: minuto hora dia mês dia-semana (UTC)</div>
              </div>
            )}
            <div style={{ fontSize: 11, color: "#A3A3A3", marginTop: 4, display: "flex", alignItems: "center", gap: 4 }}>
              <Info size={11} /> Todos os horários são em UTC
            </div>
          </div>

          <div>
            <label style={labelStyle}>Mensagem de entrada</label>
            <textarea
              value={form.input_message}
              onChange={e => setForm(f => ({ ...f, input_message: e.target.value }))}
              rows={3}
              placeholder="Mensagem enviada ao agente em cada execução..."
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }}
              onFocus={e => e.target.style.borderColor = "#F97316"}
              onBlur={e => e.target.style.borderColor = "#27272A"}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 14px", background: "#2A2A2A", borderRadius: 8, border: "1px solid #27272A" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "white" }}>Ativo</div>
              <div style={{ fontSize: 11, color: "#737373" }}>Ativar o agendamento imediatamente</div>
            </div>
            <button
              onClick={() => setForm(f => ({ ...f, active: !f.active }))}
              style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
            >
              {form.active
                ? <ToggleRight size={28} color="#F97316" />
                : <ToggleLeft size={28} color="#737373" />}
            </button>
          </div>
        </div>

        <div style={{ padding: "14px 22px", borderTop: "1px solid #27272A" }}>
          <button
            onClick={handleSubmit}
            disabled={saving}
            style={{ width: "100%", padding: "11px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: saving ? "not-allowed" : "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}
          >
            <Save size={15} /> {saving ? "Salvando..." : (isEdit ? "Salvar alterações" : "Criar agendamento")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Schedules() {
  const [schedules, setSchedules] = useState([]);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editSchedule, setEditSchedule] = useState(null);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const showSuccess = (msg) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(""), 3000); };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [schedsRes, agentsRes] = await Promise.all([
        axios.get(`${API}/schedules`, { withCredentials: true }),
        axios.get(`${API}/agents`, { withCredentials: true }),
      ]);
      setSchedules(schedsRes.data.schedules || []);
      setAgents(agentsRes.data.agents || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreate = async (form) => {
    const { data } = await axios.post(`${API}/schedules`, form, { withCredentials: true });
    setSchedules(s => [data, ...s]);
    showSuccess("Agendamento criado!");
  };

  const handleUpdate = async (form) => {
    const { data } = await axios.put(`${API}/schedules/${editSchedule.schedule_id}`, form, { withCredentials: true });
    setSchedules(s => s.map(sc => sc.schedule_id === data.schedule_id ? data : sc));
    showSuccess("Agendamento atualizado!");
  };

  const handleToggle = async (schedule) => {
    try {
      const { data } = await axios.put(`${API}/schedules/${schedule.schedule_id}`, { active: !schedule.active }, { withCredentials: true });
      setSchedules(s => s.map(sc => sc.schedule_id === data.schedule_id ? data : sc));
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao atualizar");
    }
  };

  const handleDelete = async (scheduleId) => {
    if (!window.confirm("Excluir este agendamento?")) return;
    try {
      await axios.delete(`${API}/schedules/${scheduleId}`, { withCredentials: true });
      setSchedules(s => s.filter(sc => sc.schedule_id !== scheduleId));
      showSuccess("Agendamento excluído!");
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao excluir");
    }
  };

  const formatDate = (dt) => {
    if (!dt) return null;
    return new Date(dt).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
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
      <div style={{ animation: "fadeIn 0.3s ease-out" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, background: "rgba(249,115,22,0.15)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Calendar size={20} color="#F97316" />
            </div>
            <div>
              <h1 style={{ fontFamily: "Outfit, sans-serif", fontSize: 22, fontWeight: 800, color: "white", margin: 0 }}>Agendamentos</h1>
              <p style={{ fontSize: 12, color: "#737373", margin: 0 }}>Execute agentes automaticamente por cron</p>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={fetchData}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "#A3A3A3", cursor: "pointer", fontSize: 13, transition: "all 0.2s" }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={() => { setEditSchedule(null); setShowModal(true); }}
              disabled={agents.length === 0}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 18px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: agents.length === 0 ? "not-allowed" : "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13, opacity: agents.length === 0 ? 0.5 : 1 }}
            >
              <Plus size={15} /> Novo Agendamento
            </button>
          </div>
        </div>

        {/* Alerts */}
        {error && (
          <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, color: "#EF4444", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            {error}
            <button onClick={() => setError("")} style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer" }}><X size={14} /></button>
          </div>
        )}
        {successMsg && (
          <div style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, color: "#10B981", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
            <CheckCircle size={14} /> {successMsg}
          </div>
        )}

        {/* What is this? — shown while no schedules exist */}
        {schedules.length === 0 && (
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 28, marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
              <div style={{ width: 36, height: 36, background: "rgba(249,115,22,0.12)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Zap size={18} color="#F97316" />
              </div>
              <div>
                <div style={{ fontFamily: "Outfit, sans-serif", fontSize: 15, fontWeight: 700, color: "white" }}>O que são Agendamentos?</div>
                <div style={{ fontSize: 12, color: "#737373" }}>Automação sem precisar clicar em nada</div>
              </div>
            </div>
            <p style={{ fontSize: 13, color: "#A3A3A3", lineHeight: 1.7, margin: "0 0 20px" }}>
              Com agendamentos, seus agentes rodam <strong style={{ color: "white" }}>automaticamente em horários definidos</strong> — sem que você precise enviar um comando manualmente. É como contratar um assistente que trabalha 24h.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
              {[
                {
                  icon: FileText, color: "#3B82F6",
                  title: "Relatório Diário",
                  desc: "Todo dia às 9h, o agente lista os tickets pendentes e gera um resumo automático",
                  cron: "0 9 * * *",
                },
                {
                  icon: Users, color: "#10B981",
                  title: "Follow-up de Leads",
                  desc: "Dias úteis às 8h, verifica contatos sem resposta e envia mensagens de acompanhamento",
                  cron: "0 8 * * 1-5",
                },
                {
                  icon: Zap, color: "#F97316",
                  title: "Triagem de Leads",
                  desc: "A cada hora, verifica novos leads no CRM e faz o pré-atendimento automaticamente",
                  cron: "0 * * * *",
                },
              ].map(({ icon: Icon, color, title, desc, cron }) => (
                <div key={title} style={{ background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 10, padding: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <div style={{ width: 28, height: 28, background: `${color}18`, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Icon size={14} color={color} />
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>{title}</span>
                  </div>
                  <p style={{ fontSize: 12, color: "#A3A3A3", margin: "0 0 8px", lineHeight: 1.5 }}>{desc}</p>
                  <div style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11, color: color, background: `${color}10`, padding: "3px 8px", borderRadius: 5, display: "inline-block" }}>{cron}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {agents.length === 0 && (
          <div style={{ background: "rgba(249,115,22,0.05)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 10, padding: 16, marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
            <Info size={16} color="#F97316" />
            <span style={{ fontSize: 13, color: "#A3A3A3" }}>Você precisa ter pelo menos um agente salvo para criar agendamentos.</span>
          </div>
        )}

        {/* Schedules list */}
        {schedules.length === 0 ? (
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 60, textAlign: "center" }}>
            <Calendar size={40} style={{ color: "#27272A", marginBottom: 12 }} />
            <p style={{ fontSize: 16, fontWeight: 600, color: "#A3A3A3", fontFamily: "Outfit, sans-serif", marginBottom: 6 }}>Nenhum agendamento</p>
            <p style={{ fontSize: 13, color: "#737373", marginBottom: 20 }}>Crie agendamentos para executar seus agentes automaticamente</p>
            {agents.length > 0 && (
              <button
                onClick={() => { setEditSchedule(null); setShowModal(true); }}
                style={{ padding: "10px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13 }}
              >
                Criar primeiro agendamento
              </button>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {schedules.map(schedule => (
              <div
                key={schedule.schedule_id}
                style={{ background: "#1A1A1A", border: `1px solid ${schedule.active ? "rgba(249,115,22,0.2)" : "#27272A"}`, borderRadius: 12, padding: "16px 20px", display: "flex", alignItems: "center", gap: 16, transition: "border-color 0.2s" }}
              >
                {/* Status indicator */}
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: schedule.active ? "#10B981" : "#404040", boxShadow: schedule.active ? "0 0 8px #10B981" : "none", flexShrink: 0 }} />

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, color: "white", fontSize: 14 }}>{schedule.name}</span>
                    {!schedule.active && <span style={{ fontSize: 10, color: "#737373", background: "#2A2A2A", padding: "2px 6px", borderRadius: 4, border: "1px solid #27272A" }}>PAUSADO</span>}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#A3A3A3" }}>
                      <Bot size={12} />
                      <span>{schedule.agent_name}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#A3A3A3" }}>
                      <Clock size={12} />
                      <span style={{ fontFamily: "IBM Plex Mono, monospace", color: "#F97316" }}>{schedule.cron_expression}</span>
                      <span style={{ color: "#737373" }}>({describeCron(schedule.cron_expression)})</span>
                    </div>
                    {schedule.last_run && (
                      <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#737373" }}>
                        {schedule.last_run_status === "completed"
                          ? <CheckCircle size={11} color="#10B981" />
                          : <AlertCircle size={11} color="#EF4444" />}
                        Última: {formatDate(schedule.last_run)}
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  <button
                    onClick={() => handleToggle(schedule)}
                    title={schedule.active ? "Pausar" : "Ativar"}
                    style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}
                  >
                    {schedule.active
                      ? <ToggleRight size={22} color="#F97316" />
                      : <ToggleLeft size={22} color="#737373" />}
                  </button>
                  <button
                    onClick={() => { setEditSchedule(schedule); setShowModal(true); }}
                    title="Editar"
                    style={{ padding: "6px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", transition: "all 0.2s" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; }}
                  >
                    <Edit2 size={13} color="#A3A3A3" />
                  </button>
                  <button
                    onClick={() => handleDelete(schedule.schedule_id)}
                    title="Excluir"
                    style={{ padding: "6px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", transition: "all 0.2s" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.2)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "rgba(239,68,68,0.08)"; }}
                  >
                    <Trash2 size={13} color="#EF4444" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <ScheduleModal
          schedule={editSchedule}
          agents={agents}
          onSave={editSchedule ? handleUpdate : handleCreate}
          onClose={() => { setShowModal(false); setEditSchedule(null); }}
        />
      )}
    </Layout>
  );
}

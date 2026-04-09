import React, { useEffect, useState } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Shield, Users, Building2, Bot, Play, Trash2, RefreshCw, ChevronDown, Search, X, Crown, CheckCircle, AlertCircle, Clock, Calendar } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const PLAN_COLORS = {
  free: { bg: "rgba(115,115,115,0.15)", text: "#A3A3A3", border: "rgba(115,115,115,0.3)" },
  pro: { bg: "rgba(59,130,246,0.15)", text: "#3B82F6", border: "rgba(59,130,246,0.3)" },
  enterprise: { bg: "rgba(249,115,22,0.15)", text: "#F97316", border: "rgba(249,115,22,0.3)" },
};

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: "20px 22px", display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{ width: 44, height: 44, background: `${color}18`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <Icon size={20} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 24, fontWeight: 800, color: "white", fontFamily: "Outfit, sans-serif", lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 12, color: "#737373", marginTop: 4, fontFamily: "IBM Plex Sans, sans-serif" }}>{label}</div>
      </div>
    </div>
  );
}

function DeleteConfirmModal({ tenant, onConfirm, onClose }) {
  const [confirming, setConfirming] = useState(false);
  const handleConfirm = async () => {
    setConfirming(true);
    await onConfirm();
    setConfirming(false);
  };
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 300, padding: 20 }} onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 16, maxWidth: 440, width: "100%", padding: 28 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <div style={{ width: 44, height: 44, background: "rgba(239,68,68,0.1)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Trash2 size={20} color="#EF4444" />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>Excluir Tenant</div>
            <div style={{ fontSize: 12, color: "#737373" }}>Esta a\u00e7\u00e3o n\u00e3o pode ser desfeita</div>
          </div>
        </div>
        <p style={{ fontSize: 13, color: "#A3A3A3", lineHeight: 1.6, marginBottom: 20 }}>
          Voc\u00ea est\u00e1 prestes a excluir o workspace <strong style={{ color: "white" }}>{tenant?.name}</strong> e todos os dados do usu\u00e1rio <strong style={{ color: "white" }}>{tenant?.owner?.email}</strong>, incluindo agentes, execu\u00e7\u00f5es e credenciais.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={onClose}
            style={{ flex: 1, padding: "10px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "#A3A3A3", cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13 }}
          >Cancelar</button>
          <button
            onClick={handleConfirm}
            disabled={confirming}
            style={{ flex: 1, padding: "10px", background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 8, color: "#EF4444", cursor: confirming ? "not-allowed" : "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 13 }}
          >
            {confirming ? "Excluindo..." : "Excluir Permanentemente"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminPanel() {
  const [stats, setStats] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState("all");
  const [deleteTenant, setDeleteTenant] = useState(null);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [changingPlan, setChangingPlan] = useState({});

  const showSuccess = (msg) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(""), 3000);
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, tenantsRes] = await Promise.all([
        axios.get(`${API}/admin/stats`, { withCredentials: true }),
        axios.get(`${API}/admin/tenants`, { withCredentials: true }),
      ]);
      setStats(statsRes.data);
      setTenants(tenantsRes.data.tenants || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handlePlanChange = async (workspaceId, newPlan) => {
    setChangingPlan(p => ({ ...p, [workspaceId]: true }));
    try {
      await axios.put(`${API}/admin/tenants/${workspaceId}`, { plan: newPlan }, { withCredentials: true });
      setTenants(ts => ts.map(t => t.workspace_id === workspaceId ? { ...t, plan: newPlan } : t));
      showSuccess("Plano atualizado com sucesso");
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao atualizar plano");
    } finally {
      setChangingPlan(p => ({ ...p, [workspaceId]: false }));
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTenant) return;
    try {
      await axios.delete(`${API}/admin/users/${deleteTenant.owner?.user_id}`, { withCredentials: true });
      setTenants(ts => ts.filter(t => t.workspace_id !== deleteTenant.workspace_id));
      showSuccess("Tenant exclu\u00eddo com sucesso");
      setDeleteTenant(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao excluir tenant");
    }
  };

  const filtered = tenants.filter(t => {
    const matchSearch = !search ||
      t.name?.toLowerCase().includes(search.toLowerCase()) ||
      t.owner?.email?.toLowerCase().includes(search.toLowerCase()) ||
      t.owner?.name?.toLowerCase().includes(search.toLowerCase());
    const matchPlan = planFilter === "all" || t.plan === planFilter;
    return matchSearch && matchPlan;
  });

  const formatDate = (dt) => {
    if (!dt) return "-";
    return new Date(dt).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
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
              <Shield size={20} color="#F97316" />
            </div>
            <div>
              <h1 style={{ fontFamily: "Outfit, sans-serif", fontSize: 22, fontWeight: 800, color: "white", margin: 0 }}>Admin Panel</h1>
              <p style={{ fontSize: 12, color: "#737373", margin: 0 }}>Ger\u00eancia de todos os tenants da plataforma</p>
            </div>
          </div>
          <button
            onClick={fetchData}
            style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "#A3A3A3", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif", fontSize: 13, transition: "all 0.2s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
          >
            <RefreshCw size={14} /> Atualizar
          </button>
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

        {/* Stats */}
        {stats && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 14, marginBottom: 28 }}>
            <StatCard icon={Users} label="Usu\u00e1rios" value={stats.total_users} color="#3B82F6" />
            <StatCard icon={Building2} label="Workspaces" value={stats.total_workspaces} color="#8B5CF6" />
            <StatCard icon={Bot} label="Agentes" value={stats.total_agents} color="#F97316" />
            <StatCard icon={Play} label="Execu\u00e7\u00f5es" value={stats.total_runs} color="#10B981" />
            <StatCard icon={Crown} label="Taxa de Sucesso" value={`${stats.success_rate}%`} color="#F59E0B" />
            <StatCard icon={Calendar} label="Agendamentos Ativos" value={stats.active_schedules || 0} color="#EC4899" />
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 200, position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#737373" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar workspace ou email..."
              style={{ width: "100%", padding: "9px 10px 9px 32px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
              onFocus={e => e.target.style.borderColor = "#F97316"}
              onBlur={e => e.target.style.borderColor = "#27272A"}
            />
          </div>
          <select
            value={planFilter}
            onChange={e => setPlanFilter(e.target.value)}
            style={{ padding: "9px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none" }}
          >
            <option value="all">Todos os planos</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>

        {/* Tenant Table */}
        <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid #27272A", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>Tenants ({filtered.length})</div>
          </div>

          {filtered.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#737373" }}>
              <Building2 size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
              <p style={{ fontSize: 14 }}>Nenhum tenant encontrado</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #27272A" }}>
                    {["Workspace", "Propriet\u00e1rio", "Plano", "Agentes", "Execu\u00e7\u00f5es", "Criado em", "A\u00e7\u00f5es"].map(h => (
                      <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontFamily: "Outfit, sans-serif", fontWeight: 600, color: "#737373", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(tenant => {
                    const planStyle = PLAN_COLORS[tenant.plan] || PLAN_COLORS.free;
                    return (
                      <tr key={tenant.workspace_id} style={{ borderBottom: "1px solid rgba(39,39,42,0.6)", transition: "background 0.15s" }}
                        onMouseEnter={e => e.currentTarget.style.background = "#222"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                      >
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ fontWeight: 600, color: "white" }}>{tenant.name}</div>
                          <div style={{ fontSize: 11, color: "#737373" }}>{tenant.workspace_id}</div>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ color: "#E2E8F0" }}>{tenant.owner?.name || "-"}</div>
                          <div style={{ fontSize: 11, color: "#737373" }}>{tenant.owner?.email || "-"}</div>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <select
                            value={tenant.plan || "free"}
                            onChange={e => handlePlanChange(tenant.workspace_id, e.target.value)}
                            disabled={changingPlan[tenant.workspace_id]}
                            style={{ padding: "4px 8px", background: planStyle.bg, border: `1px solid ${planStyle.border}`, borderRadius: 6, color: planStyle.text, fontSize: 12, fontFamily: "Outfit, sans-serif", fontWeight: 700, cursor: "pointer", outline: "none" }}
                          >
                            <option value="free">Free</option>
                            <option value="pro">Pro</option>
                            <option value="enterprise">Enterprise</option>
                          </select>
                        </td>
                        <td style={{ padding: "12px 16px", color: "#E2E8F0", textAlign: "center" }}>{tenant.agent_count || 0}</td>
                        <td style={{ padding: "12px 16px", color: "#E2E8F0", textAlign: "center" }}>{tenant.run_count || 0}</td>
                        <td style={{ padding: "12px 16px", color: "#A3A3A3", whiteSpace: "nowrap" }}>{formatDate(tenant.created_at)}</td>
                        <td style={{ padding: "12px 16px" }}>
                          <button
                            onClick={() => setDeleteTenant(tenant)}
                            title="Excluir tenant"
                            style={{ padding: "6px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s" }}
                            onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.2)"; }}
                            onMouseLeave={e => { e.currentTarget.style.background = "rgba(239,68,68,0.1)"; }}
                          >
                            <Trash2 size={14} color="#EF4444" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Delete confirm modal */}
      {deleteTenant && (
        <DeleteConfirmModal
          tenant={deleteTenant}
          onConfirm={handleDeleteConfirm}
          onClose={() => setDeleteTenant(null)}
        />
      )}
    </Layout>
  );
}

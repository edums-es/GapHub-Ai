import React, { useEffect, useState } from "react";
import { Save, Key, Trash2, User, Building2, CheckCircle, AlertCircle, Shield, RefreshCw, Edit2, Eye, EyeOff, X } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const CRED_FIELDS = {
  clickmassa: [
    { key: "base_url",  label: "URL da instância",    placeholder: "https://enterprise-40api.seudominio.com.br", type: "text" },
    { key: "token",     label: "Token de API",         placeholder: "••••••••",                                  type: "password", sensitive: true },
    { key: "email",     label: "Email de login (opcional)", placeholder: "admin@seudominio.com.br",            type: "email" },
    { key: "password",  label: "Senha (opcional)",     placeholder: "••••••••",                                  type: "password", sensitive: true },
    { key: "canal_id",  label: "Canal ID (WhatsApp)",  placeholder: "ID do canal padrão",                        type: "text" },
  ],
};

const MCP_LABELS = {
  clickmassa: "ClickMassa CRM",
  web_search: "Busca na Web",
  http_request: "HTTP Request",
};

function Section({ title, icon: Icon, children }) {
  return (
    <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 24, marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid #27272A" }}>
        <div style={{ width: 32, height: 32, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon size={16} color="#F97316" />
        </div>
        <h2 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, color: "white", margin: 0 }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

function CredentialEditModal({ mcp_id, existingMasked, onClose, onSaved }) {
  const fields = CRED_FIELDS[mcp_id] || [];
  const [formData, setFormData] = useState(() => {
    const init = {};
    fields.forEach(f => {
      // Pre-fill non-sensitive fields from existing masked data
      if (!f.sensitive && existingMasked?.[f.key]) {
        init[f.key] = existingMasked[f.key];
      } else {
        init[f.key] = "";
      }
    });
    return init;
  });
  const [showPwd, setShowPwd] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await axios.post(`${API}/credentials`, { mcp_id, data: formData }, { withCredentials: true });
      onSaved();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao salvar credenciais");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 20 }}
      onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, padding: 28, width: "100%", maxWidth: 460 }}
        onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 16, fontWeight: 700, color: "white", margin: 0 }}>
            Editar {MCP_LABELS[mcp_id] || mcp_id}
          </h3>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#737373", cursor: "pointer" }}><X size={16} /></button>
        </div>

        {error && (
          <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", marginBottom: 14, color: "#EF4444", fontSize: 13 }}>{error}</div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
          {fields.map(f => (
            <div key={f.key}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 5 }}>
                {f.label}
                {f.sensitive && <span style={{ fontSize: 10, color: "#737373", marginLeft: 6 }}>(deixe vazio para manter atual)</span>}
              </label>
              <div style={{ position: "relative" }}>
                <input
                  type={f.sensitive && !showPwd[f.key] ? "password" : "text"}
                  placeholder={f.sensitive ? "••••••••" : f.placeholder}
                  value={formData[f.key] || ""}
                  onChange={e => setFormData(d => ({ ...d, [f.key]: e.target.value }))}
                  style={{ width: "100%", padding: f.sensitive ? "9px 36px 9px 12px" : "9px 12px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
                  onFocus={e => e.target.style.borderColor = "#F97316"}
                  onBlur={e => e.target.style.borderColor = "#27272A"}
                />
                {f.sensitive && (
                  <button onClick={() => setShowPwd(p => ({ ...p, [f.key]: !p[f.key] }))}
                    style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#737373", padding: 2 }}>
                    {showPwd[f.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose}
            style={{ flex: 1, padding: "10px", background: "#2A2A2A", color: "#A3A3A3", border: "1px solid #27272A", borderRadius: 8, cursor: "pointer", fontSize: 13, fontFamily: "Outfit, sans-serif", fontWeight: 600 }}>
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving}
            style={{ flex: 2, padding: "10px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: saving ? "not-allowed" : "pointer", fontSize: 13, fontFamily: "Outfit, sans-serif", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
            {saving ? <RefreshCw size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={13} />}
            {saving ? "Salvando..." : "Salvar credenciais"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Settings() {
  const { user, refreshUser } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [credentials, setCredentials] = useState([]);
  const [profile, setProfile] = useState({ name: "", email: "" });
  const [wsName, setWsName] = useState("");
  const [saving, setSaving] = useState("");
  const [saved, setSaved] = useState("");
  const [editingCred, setEditingCred] = useState(null);
  // Inline add form state
  const [addForm, setAddForm] = useState({});
  const [addSaving, setAddSaving] = useState(false);
  const [addSaved, setAddSaved] = useState(false);
  const [addError, setAddError] = useState("");
  const [showAddPwd, setShowAddPwd] = useState({});

  const loadCredentials = () =>
    axios.get(`${API}/credentials`, { withCredentials: true })
      .then(r => setCredentials(r.data.credentials || []))
      .catch(console.error);

  useEffect(() => {
    if (user) setProfile({ name: user.name || "", email: user.email || "" });
    Promise.all([
      axios.get(`${API}/workspace`, { withCredentials: true }),
      axios.get(`${API}/credentials`, { withCredentials: true }),
    ]).then(([wsRes, credRes]) => {
      setWorkspace(wsRes.data);
      setWsName(wsRes.data.name || "");
      setCredentials(credRes.data.credentials || []);
    }).catch(console.error);
  }, [user]);

  const saveProfile = async () => {
    setSaving("profile");
    try {
      await axios.put(`${API}/auth/profile`, { name: profile.name }, { withCredentials: true });
      await refreshUser();
      setSaved("profile");
      setTimeout(() => setSaved(""), 2000);
    } finally { setSaving(""); }
  };

  const saveWorkspace = async () => {
    setSaving("workspace");
    try {
      await axios.put(`${API}/workspace`, { name: wsName }, { withCredentials: true });
      setSaved("workspace");
      setTimeout(() => setSaved(""), 2000);
    } finally { setSaving(""); }
  };

  const deleteCred = async (mcp_id) => {
    if (!window.confirm(`Remover credenciais de ${MCP_LABELS[mcp_id] || mcp_id}?`)) return;
    await axios.delete(`${API}/credentials/${mcp_id}`, { withCredentials: true });
    setCredentials(c => c.filter(x => x.mcp_id !== mcp_id));
  };

  const handleAddSave = async () => {
    setAddSaving(true);
    setAddError("");
    try {
      await axios.post(`${API}/credentials`, { mcp_id: "clickmassa", data: addForm }, { withCredentials: true });
      setAddSaved(true);
      setAddForm({});
      await loadCredentials();
      setTimeout(() => setAddSaved(false), 2000);
    } catch (e) {
      setAddError(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setAddSaving(false);
    }
  };

  const clickmassaCred = credentials.find(c => c.mcp_id === "clickmassa");
  const fields = CRED_FIELDS.clickmassa;

  const inputStyle = {
    width: "100%", padding: "9px 12px", background: "#2A2A2A",
    border: "1px solid #27272A", borderRadius: 7, color: "white",
    fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box",
  };

  return (
    <Layout>
      <div style={{ animation: "fadeIn 0.3s ease-out", maxWidth: 700 }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 28, color: "white", letterSpacing: "-0.03em", marginBottom: 6 }}>Configurações</h1>
          <p style={{ fontSize: 14, color: "#737373" }}>Gerencie seu perfil, workspace e credenciais</p>
        </div>

        {/* Profile */}
        <Section title="Perfil" icon={User}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Nome</label>
              <input
                data-testid="profile-name-input"
                value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                style={{ ...inputStyle, padding: "10px 14px", fontSize: 14 }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Email</label>
              <input value={profile.email} disabled style={{ ...inputStyle, padding: "10px 14px", fontSize: 14, color: "#737373", cursor: "not-allowed" }} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button onClick={saveProfile} data-testid="save-profile-btn" disabled={saving === "profile"}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14 }}>
                {saving === "profile" ? <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={14} />}
                Salvar perfil
              </button>
              {saved === "profile" && <span style={{ fontSize: 13, color: "#10B981", display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={14} /> Salvo!</span>}
            </div>
          </div>
        </Section>

        {/* Workspace */}
        <Section title="Workspace" icon={Building2}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Nome do Workspace</label>
              <input
                data-testid="workspace-name-input"
                value={wsName}
                onChange={e => setWsName(e.target.value)}
                style={{ ...inputStyle, padding: "10px 14px", fontSize: 14 }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            {workspace && (
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                {[
                  { label: "Agentes", value: workspace.agent_count },
                  { label: "Execuções", value: workspace.run_count },
                  { label: "Credenciais", value: workspace.credential_count },
                  { label: "Plano", value: workspace.plan?.toUpperCase() },
                ].map(({ label, value }) => (
                  <div key={label} style={{ background: "#2A2A2A", borderRadius: 8, padding: "8px 14px" }}>
                    <div style={{ fontSize: 10, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "white", fontFamily: "Outfit, sans-serif" }}>{value}</div>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button onClick={saveWorkspace} data-testid="save-workspace-btn" disabled={saving === "workspace"}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14 }}>
                {saving === "workspace" ? <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={14} />}
                Salvar workspace
              </button>
              {saved === "workspace" && <span style={{ fontSize: 13, color: "#10B981", display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={14} /> Salvo!</span>}
            </div>
          </div>
        </Section>

        {/* Credentials */}
        <Section title="Credenciais de MCP" icon={Key}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Saved credentials */}
            {credentials.map(cred => (
              <div key={cred.mcp_id} style={{ background: "#2A2A2A", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 10, padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 8, height: 8, background: "#10B981", borderRadius: "50%", boxShadow: "0 0 6px #10B981" }} />
                    <span style={{ fontSize: 14, fontWeight: 600, color: "white", fontFamily: "Outfit, sans-serif" }}>{MCP_LABELS[cred.mcp_id] || cred.mcp_id}</span>
                    <span style={{ fontSize: 10, color: "#10B981", background: "rgba(16,185,129,0.1)", padding: "2px 7px", borderRadius: 4, fontWeight: 600 }}>CONFIGURADO</span>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button onClick={() => setEditingCred(cred)}
                      style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", cursor: "pointer", fontSize: 12, transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}>
                      <Edit2 size={12} /> Editar
                    </button>
                    <button onClick={() => deleteCred(cred.mcp_id)}
                      style={{ width: 30, height: 30, background: "transparent", border: "1px solid #27272A", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.1)"; e.currentTarget.style.borderColor = "rgba(239,68,68,0.3)"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "#27272A"; }}>
                      <Trash2 size={13} color="#EF4444" />
                    </button>
                  </div>
                </div>
                {/* Show non-sensitive values */}
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {Object.entries(cred.data_masked || {}).map(([k, v]) => (
                    <div key={k} style={{ background: "#1A1A1A", borderRadius: 6, padding: "4px 10px" }}>
                      <span style={{ fontSize: 10, color: "#737373", textTransform: "uppercase", letterSpacing: "0.08em" }}>{k}: </span>
                      <span style={{ fontSize: 11, color: v === "••••••••" ? "#737373" : "#A3A3A3", fontFamily: "IBM Plex Mono, monospace" }}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {/* Add ClickMassa (only if not yet configured) */}
            {!clickmassaCred && (
              <div style={{ background: "rgba(249,115,22,0.04)", border: "1px dashed rgba(249,115,22,0.25)", borderRadius: 10, padding: 18 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#F97316", marginBottom: 14, display: "flex", alignItems: "center", gap: 7 }}>
                  <Shield size={14} /> Configurar ClickMassa CRM
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {fields.map(f => (
                    <div key={f.key}>
                      <label style={{ display: "block", fontSize: 11, fontWeight: 500, color: "#A3A3A3", marginBottom: 5 }}>{f.label}</label>
                      <div style={{ position: "relative" }}>
                        <input
                          data-testid={`settings-${f.key}`}
                          type={f.sensitive && !showAddPwd[f.key] ? "password" : "text"}
                          placeholder={f.placeholder}
                          value={addForm[f.key] || ""}
                          onChange={e => setAddForm(d => ({ ...d, [f.key]: e.target.value }))}
                          style={{ ...inputStyle, paddingRight: f.sensitive ? 36 : 12 }}
                          onFocus={e => e.target.style.borderColor = "#F97316"}
                          onBlur={e => e.target.style.borderColor = "#27272A"}
                        />
                        {f.sensitive && (
                          <button onClick={() => setShowAddPwd(p => ({ ...p, [f.key]: !p[f.key] }))}
                            style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#737373", padding: 2 }}>
                            {showAddPwd[f.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {addError && <div style={{ color: "#EF4444", fontSize: 12 }}>{addError}</div>}
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <button onClick={handleAddSave} data-testid="save-clickmassa-creds" disabled={addSaving}
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", background: "#F97316", color: "white", border: "none", borderRadius: 7, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13 }}>
                      {addSaving ? <RefreshCw size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Shield size={13} />}
                      Salvar credenciais
                    </button>
                    {addSaved && <span style={{ fontSize: 12, color: "#10B981", display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={13} /> Salvo!</span>}
                  </div>
                </div>
              </div>
            )}

            {/* Help text */}
            <div style={{ background: "rgba(59,130,246,0.05)", border: "1px solid rgba(59,130,246,0.15)", borderRadius: 8, padding: "10px 14px" }}>
              <p style={{ fontSize: 12, color: "#737373", margin: 0, lineHeight: 1.6 }}>
                <strong style={{ color: "#3B82F6" }}>Dica:</strong> As credenciais são criptografadas e utilizadas pelos agentes para acessar o CRM. Ao editar, deixe o campo de senha vazio para manter a senha atual.
              </p>
            </div>
          </div>
        </Section>
      </div>

      {editingCred && (
        <CredentialEditModal
          mcp_id={editingCred.mcp_id}
          existingMasked={editingCred.data_masked}
          onClose={() => setEditingCred(null)}
          onSaved={loadCredentials}
        />
      )}
    </Layout>
  );
}

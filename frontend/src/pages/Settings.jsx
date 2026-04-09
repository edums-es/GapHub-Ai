import React, { useEffect, useState } from "react";
import { Save, Key, Trash2, User, Building2, CheckCircle, AlertCircle, Shield, RefreshCw } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const MCP_LABELS = {
  clickmassa: "ClickMassa CRM",
  web_search: "Busca na Web",
  http_request: "HTTP Request",
  whatsapp_evolution: "WhatsApp Evolution",
  google_calendar: "Google Calendar",
  gmail: "Gmail",
};

function Section({ title, icon: Icon, children }) {
  return (
    <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 24, marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid #27272A" }}>
        <div style={{ width: 32, height: 32, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon size={16} color="#F97316" />
        </div>
        <h2 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, color: "white" }}>{title}</h2>
      </div>
      {children}
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
  const [selectedCred, setSelectedCred] = useState(null);
  const [newCred, setNewCred] = useState({ mcp_id: "clickmassa", data: {} });
  const [showCredModal, setShowCredModal] = useState(false);

  useEffect(() => {
    if (user) {
      setProfile({ name: user.name || "", email: user.email || "" });
    }
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
    } finally {
      setSaving("");
    }
  };

  const saveWorkspace = async () => {
    setSaving("workspace");
    try {
      await axios.put(`${API}/workspace`, { name: wsName }, { withCredentials: true });
      setSaved("workspace");
      setTimeout(() => setSaved(""), 2000);
    } finally {
      setSaving("");
    }
  };

  const deleteCred = async (mcp_id) => {
    if (!window.confirm(`Remover credenciais de ${MCP_LABELS[mcp_id] || mcp_id}?`)) return;
    await axios.delete(`${API}/credentials/${mcp_id}`, { withCredentials: true });
    setCredentials(c => c.filter(x => x.mcp_id !== mcp_id));
  };

  const CRED_FIELDS = {
    clickmassa: [
      { key: "base_url", label: "URL da instância", placeholder: "https://enterprise-40api.seudominio.com.br", type: "text" },
      { key: "email", label: "Email de login", placeholder: "admin@seudominio.com.br", type: "email" },
      { key: "password", label: "Senha", placeholder: "••••••••", type: "password" },
      { key: "canal_id", label: "Canal ID (WhatsApp)", placeholder: "ID do canal padrão", type: "text" },
    ],
    web_search: [],
    http_request: [],
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
                style={{ width: "100%", padding: "10px 14px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Email</label>
              <input
                value={profile.email}
                disabled
                style={{ width: "100%", padding: "10px 14px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "#737373", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box", cursor: "not-allowed" }}
              />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button
                onClick={saveProfile}
                data-testid="save-profile-btn"
                disabled={saving === "profile"}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, transition: "all 0.2s" }}
              >
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
                style={{ width: "100%", padding: "10px 14px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
                onFocus={e => e.target.style.borderColor = "#F97316"}
                onBlur={e => e.target.style.borderColor = "#27272A"}
              />
            </div>
            {workspace && (
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
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
              <button
                onClick={saveWorkspace}
                data-testid="save-workspace-btn"
                disabled={saving === "workspace"}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14 }}
              >
                {saving === "workspace" ? <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={14} />}
                Salvar workspace
              </button>
              {saved === "workspace" && <span style={{ fontSize: 13, color: "#10B981", display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={14} /> Salvo!</span>}
            </div>
          </div>
        </Section>

        {/* Credentials */}
        <Section title="Credenciais de MCP" icon={Key}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {credentials.length === 0 ? (
              <div style={{ background: "rgba(249,115,22,0.05)", border: "1px dashed rgba(249,115,22,0.2)", borderRadius: 8, padding: "20px", textAlign: "center" }}>
                <AlertCircle size={20} color="#F97316" style={{ margin: "0 auto 8px" }} />
                <p style={{ fontSize: 13, color: "#737373", margin: 0 }}>Nenhuma credencial configurada. Configure o ClickMassa para usar os agentes.</p>
              </div>
            ) : credentials.map(cred => (
              <div key={cred.mcp_id} style={{ background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "white", fontFamily: "Outfit, sans-serif" }}>{MCP_LABELS[cred.mcp_id] || cred.mcp_id}</div>
                  <div style={{ fontSize: 12, color: "#737373" }}>{Object.keys(cred.data_masked || {}).join(", ")}</div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    onClick={() => setSelectedCred(cred.mcp_id)}
                    style={{ padding: "6px 12px", background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", cursor: "pointer", fontSize: 12, transition: "all 0.2s" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
                  >
                    Editar
                  </button>
                  <button
                    onClick={() => deleteCred(cred.mcp_id)}
                    style={{ width: 30, height: 30, background: "transparent", border: "1px solid #27272A", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#A3A3A3", transition: "all 0.2s" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.1)"; e.currentTarget.style.borderColor = "rgba(239,68,68,0.3)"; e.currentTarget.style.color = "#EF4444"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}

            {/* Add ClickMassa Credential Form */}
            <CredentialForm mcp_id="clickmassa" fields={CRED_FIELDS.clickmassa} onSaved={(mcpId) => { axios.get(`${API}/credentials`, { withCredentials: true }).then(r => setCredentials(r.data.credentials || [])); }} />
          </div>
        </Section>
      </div>

      {/* Quick credential edit from list */}
      {selectedCred && (
        <CredentialModal
          mcp_id={selectedCred}
          fields={CRED_FIELDS[selectedCred] || []}
          onClose={() => { setSelectedCred(null); axios.get(`${API}/credentials`, { withCredentials: true }).then(r => setCredentials(r.data.credentials || [])); }}
        />
      )}
    </Layout>
  );
}

function CredentialForm({ mcp_id, fields, onSaved }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await axios.post(`${API}/credentials`, { mcp_id, data: formData }, { withCredentials: true });
      setSaved(true);
      onSaved(mcp_id);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  if (!fields.length) return null;

  return (
    <div style={{ background: "rgba(249,115,22,0.05)", border: "1px dashed rgba(249,115,22,0.2)", borderRadius: 10, padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#F97316", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.1em" }}>
        Configurar ClickMassa CRM
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {fields.map(f => (
          <div key={f.key}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 500, color: "#A3A3A3", marginBottom: 5 }}>{f.label}</label>
            <input
              data-testid={`settings-${f.key}`}
              type={f.type}
              placeholder={f.placeholder}
              value={formData[f.key] || ""}
              onChange={e => setFormData(d => ({ ...d, [f.key]: e.target.value }))}
              style={{ width: "100%", padding: "9px 12px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
              onFocus={e => e.target.style.borderColor = "#F97316"}
              onBlur={e => e.target.style.borderColor = "#27272A"}
            />
          </div>
        ))}
        {error && <div style={{ color: "#EF4444", fontSize: 12 }}>{error}</div>}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={handleSave}
            data-testid="save-clickmassa-creds"
            disabled={saving}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", background: "#F97316", color: "white", border: "none", borderRadius: 7, cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 13, transition: "all 0.2s" }}
          >
            {saving ? <RefreshCw size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Shield size={13} />}
            Salvar credenciais
          </button>
          {saved && <span style={{ fontSize: 12, color: "#10B981", display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={13} /> Salvo!</span>}
        </div>
      </div>
    </div>
  );
}

function CredentialModal({ mcp_id, fields, onClose }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/credentials`, { mcp_id, data: formData }, { withCredentials: true });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 20 }} onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, padding: 28, width: "100%", maxWidth: 440 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 18, fontWeight: 700, color: "white", marginBottom: 20 }}>Editar credenciais</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
          {fields.map(f => (
            <div key={f.key}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 5 }}>{f.label}</label>
              <input
                type={f.type}
                placeholder={f.placeholder}
                value={formData[f.key] || ""}
                onChange={e => setFormData(d => ({ ...d, [f.key]: e.target.value }))}
                style={{ width: "100%", padding: "9px 12px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 7, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
              />
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose} style={{ flex: 1, padding: "10px", background: "#2A2A2A", color: "#A3A3A3", border: "1px solid #27272A", borderRadius: 8, cursor: "pointer", fontSize: 14, fontFamily: "Outfit, sans-serif", fontWeight: 600 }}>Cancelar</button>
          <button onClick={handleSave} disabled={saving} style={{ flex: 2, padding: "10px", background: "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 14, fontFamily: "Outfit, sans-serif", fontWeight: 700 }}>
            {saving ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// RefreshCw imported from lucide-react above

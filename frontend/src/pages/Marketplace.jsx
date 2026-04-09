import React, { useEffect, useState } from "react";
import { Search, Store, Star, Download, Lock, CheckCircle, ExternalLink, Zap } from "lucide-react";
import axios from "axios";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const ICON_MAP = {
  database: "🗄️", search: "🔍", globe: "🌐", "message-circle": "💬",
  calendar: "📅", mail: "✉️", zap: "⚡", send: "📤", "credit-card": "💳",
  github: "🐙", hash: "#", bot: "🤖",
};

function MCPCard({ mcp, isInstalled, onInstall }) {
  const statusLabels = { active: "Ativo", coming_soon: "Em breve" };
  return (
    <div
      data-testid={`mcp-card-${mcp.id}`}
      style={{ background: "#1A1A1A", border: `1px solid ${isInstalled ? "rgba(249,115,22,0.3)" : "#27272A"}`, borderRadius: 12, padding: 20, display: "flex", flexDirection: "column", gap: 14, transition: "all 0.2s", position: "relative" }}
      onMouseEnter={e => { if (!isInstalled) e.currentTarget.style.borderColor = "rgba(249,115,22,0.25)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
      onMouseLeave={e => { if (!isInstalled) e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.transform = ""; }}
    >
      {isInstalled && (
        <div style={{ position: "absolute", top: 12, right: 12, background: "rgba(249,115,22,0.15)", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 100, padding: "2px 8px", fontSize: 10, fontWeight: 700, color: "#F97316" }}>
          INSTALADO
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div style={{ width: 46, height: 46, background: `${mcp.color}15`, border: `1px solid ${mcp.color}30`, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, flexShrink: 0 }}>
          {ICON_MAP[mcp.icon] || "🔧"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 15, color: "white" }}>{mcp.name}</span>
            <span style={{ fontSize: 10, color: mcp.status === "active" ? "#10B981" : "#F97316", background: mcp.status === "active" ? "rgba(16,185,129,0.1)" : "rgba(249,115,22,0.1)", border: `1px solid ${mcp.status === "active" ? "rgba(16,185,129,0.2)" : "rgba(249,115,22,0.2)"}`, borderRadius: 100, padding: "1px 7px", fontWeight: 600 }}>
              {statusLabels[mcp.status] || mcp.status}
            </span>
          </div>
          <p style={{ fontSize: 12, color: "#737373", lineHeight: 1.5, margin: 0 }}>{mcp.description}</p>
        </div>
      </div>

      {/* Tools list (collapsed) */}
      {mcp.tools?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {mcp.tools.slice(0, 4).map(t => (
            <span key={t.name} style={{ fontSize: 10, color: "#A3A3A3", background: "#2A2A2A", borderRadius: 4, padding: "2px 6px", fontFamily: "JetBrains Mono, monospace" }}>{t.name}</span>
          ))}
          {mcp.tools.length > 4 && <span style={{ fontSize: 10, color: "#737373", padding: "2px 0" }}>+{mcp.tools.length - 4} mais</span>}
        </div>
      )}

      {/* Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid #27272A" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {mcp.rating > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Star size={12} fill="#F59E0B" color="#F59E0B" />
              <span style={{ fontSize: 12, color: "#A3A3A3" }}>{mcp.rating}</span>
            </div>
          )}
          {mcp.installs > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Download size={12} color="#737373" />
              <span style={{ fontSize: 12, color: "#737373" }}>{mcp.installs.toLocaleString()}</span>
            </div>
          )}
          {mcp.credentials_required?.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Lock size={12} color="#737373" />
              <span style={{ fontSize: 12, color: "#737373" }}>{mcp.credentials_required.length} credencial{mcp.credentials_required.length !== 1 ? "s" : ""}</span>
            </div>
          )}
        </div>

        {mcp.status === "active" ? (
          <button
            onClick={() => onInstall(mcp)}
            data-testid={`install-${mcp.id}`}
            style={{ padding: "6px 14px", background: isInstalled ? "rgba(16,185,129,0.1)" : "rgba(249,115,22,0.1)", color: isInstalled ? "#10B981" : "#F97316", border: `1px solid ${isInstalled ? "rgba(16,185,129,0.3)" : "rgba(249,115,22,0.3)"}`, borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5, transition: "all 0.2s", fontFamily: "Outfit, sans-serif" }}
            onMouseEnter={e => { if (!isInstalled) { e.currentTarget.style.background = "rgba(249,115,22,0.2)"; } }}
            onMouseLeave={e => { if (!isInstalled) { e.currentTarget.style.background = "rgba(249,115,22,0.1)"; } }}
          >
            {isInstalled ? <><CheckCircle size={12} /> Configurar</> : <><Zap size={12} /> Instalar</>}
          </button>
        ) : (
          <span style={{ fontSize: 12, color: "#737373", fontStyle: "italic" }}>Em breve</span>
        )}
      </div>
    </div>
  );
}

export default function Marketplace() {
  const [mcps, setMcps] = useState([]);
  const [categories, setCategories] = useState([]);
  const [installed, setInstalled] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedMcp, setSelectedMcp] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    const [mktRes, credRes] = await Promise.all([
      axios.get(`${API}/marketplace?category=${activeCategory}&search=${search}`).catch(() => ({ data: { mcps: [], categories: [] } })),
      axios.get(`${API}/credentials`, { withCredentials: true }).catch(() => ({ data: { credentials: [] } })),
    ]);
    setMcps(mktRes.data.mcps || []);
    setCategories(mktRes.data.categories || []);
    setInstalled((credRes.data.credentials || []).map(c => c.mcp_id));
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [activeCategory]);

  const handleSearch = (e) => {
    if (e.key === "Enter") fetchData();
  };

  const handleInstall = (mcp) => setSelectedMcp(mcp);

  return (
    <Layout>
      <div style={{ animation: "fadeIn 0.3s ease-out" }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 28, color: "white", letterSpacing: "-0.03em", marginBottom: 6 }}>MCP Marketplace</h1>
          <p style={{ fontSize: 14, color: "#737373" }}>Descubra e instale ferramentas para potencializar seus agentes de IA</p>
        </div>

        {/* Search */}
        <div style={{ position: "relative", marginBottom: 20 }}>
          <Search size={16} style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#737373" }} />
          <input
            data-testid="marketplace-search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={handleSearch}
            placeholder="Buscar MCPs e ferramentas..."
            style={{ width: "100%", padding: "11px 14px 11px 42px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box", transition: "border-color 0.2s" }}
            onFocus={e => e.target.style.borderColor = "#F97316"}
            onBlur={e => e.target.style.borderColor = "#27272A"}
          />
        </div>

        {/* Categories */}
        <div style={{ display: "flex", gap: 8, marginBottom: 24, flexWrap: "wrap" }}>
          {categories.map(cat => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              data-testid={`category-${cat.id}`}
              style={{ padding: "6px 14px", borderRadius: 100, border: "1px solid", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: "Outfit, sans-serif", transition: "all 0.2s", background: activeCategory === cat.id ? "#F97316" : "transparent", borderColor: activeCategory === cat.id ? "#F97316" : "#27272A", color: activeCategory === cat.id ? "white" : "#A3A3A3" }}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Grid */}
        {loading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
            {[1, 2, 3, 4].map(i => <div key={i} style={{ height: 200, background: "#1A1A1A", borderRadius: 12, border: "1px solid #27272A" }} />)}
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
            {mcps.map(mcp => (
              <MCPCard key={mcp.id} mcp={mcp} isInstalled={installed.includes(mcp.id)} onInstall={handleInstall} />
            ))}
          </div>
        )}

        {/* Install Modal */}
        {selectedMcp && (
          <InstallModal mcp={selectedMcp} onClose={() => { setSelectedMcp(null); fetchData(); }} />
        )}
      </div>
    </Layout>
  );
}

function InstallModal({ mcp, onClose }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await axios.post(`${API}/credentials`, { mcp_id: mcp.id, data: formData }, { withCredentials: true });
      setSaved(true);
      setTimeout(onClose, 1200);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao salvar credenciais");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 20 }} onClick={onClose}>
      <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 16, padding: 28, width: "100%", maxWidth: 460, animation: "fadeIn 0.2s ease-out" }} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 20, color: "white", marginBottom: 6 }}>Instalar {mcp.name}</h3>
        <p style={{ fontSize: 13, color: "#737373", marginBottom: 24 }}>Configure as credenciais necessárias para este MCP</p>

        {mcp.credentials_required?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 24 }}>
            {mcp.credentials_required.map(field => (
              <div key={field}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#A3A3A3", marginBottom: 6, textTransform: "capitalize" }}>{field.replace(/_/g, " ")}</label>
                <input
                  data-testid={`cred-${field}`}
                  type={field.toLowerCase().includes("password") || field.toLowerCase().includes("key") || field.toLowerCase().includes("token") ? "password" : "text"}
                  placeholder={`Digite ${field.replace(/_/g, " ")}`}
                  value={formData[field] || ""}
                  onChange={e => setFormData(d => ({ ...d, [field]: e.target.value }))}
                  style={{ width: "100%", padding: "10px 14px", background: "#2A2A2A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box" }}
                  onFocus={e => e.target.style.borderColor = "#F97316"}
                  onBlur={e => e.target.style.borderColor = "#27272A"}
                />
              </div>
            ))}
          </div>
        ) : (
          <div style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 8, padding: 14, marginBottom: 24, fontSize: 13, color: "#10B981" }}>
            Este MCP não requer credenciais adicionais.
          </div>
        )}

        {error && <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, color: "#EF4444", fontSize: 12 }}>{error}</div>}

        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose} style={{ flex: 1, padding: "10px", background: "#2A2A2A", color: "#A3A3A3", border: "1px solid #27272A", borderRadius: 8, cursor: "pointer", fontSize: 14, fontFamily: "Outfit, sans-serif", fontWeight: 600 }}>Cancelar</button>
          <button
            onClick={handleSave}
            data-testid="save-credentials-btn"
            disabled={saving || saved}
            style={{ flex: 2, padding: "10px", background: saved ? "#10B981" : "#F97316", color: "white", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 14, fontFamily: "Outfit, sans-serif", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
          >
            {saved ? <><CheckCircle size={16} /> Salvo!</> : saving ? "Salvando..." : "Salvar e Instalar"}
          </button>
        </div>
      </div>
    </div>
  );
}

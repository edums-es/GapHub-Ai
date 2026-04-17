import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  MessageSquare, Target, Repeat, Calendar, UserCheck,
  Search, Globe, Check, Loader2,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// Map da string 'icon' vinda do backend → componente lucide.
// Mantém compat com novos packs cadastrados sem precisar atualizar o frontend:
// icons não mapeados caem no fallback Search.
const ICON_MAP = {
  "message-square": MessageSquare,
  "target": Target,
  "repeat": Repeat,
  "calendar": Calendar,
  "user-check": UserCheck,
  "search": Search,
  "globe": Globe,
};

/**
 * SkillPackSelector — UI para habilitar/desabilitar skill packs por agente.
 *
 * Props:
 *   agentId (string)        — se presente, salva no backend via PUT /agents/:id/skill-packs
 *   initialEnabled (string[])— lista inicial de packs habilitados (vem do agente)
 *   onChange (fn)           — callback(enabledIds) para o pai sincronizar estado local
 *   disabled (bool)         — se true, desabilita toda interação (ex: agente ainda não salvo)
 */
export default function SkillPackSelector({ agentId, initialEnabled = [], onChange, disabled = false }) {
  const [packs, setPacks] = useState([]);
  const [enabled, setEnabled] = useState(new Set(initialEnabled));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [error, setError] = useState(null);

  // Carrega catálogo público de skill packs
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/skill-packs`, { withCredentials: true })
      .then(r => { if (!cancelled) setPacks(r.data.packs || []); })
      .catch(e => { if (!cancelled) setError(e.response?.data?.detail || "Erro ao carregar skill packs"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Sincroniza com props externos quando o agente é carregado/recarregado
  useEffect(() => {
    setEnabled(new Set(initialEnabled || []));
  }, [initialEnabled?.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  const byCategory = useMemo(() => {
    const groups = {};
    for (const p of packs) {
      const cat = p.category || "outros";
      groups[cat] = groups[cat] || [];
      groups[cat].push(p);
    }
    return groups;
  }, [packs]);

  const togglePack = async (packId) => {
    if (disabled || saving) return;
    const newSet = new Set(enabled);
    if (newSet.has(packId)) newSet.delete(packId);
    else newSet.add(packId);

    setEnabled(newSet);
    onChange && onChange(Array.from(newSet));

    // Persiste se tivermos um agentId (agente já salvo)
    if (agentId) {
      setSaving(true);
      try {
        await axios.put(
          `${API}/agents/${agentId}/skill-packs`,
          { enabled_skill_packs: Array.from(newSet) },
          { withCredentials: true }
        );
        setError(null);
      } catch (e) {
        setError(e.response?.data?.detail || "Erro ao salvar skill pack");
        // Reverte em caso de falha
        setEnabled(enabled);
        onChange && onChange(Array.from(enabled));
      } finally {
        setSaving(false);
      }
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "12px 10px", color: "#737373", fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
        <Loader2 size={12} className="spin" /> Carregando skills…
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 8px 0", borderTop: "1px solid #27272A", marginTop: 6 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 2px 6px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "#737373", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Skill Packs
        </div>
        {saving && <Loader2 size={10} color="#F97316" className="spin" />}
      </div>

      {disabled && (
        <div style={{ fontSize: 9, color: "#737373", padding: "0 2px 6px", lineHeight: 1.4 }}>
          Salve o agente primeiro para habilitar skill packs.
        </div>
      )}
      {error && (
        <div style={{
          fontSize: 9, color: "#EF4444", background: "rgba(239,68,68,0.08)",
          border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, padding: "4px 6px",
          marginBottom: 6,
        }}>{error}</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {packs.map(pack => {
          const Icon = ICON_MAP[pack.icon] || Search;
          const on = enabled.has(pack.id);
          const isExpanded = expanded === pack.id;

          return (
            <div key={pack.id} style={{
              background: on ? `${pack.color}18` : "#2A2A2A",
              border: `1px solid ${on ? `${pack.color}60` : "#27272A"}`,
              borderRadius: 8,
              overflow: "hidden",
              transition: "all 0.15s",
              opacity: disabled ? 0.5 : 1,
            }}>
              <div
                onClick={() => togglePack(pack.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 7,
                  padding: "7px 9px",
                  cursor: disabled ? "not-allowed" : "pointer",
                  color: "white",
                  fontSize: 11, fontFamily: "IBM Plex Sans, sans-serif",
                }}
                data-testid={`skill-pack-${pack.id}`}
              >
                <div style={{
                  width: 22, height: 22, background: `${pack.color}20`,
                  borderRadius: 5, display: "flex", alignItems: "center",
                  justifyContent: "center", flexShrink: 0,
                }}>
                  <Icon size={12} color={pack.color} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 600,
                    overflow: "hidden", textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    display: "flex", alignItems: "center", gap: 4,
                  }}>
                    {pack.name}
                    {pack.recommended && (
                      <span style={{
                        fontSize: 8, fontWeight: 700, color: "#F97316",
                        background: "rgba(249,115,22,0.15)",
                        border: "1px solid rgba(249,115,22,0.3)",
                        padding: "1px 4px", borderRadius: 3,
                        textTransform: "uppercase", letterSpacing: "0.05em",
                      }}>Rec</span>
                    )}
                  </div>
                  <div style={{ fontSize: 9, color: "#A3A3A3", marginTop: 1 }}>
                    {pack.tools?.length || 0} tools
                  </div>
                </div>
                <div style={{
                  width: 16, height: 16, borderRadius: 4,
                  background: on ? pack.color : "transparent",
                  border: `1.5px solid ${on ? pack.color : "#404040"}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  {on && <Check size={10} color="white" strokeWidth={3} />}
                </div>
              </div>

              <div
                onClick={(e) => { e.stopPropagation(); setExpanded(isExpanded ? null : pack.id); }}
                style={{
                  padding: "4px 9px",
                  borderTop: `1px solid ${on ? `${pack.color}30` : "#27272A"}`,
                  fontSize: 9, color: "#737373",
                  cursor: "pointer", userSelect: "none",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}
              >
                <span>{isExpanded ? "Ocultar detalhes" : "Ver detalhes"}</span>
                <span>{isExpanded ? "−" : "+"}</span>
              </div>

              {isExpanded && (
                <div style={{ padding: "6px 9px 8px", background: "#0A0A0A" }}>
                  <div style={{ fontSize: 10, color: "#D4D4D8", lineHeight: 1.5, marginBottom: 6 }}>
                    {pack.description}
                  </div>
                  <div style={{ fontSize: 9, color: "#737373", marginBottom: 3, fontWeight: 600 }}>
                    Tools incluídas:
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {(pack.tools || []).map(t => (
                      <span key={t} style={{
                        fontSize: 9, fontFamily: "IBM Plex Mono, monospace",
                        background: "#1A1A1A", border: "1px solid #27272A",
                        padding: "2px 5px", borderRadius: 4, color: "#A3A3A3",
                      }}>{t}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {Object.keys(byCategory).length === 0 && !loading && (
        <div style={{ fontSize: 10, color: "#737373", padding: "6px 2px" }}>
          Nenhum skill pack disponível.
        </div>
      )}

      <style>{`.spin{animation:spin 0.8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

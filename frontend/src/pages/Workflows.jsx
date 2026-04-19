import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Plus, Workflow as WorkflowIcon, Trash2, Sparkles, Edit, ArrowRight, Zap, FileText } from "lucide-react";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const TEMPLATE_ICONS = {
  atendimento_whatsapp: "💬",
  qualificacao_lead: "🎯",
  faq_inteligente: "📚",
};

export default function Workflows() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showTemplates, setShowTemplates] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setLoading(true);
      const [wfRes, tplRes] = await Promise.all([
        axios.get(`${API}/workflows`, { withCredentials: true }),
        axios.get(`${API}/workflow-templates`, { withCredentials: true }),
      ]);
      setWorkflows(wfRes.data?.workflows || []);
      setTemplates(tplRes.data?.templates || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao carregar workflows");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const createBlank = async () => {
    try {
      const { data } = await axios.post(
        `${API}/workflows`,
        {
          name: "Novo Workflow",
          description: "",
          trigger_type: "webhook",
          nodes: [
            { id: "trigger", type: "trigger", label: "Início", position: { x: 0, y: 0 }, config: {}, next: "end" },
            { id: "end", type: "end", label: "Fim", position: { x: 0, y: 0 }, config: {} },
          ],
        },
        { withCredentials: true },
      );
      navigate(`/workflows/${data.workflow_id}`);
    } catch (e) {
      alert(e.response?.data?.detail?.message || e.response?.data?.detail || "Erro ao criar workflow");
    }
  };

  const createFromTemplate = async (templateId) => {
    try {
      const { data } = await axios.post(
        `${API}/workflows/from-template/${templateId}`,
        {},
        { withCredentials: true },
      );
      navigate(`/workflows/${data.workflow_id}`);
    } catch (e) {
      alert(e.response?.data?.detail || "Erro ao criar workflow do template");
    }
  };

  const deleteWorkflow = async (id) => {
    if (!window.confirm("Excluir este workflow? Os agentes ligados a ele voltarão ao modo prompt.")) return;
    try {
      await axios.delete(`${API}/workflows/${id}`, { withCredentials: true });
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Erro ao excluir");
    }
  };

  return (
    <Layout>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
          <div>
            <h1 style={{ fontFamily: "Outfit, sans-serif", fontSize: 30, fontWeight: 800, color: "white", marginBottom: 6, letterSpacing: "-0.02em" }}>
              Workflows
            </h1>
            <p style={{ color: "#A3A3A3", fontSize: 14, maxWidth: 640, lineHeight: 1.55 }}>
              Monte fluxos de atendimento visuais — o agente segue passo a passo, sem improviso. Classifica a mensagem,
              usa ferramentas do CRM e responde com precisão.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={() => setShowTemplates(true)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 16px", background: "transparent",
                border: "1px solid rgba(249, 115, 22, 0.4)", borderRadius: 8,
                color: "#F97316", fontSize: 14, fontWeight: 600, cursor: "pointer",
                fontFamily: "Outfit, sans-serif",
              }}
            >
              <Sparkles size={16} /> Usar Template
            </button>
            <button
              onClick={createBlank}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 16px",
                background: "linear-gradient(135deg, #F97316, #EA580C)",
                border: "none", borderRadius: 8,
                color: "white", fontSize: 14, fontWeight: 600, cursor: "pointer",
                fontFamily: "Outfit, sans-serif",
                boxShadow: "0 4px 14px rgba(249, 115, 22, 0.3)",
              }}
            >
              <Plus size={16} /> Novo Workflow
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: 14, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, color: "#F87171", marginBottom: 20, fontSize: 13 }}>
            {error}
          </div>
        )}

        {/* List */}
        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: "#737373" }}>Carregando...</div>
        ) : workflows.length === 0 ? (
          <EmptyState onCreate={createBlank} onTemplate={() => setShowTemplates(true)} />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {workflows.map(wf => (
              <WorkflowCard
                key={wf.workflow_id}
                workflow={wf}
                onOpen={() => navigate(`/workflows/${wf.workflow_id}`)}
                onDelete={() => deleteWorkflow(wf.workflow_id)}
              />
            ))}
          </div>
        )}

        {/* Templates drawer */}
        {showTemplates && (
          <TemplatesDrawer
            templates={templates}
            onClose={() => setShowTemplates(false)}
            onPick={(id) => { setShowTemplates(false); createFromTemplate(id); }}
          />
        )}
      </div>
    </Layout>
  );
}

function EmptyState({ onCreate, onTemplate }) {
  return (
    <div style={{
      padding: 60, textAlign: "center", borderRadius: 14,
      background: "#121212", border: "1px dashed #27272A",
    }}>
      <div style={{ width: 64, height: 64, borderRadius: 16, margin: "0 auto 20px",
        background: "rgba(249,115,22,0.12)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <WorkflowIcon size={32} color="#F97316" />
      </div>
      <h3 style={{ fontFamily: "Outfit, sans-serif", fontSize: 20, fontWeight: 700, color: "white", marginBottom: 8 }}>
        Nenhum workflow ainda
      </h3>
      <p style={{ color: "#A3A3A3", fontSize: 14, marginBottom: 24, maxWidth: 440, margin: "0 auto 24px", lineHeight: 1.55 }}>
        Comece de um template pronto ou crie um workflow do zero. Você define os passos — o agente segue exatamente,
        sem sair do roteiro.
      </p>
      <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
        <button
          onClick={onTemplate}
          style={{
            padding: "10px 16px", background: "transparent",
            border: "1px solid rgba(249, 115, 22, 0.4)", borderRadius: 8,
            color: "#F97316", fontSize: 14, fontWeight: 600, cursor: "pointer",
            fontFamily: "Outfit, sans-serif",
            display: "flex", alignItems: "center", gap: 8,
          }}
        >
          <Sparkles size={16} /> Ver Templates
        </button>
        <button
          onClick={onCreate}
          style={{
            padding: "10px 16px",
            background: "linear-gradient(135deg, #F97316, #EA580C)",
            border: "none", borderRadius: 8,
            color: "white", fontSize: 14, fontWeight: 600, cursor: "pointer",
            fontFamily: "Outfit, sans-serif",
            display: "flex", alignItems: "center", gap: 8,
          }}
        >
          <Plus size={16} /> Criar do Zero
        </button>
      </div>
    </div>
  );
}

function WorkflowCard({ workflow, onOpen, onDelete }) {
  const nodeCount = (workflow.nodes || []).length;
  return (
    <div
      style={{
        background: "#121212", border: "1px solid #27272A", borderRadius: 12,
        padding: 18, cursor: "pointer", transition: "all 0.2s",
        display: "flex", flexDirection: "column", minHeight: 160,
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.transform = "translateY(0)"; }}
      onClick={onOpen}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: "rgba(249,115,22,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <WorkflowIcon size={18} color="#F97316" />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "white", fontSize: 15, fontWeight: 700, fontFamily: "Outfit, sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {workflow.name || "Sem nome"}
          </div>
          <div style={{ color: "#737373", fontSize: 11, marginTop: 2 }}>
            {nodeCount} passo{nodeCount !== 1 ? "s" : ""} · gatilho: {workflow.trigger_type || "webhook"}
          </div>
        </div>
      </div>
      <p style={{ color: "#A3A3A3", fontSize: 13, lineHeight: 1.5, flex: 1, margin: "4px 0 14px",
        display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {workflow.description || "Sem descrição"}
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ color: "#F97316", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
          Abrir editor <ArrowRight size={12} />
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          style={{ background: "transparent", border: "none", color: "#737373", cursor: "pointer", padding: 4, borderRadius: 4 }}
          onMouseEnter={e => { e.currentTarget.style.color = "#EF4444"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "#737373"; }}
          title="Excluir"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

function TemplatesDrawer({ templates, onClose, onPick }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: 780, width: "100%", maxHeight: "85vh", overflowY: "auto",
          background: "#0F0F0F", border: "1px solid #27272A", borderRadius: 14, padding: 24,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
          <div>
            <h2 style={{ fontFamily: "Outfit, sans-serif", fontSize: 22, fontWeight: 800, color: "white", marginBottom: 4 }}>
              Templates prontos
            </h2>
            <p style={{ color: "#A3A3A3", fontSize: 13 }}>
              Fluxos testados para cenários comuns. Clique para usar como ponto de partida.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#737373", cursor: "pointer", fontSize: 20 }}
          >
            ×
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
          {templates.map(t => (
            <div
              key={t.template_id}
              onClick={() => onPick(t.template_id)}
              style={{
                background: "#121212", border: "1px solid #27272A", borderRadius: 10,
                padding: 14, cursor: "pointer", transition: "all 0.2s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>{TEMPLATE_ICONS[t.template_id] || "⚡"}</div>
              <div style={{ color: "white", fontWeight: 700, fontSize: 14, fontFamily: "Outfit, sans-serif", marginBottom: 4 }}>
                {t.name}
              </div>
              <div style={{ color: "#A3A3A3", fontSize: 12, lineHeight: 1.5, marginBottom: 10 }}>
                {t.description}
              </div>
              <div style={{ color: "#737373", fontSize: 11 }}>
                {t.node_count} passos
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

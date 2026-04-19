import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, Save, Play, Plus, Trash2, Zap, GitBranch, Brain, MessageSquare,
  Wrench, Variable, Flag, CheckCircle2, ChevronDown, ChevronUp, AlertTriangle,
  X, Info, Sparkles,
} from "lucide-react";
import Layout from "@/components/Layout";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

/* ─────────────────────────────────────────────────────────────────
 * Definição amigável dos tipos de nó. O backend (workflow_engine.py)
 * também conhece esses tipos. Se adicionar um tipo novo aqui,
 * adicione em NODE_TYPES no backend também.
 * ───────────────────────────────────────────────────────────────── */
const NODE_CATALOG = [
  {
    type: "trigger",
    label: "Início (Gatilho)",
    short: "Início",
    description: "Ponto de entrada do workflow. Executa quando uma mensagem chega.",
    icon: Flag,
    color: "#F97316",
    unique: true,      // só pode existir um
  },
  {
    type: "set_variable",
    label: "Definir Variável",
    short: "Variável",
    description: "Guarda valores fixos que serão usados nos passos seguintes.",
    icon: Variable,
    color: "#8B5CF6",
  },
  {
    type: "classify_intent",
    label: "Classificar Intenção",
    short: "Classificar",
    description: "Usa IA para entender o que o lead quer (agendar, tirar dúvida, etc).",
    icon: Brain,
    color: "#3B82F6",
  },
  {
    type: "branch",
    label: "Desvio (Se / Então)",
    short: "Desvio",
    description: "Manda o fluxo para um caminho diferente baseado numa variável.",
    icon: GitBranch,
    color: "#F59E0B",
  },
  {
    type: "tool_call",
    label: "Executar Ação (MCP)",
    short: "Ação",
    description: "Chama uma ferramenta do CRM — criar contato, abrir ticket, etc.",
    icon: Wrench,
    color: "#10B981",
  },
  {
    type: "llm_reply",
    label: "Gerar Resposta com IA",
    short: "Resposta IA",
    description: "Usa a IA para escrever uma resposta personalizada para o lead.",
    icon: Brain,
    color: "#EC4899",
  },
  {
    type: "send_message",
    label: "Enviar Mensagem",
    short: "Enviar",
    description: "Manda a resposta final pelo WhatsApp, aparece como empresa no CRM.",
    icon: MessageSquare,
    color: "#14B8A6",
  },
  {
    type: "end",
    label: "Fim",
    short: "Fim",
    description: "Encerra o workflow.",
    icon: CheckCircle2,
    color: "#737373",
  },
];

const nodeCatalogEntry = (type) => NODE_CATALOG.find(n => n.type === type) || NODE_CATALOG[NODE_CATALOG.length - 1];

const CLICKMASSA_TOOLS = [
  { name: "buscar_contato_por_numero", label: "Buscar contato por número" },
  { name: "criar_contato",             label: "Criar contato" },
  { name: "atualizar_contato",         label: "Atualizar contato" },
  { name: "listar_tickets_pendentes",  label: "Listar tickets pendentes" },
  { name: "criar_tarefa",              label: "Criar tarefa" },
  { name: "fechar_ticket",             label: "Fechar ticket" },
  { name: "enviar_mensagem",           label: "Enviar mensagem (Push)" },
];

/* ────────────────────────────────────────────────────────────────── */

export default function WorkflowBuilder() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromAgent = searchParams.get("from") === "agent";
  const fromAgentId = searchParams.get("agentId") || "";

  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);
  const [showTestRun, setShowTestRun] = useState(false);
  const [showPalette, setShowPalette] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await axios.get(`${API}/workflows/${workflowId}`, { withCredentials: true });
      setWorkflow(data);
      // Auto-select trigger node at start
      const trig = (data.nodes || []).find(n => n.type === "trigger");
      if (trig) setSelectedNodeId(trig.id);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao carregar workflow");
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!workflow) return;
    try {
      setSaving(true);
      const { data } = await axios.put(
        `${API}/workflows/${workflowId}`,
        {
          name: workflow.name,
          description: workflow.description || "",
          trigger_type: workflow.trigger_type || "webhook",
          nodes: workflow.nodes || [],
        },
        { withCredentials: true },
      );
      setWorkflow(data);
      setValidationErrors(data.validation_errors || []);
    } catch (e) {
      alert(e.response?.data?.detail?.message || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const updateMeta = (patch) => setWorkflow(w => ({ ...w, ...patch }));

  const updateNode = (nodeId, patch) => {
    setWorkflow(w => ({
      ...w,
      nodes: (w.nodes || []).map(n => n.id === nodeId ? { ...n, ...patch } : n),
    }));
  };

  const updateNodeConfig = (nodeId, configPatch) => {
    setWorkflow(w => ({
      ...w,
      nodes: (w.nodes || []).map(n => n.id === nodeId
        ? { ...n, config: { ...(n.config || {}), ...configPatch } }
        : n),
    }));
  };

  const addNode = (type, afterNodeId = null) => {
    const cat = nodeCatalogEntry(type);
    if (cat.unique && (workflow.nodes || []).some(n => n.type === type)) {
      alert(`Só pode existir um nó do tipo "${cat.label}".`);
      return;
    }
    const id = `n_${Math.random().toString(36).slice(2, 8)}`;
    const newNode = {
      id,
      type,
      label: cat.short,
      position: { x: 0, y: 0 },
      config: defaultConfig(type),
      next: null,
    };

    setWorkflow(w => {
      let nodes = [...(w.nodes || [])];
      if (afterNodeId) {
        const idx = nodes.findIndex(n => n.id === afterNodeId);
        if (idx >= 0) {
          const prev = nodes[idx];
          // Link: prev → newNode → (prev.next)
          newNode.next = prev.next;
          nodes[idx] = { ...prev, next: id };
          nodes.splice(idx + 1, 0, newNode);
        } else {
          nodes.push(newNode);
        }
      } else {
        nodes.push(newNode);
      }
      return { ...w, nodes };
    });
    setSelectedNodeId(id);
    setShowPalette(false);
  };

  const deleteNode = (nodeId) => {
    if (!window.confirm("Excluir este passo?")) return;
    setWorkflow(w => {
      const node = (w.nodes || []).find(n => n.id === nodeId);
      if (!node) return w;
      if (node.type === "trigger") {
        alert("Não é possível excluir o nó de Início.");
        return w;
      }
      const newNext = node.next;
      // Redirect all incoming references
      const nodes = (w.nodes || [])
        .filter(n => n.id !== nodeId)
        .map(n => {
          let patched = { ...n };
          if (patched.next === nodeId) patched.next = newNext;
          if (patched.type === "branch") {
            const cfg = { ...(patched.config || {}) };
            cfg.cases = (cfg.cases || []).map(c => c.to === nodeId ? { ...c, to: newNext } : c);
            if (cfg.default === nodeId) cfg.default = newNext;
            patched.config = cfg;
          }
          return patched;
        });
      return { ...w, nodes };
    });
    if (selectedNodeId === nodeId) setSelectedNodeId(null);
  };

  const selectedNode = (workflow?.nodes || []).find(n => n.id === selectedNodeId);

  // Cada nó da lista, em ordem de execução (segue o ponteiro `next`).
  const orderedNodes = useMemo(() => {
    if (!workflow?.nodes) return [];
    const byId = Object.fromEntries(workflow.nodes.map(n => [n.id, n]));
    const trigger = workflow.nodes.find(n => n.type === "trigger") || workflow.nodes[0];
    const result = [];
    const visited = new Set();
    let cur = trigger;
    while (cur && !visited.has(cur.id)) {
      visited.add(cur.id);
      result.push(cur);
      if (cur.type === "branch") {
        // Só mostra na linha principal o "default" — os demais ramos aparecem como sublistas depois.
        cur = cur.config?.default ? byId[cur.config.default] : null;
      } else if (cur.type === "end") {
        break;
      } else {
        cur = cur.next ? byId[cur.next] : null;
      }
    }
    // Anexa nós órfãos no fim (para não perder referência)
    const orphan = workflow.nodes.filter(n => !visited.has(n.id));
    return [...result, ...orphan];
  }, [workflow]);

  if (loading) return <Layout><div style={{ padding: 40, color: "#737373" }}>Carregando...</div></Layout>;
  if (error)   return <Layout><div style={{ padding: 40, color: "#EF4444" }}>{error}</div></Layout>;
  if (!workflow) return <Layout><div style={{ padding: 40, color: "#737373" }}>Workflow não encontrado.</div></Layout>;

  return (
    <Layout>
      <div style={{ maxWidth: 1400, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Topo */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 4 }}>
          <button
            onClick={() => {
              if (fromAgent && fromAgentId) navigate(`/agents/${fromAgentId}`);
              else navigate("/agents");
            }}
            style={{
              background: fromAgent ? "rgba(249,115,22,0.1)" : "transparent",
              border: `1px solid ${fromAgent ? "rgba(249,115,22,0.3)" : "#27272A"}`,
              borderRadius: 8, color: fromAgent ? "#F97316" : "#A3A3A3",
              padding: "8px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
              fontSize: 13, fontWeight: 600,
            }}
          >
            <ArrowLeft size={14} /> {fromAgent ? "Voltar ao agente" : "Voltar aos agentes"}
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <input
              value={workflow.name || ""}
              onChange={(e) => updateMeta({ name: e.target.value })}
              placeholder="Nome do workflow"
              style={{
                background: "transparent", border: "none",
                fontFamily: "Outfit, sans-serif", fontSize: 22, fontWeight: 800,
                color: "white", width: "100%", outline: "none", padding: 0,
              }}
            />
            <input
              value={workflow.description || ""}
              onChange={(e) => updateMeta({ description: e.target.value })}
              placeholder="Descrição (o que este workflow faz?)"
              style={{
                background: "transparent", border: "none",
                fontSize: 13, color: "#A3A3A3", width: "100%", outline: "none", marginTop: 2,
              }}
            />
          </div>
          <button
            onClick={() => setShowTestRun(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "9px 14px", background: "transparent",
              border: "1px solid #27272A", borderRadius: 8,
              color: "#A3A3A3", fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            <Play size={14} /> Testar
          </button>
          <button
            onClick={save}
            disabled={saving}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "9px 14px",
              background: "linear-gradient(135deg, #F97316, #EA580C)",
              border: "none", borderRadius: 8,
              color: "white", fontSize: 13, fontWeight: 700, cursor: saving ? "wait" : "pointer",
              fontFamily: "Outfit, sans-serif",
              boxShadow: "0 4px 14px rgba(249, 115, 22, 0.3)",
              opacity: saving ? 0.7 : 1,
            }}
          >
            <Save size={14} /> {saving ? "Salvando..." : "Salvar"}
          </button>
        </div>

        {validationErrors && validationErrors.length > 0 && (
          <div style={{ padding: 12, background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: 8, color: "#FBBF24", fontSize: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, fontWeight: 700 }}>
              <AlertTriangle size={14} /> Avisos de validação (não bloqueia salvar)
            </div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {validationErrors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}

        {/* Grid: canvas + inspector */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 16, alignItems: "flex-start" }}>
          {/* Canvas */}
          <div style={{ background: "#0F0F0F", border: "1px solid #27272A", borderRadius: 12, padding: 20, minHeight: 500 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div>
                <div style={{ color: "white", fontFamily: "Outfit, sans-serif", fontSize: 15, fontWeight: 700 }}>
                  Passos do Workflow
                </div>
                <div style={{ color: "#737373", fontSize: 11, marginTop: 2 }}>
                  Execução de cima para baixo. Clique em um passo para configurar.
                </div>
              </div>
              <button
                onClick={() => setShowPalette(true)}
                style={{ padding: "7px 12px", background: "rgba(249,115,22,0.12)", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 8, color: "#F97316", fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
              >
                <Plus size={14} /> Adicionar passo
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {orderedNodes.map((node, idx) => (
                <NodeBar
                  key={node.id}
                  node={node}
                  index={idx}
                  total={orderedNodes.length}
                  selected={selectedNodeId === node.id}
                  onSelect={() => setSelectedNodeId(node.id)}
                  onDelete={() => deleteNode(node.id)}
                  onAddAfter={() => { setSelectedNodeId(node.id); setShowPalette(true); }}
                  nodesById={Object.fromEntries((workflow.nodes || []).map(n => [n.id, n]))}
                />
              ))}
            </div>
          </div>

          {/* Inspector */}
          <div style={{ background: "#0F0F0F", border: "1px solid #27272A", borderRadius: 12, padding: 18, minHeight: 500, position: "sticky", top: 0 }}>
            {selectedNode ? (
              <NodeInspector
                node={selectedNode}
                allNodes={workflow.nodes || []}
                onUpdate={(patch) => updateNode(selectedNode.id, patch)}
                onUpdateConfig={(cfg) => updateNodeConfig(selectedNode.id, cfg)}
                onDelete={() => deleteNode(selectedNode.id)}
              />
            ) : (
              <div style={{ color: "#737373", fontSize: 13, padding: 20, textAlign: "center" }}>
                <Info size={22} style={{ margin: "0 auto 10px", opacity: 0.5 }} />
                <div style={{ marginBottom: 4, color: "#A3A3A3", fontWeight: 600 }}>Nenhum passo selecionado</div>
                <div>Clique num passo ao lado para configurar.</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Palette (modal) */}
      {showPalette && (
        <NodePaletteModal
          onClose={() => setShowPalette(false)}
          onPick={(type) => addNode(type, selectedNodeId)}
          workflow={workflow}
        />
      )}

      {/* Test run (sandbox) */}
      {showTestRun && (
        <TestRunModal
          workflowId={workflowId}
          onClose={() => setShowTestRun(false)}
        />
      )}
    </Layout>
  );
}

/* ─────────────────────────────────────────────────────────────────
 * NodeBar — linha horizontal representando um passo
 * ───────────────────────────────────────────────────────────────── */
function NodeBar({ node, index, total, selected, onSelect, onDelete, onAddAfter, nodesById }) {
  const cat = nodeCatalogEntry(node.type);
  const Icon = cat.icon;
  const isLast = index === total - 1;

  // Resumo do que o nó faz, pegando do config
  const summary = summaryForNode(node);

  return (
    <>
      <div
        onClick={onSelect}
        style={{
          display: "flex", alignItems: "stretch", gap: 12,
          background: selected ? "rgba(249,115,22,0.08)" : "#121212",
          border: selected ? "1px solid rgba(249,115,22,0.5)" : "1px solid #27272A",
          borderRadius: 10, padding: "12px 14px", cursor: "pointer",
          transition: "all 0.15s",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, minWidth: 28 }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: `${cat.color}22`, color: cat.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
            {index + 1}
          </div>
        </div>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: `${cat.color}22`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon size={18} color={cat.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "white", fontSize: 14, fontWeight: 700, fontFamily: "Outfit, sans-serif" }}>
            {node.label || cat.label}
            <span style={{ color: "#525252", fontSize: 11, fontWeight: 500, marginLeft: 8 }}>{cat.label}</span>
          </div>
          {summary && (
            <div style={{ color: "#A3A3A3", fontSize: 12, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {summary}
            </div>
          )}
          {node.type === "branch" && (
            <BranchPreview branch={node} nodesById={nodesById} />
          )}
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <button
            onClick={(e) => { e.stopPropagation(); onAddAfter(); }}
            title="Adicionar passo depois"
            style={{ background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#A3A3A3", padding: 4, cursor: "pointer" }}
          >
            <Plus size={12} />
          </button>
          {node.type !== "trigger" && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Excluir"
              style={{ background: "transparent", border: "1px solid #27272A", borderRadius: 6, color: "#737373", padding: 4, cursor: "pointer" }}
              onMouseEnter={e => { e.currentTarget.style.color = "#EF4444"; e.currentTarget.style.borderColor = "rgba(239,68,68,0.3)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "#737373"; e.currentTarget.style.borderColor = "#27272A"; }}
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>
      {!isLast && node.type !== "end" && (
        <div style={{ display: "flex", justifyContent: "center" }}>
          <ChevronDown size={16} color="#525252" />
        </div>
      )}
    </>
  );
}

function BranchPreview({ branch, nodesById }) {
  const cases = branch.config?.cases || [];
  if (cases.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
      {cases.slice(0, 3).map((c, i) => (
        <div key={i} style={{ fontSize: 10, color: "#F59E0B", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)", borderRadius: 4, padding: "2px 6px" }}>
          se <strong>{String(c.when)}</strong> → {nodesById[c.to]?.label || c.to}
        </div>
      ))}
      {cases.length > 3 && (
        <div style={{ fontSize: 10, color: "#737373" }}>+{cases.length - 3}</div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
 * Inspector — configura o nó selecionado
 * ───────────────────────────────────────────────────────────────── */
function NodeInspector({ node, allNodes, onUpdate, onUpdateConfig, onDelete }) {
  const cat = nodeCatalogEntry(node.type);
  const Icon = cat.icon;

  const nextOptions = allNodes.filter(n => n.id !== node.id);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: `${cat.color}22`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon size={18} color={cat.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "white", fontFamily: "Outfit, sans-serif", fontSize: 15, fontWeight: 700 }}>
            {cat.label}
          </div>
          <div style={{ color: "#737373", fontSize: 11 }}>id: {node.id}</div>
        </div>
      </div>
      <p style={{ color: "#A3A3A3", fontSize: 12, lineHeight: 1.5, margin: "10px 0 16px" }}>
        {cat.description}
      </p>

      <InspectorField label="Rótulo (nome amigável)">
        <input
          value={node.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          style={inputStyle}
          placeholder={cat.short}
        />
      </InspectorField>

      {node.type === "trigger" && <TriggerInspector />}

      {node.type === "set_variable" && (
        <SetVariableInspector node={node} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type === "classify_intent" && (
        <ClassifyIntentInspector node={node} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type === "branch" && (
        <BranchInspector node={node} allNodes={allNodes} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type === "tool_call" && (
        <ToolCallInspector node={node} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type === "llm_reply" && (
        <LLMReplyInspector node={node} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type === "send_message" && (
        <SendMessageInspector node={node} onUpdateConfig={onUpdateConfig} />
      )}

      {node.type !== "branch" && node.type !== "end" && (
        <InspectorField label="Próximo passo">
          <select
            value={node.next || ""}
            onChange={(e) => onUpdate({ next: e.target.value || null })}
            style={inputStyle}
          >
            <option value="">(fim do fluxo)</option>
            {nextOptions.map(n => (
              <option key={n.id} value={n.id}>{n.label || n.id} ({nodeCatalogEntry(n.type).short})</option>
            ))}
          </select>
        </InspectorField>
      )}

      {node.type !== "trigger" && (
        <button
          onClick={onDelete}
          style={{
            width: "100%", marginTop: 16, padding: "9px 12px",
            background: "transparent", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          }}
        >
          <Trash2 size={14} /> Excluir passo
        </button>
      )}
    </div>
  );
}

function TriggerInspector() {
  return (
    <div style={{ padding: 12, background: "rgba(249,115,22,0.06)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 8, fontSize: 12, color: "#A3A3A3", lineHeight: 1.5 }}>
      Este é o ponto de entrada. O workflow começa aqui quando uma mensagem do lead chega no webhook.
      <br /><br />
      Variáveis disponíveis: <code style={codeTag}>{'{{input}}'}</code>, <code style={codeTag}>{'{{ticket_id}}'}</code>, <code style={codeTag}>{'{{contact_number}}'}</code>, <code style={codeTag}>{'{{contact_name}}'}</code>.
    </div>
  );
}

function SetVariableInspector({ node, onUpdateConfig }) {
  const variables = node.config?.variables || {};
  const entries = Object.entries(variables);

  const updateEntry = (idx, key, value) => {
    const newEntries = [...entries];
    if (key !== undefined) newEntries[idx] = [key, newEntries[idx]?.[1] ?? ""];
    if (value !== undefined) newEntries[idx] = [newEntries[idx]?.[0] ?? "", value];
    onUpdateConfig({ variables: Object.fromEntries(newEntries.filter(([k]) => k)) });
  };
  const addEntry = () => {
    const newEntries = [...entries, ["nova_var", ""]];
    onUpdateConfig({ variables: Object.fromEntries(newEntries) });
  };
  const removeEntry = (idx) => {
    const newEntries = entries.filter((_, i) => i !== idx);
    onUpdateConfig({ variables: Object.fromEntries(newEntries) });
  };

  return (
    <InspectorField label="Variáveis a definir">
      {entries.length === 0 && (
        <div style={{ color: "#737373", fontSize: 12, marginBottom: 8 }}>Nenhuma variável. Clique em "Adicionar".</div>
      )}
      {entries.map(([k, v], idx) => (
        <div key={idx} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <input
            value={k}
            onChange={(e) => updateEntry(idx, e.target.value, undefined)}
            style={{ ...inputStyle, flex: 1 }}
            placeholder="nome"
          />
          <input
            value={v}
            onChange={(e) => updateEntry(idx, undefined, e.target.value)}
            style={{ ...inputStyle, flex: 2 }}
            placeholder="valor"
          />
          <button onClick={() => removeEntry(idx)} style={iconBtnStyle} title="Remover">
            <X size={12} />
          </button>
        </div>
      ))}
      <button onClick={addEntry} style={{ ...pillBtnStyle, marginTop: 6 }}>
        <Plus size={12} /> Adicionar variável
      </button>
    </InspectorField>
  );
}

function ClassifyIntentInspector({ node, onUpdateConfig }) {
  const intents = node.config?.intents || [];
  const output = node.config?.output || "intent";

  const updateIntent = (idx, field, value) => {
    const newList = intents.map((it, i) => i === idx ? { ...it, [field]: value } : it);
    onUpdateConfig({ intents: newList });
  };
  const addIntent = () => {
    onUpdateConfig({ intents: [...intents, { id: `intent_${intents.length + 1}`, description: "" }] });
  };
  const removeIntent = (idx) => {
    onUpdateConfig({ intents: intents.filter((_, i) => i !== idx) });
  };

  return (
    <>
      <InspectorField label="Salvar resultado em" hint="Nome da variável onde a intenção classificada será guardada.">
        <input
          value={output}
          onChange={(e) => onUpdateConfig({ output: e.target.value })}
          style={inputStyle}
          placeholder="intent"
        />
      </InspectorField>

      <InspectorField label="Categorias possíveis" hint="A IA escolhe UMA destas com base na mensagem do lead.">
        {intents.length === 0 && (
          <div style={{ color: "#737373", fontSize: 12, marginBottom: 8 }}>Adicione pelo menos 2 categorias.</div>
        )}
        {intents.map((it, idx) => (
          <div key={idx} style={{ marginBottom: 8, padding: 10, background: "#0A0A0A", border: "1px solid #27272A", borderRadius: 8 }}>
            <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input
                value={it.id}
                onChange={(e) => updateIntent(idx, "id", e.target.value)}
                style={{ ...inputStyle, flex: 1 }}
                placeholder="ex: agendar"
              />
              <button onClick={() => removeIntent(idx)} style={iconBtnStyle} title="Remover">
                <X size={12} />
              </button>
            </div>
            <input
              value={it.description || ""}
              onChange={(e) => updateIntent(idx, "description", e.target.value)}
              style={inputStyle}
              placeholder="descrição (ex: quer marcar horário)"
            />
          </div>
        ))}
        <button onClick={addIntent} style={pillBtnStyle}>
          <Plus size={12} /> Adicionar categoria
        </button>
      </InspectorField>
    </>
  );
}

function BranchInspector({ node, allNodes, onUpdateConfig }) {
  const on = node.config?.on || "intent";
  const cases = node.config?.cases || [];
  const defaultTo = node.config?.default || "";

  const updateCase = (idx, patch) => {
    onUpdateConfig({ cases: cases.map((c, i) => i === idx ? { ...c, ...patch } : c) });
  };
  const addCase = () => {
    onUpdateConfig({ cases: [...cases, { when: "", to: "" }] });
  };
  const removeCase = (idx) => {
    onUpdateConfig({ cases: cases.filter((_, i) => i !== idx) });
  };

  const nodeOptions = allNodes.filter(n => n.id !== node.id);

  return (
    <>
      <InspectorField label="Baseado na variável" hint="O valor desta variável decide para onde o fluxo vai.">
        <input
          value={on}
          onChange={(e) => onUpdateConfig({ on: e.target.value })}
          style={inputStyle}
          placeholder="intent"
        />
      </InspectorField>

      <InspectorField label="Regras de desvio">
        {cases.length === 0 && (
          <div style={{ color: "#737373", fontSize: 12, marginBottom: 8 }}>Adicione ao menos uma regra.</div>
        )}
        {cases.map((c, idx) => (
          <div key={idx} style={{ display: "grid", gridTemplateColumns: "1fr 14px 1fr auto", gap: 4, alignItems: "center", marginBottom: 6 }}>
            <input
              value={c.when || ""}
              onChange={(e) => updateCase(idx, { when: e.target.value })}
              style={inputStyle}
              placeholder="valor"
            />
            <span style={{ color: "#737373", fontSize: 11, textAlign: "center" }}>→</span>
            <select
              value={c.to || ""}
              onChange={(e) => updateCase(idx, { to: e.target.value })}
              style={inputStyle}
            >
              <option value="">—</option>
              {nodeOptions.map(n => (
                <option key={n.id} value={n.id}>{n.label || n.id}</option>
              ))}
            </select>
            <button onClick={() => removeCase(idx)} style={iconBtnStyle} title="Remover">
              <X size={12} />
            </button>
          </div>
        ))}
        <button onClick={addCase} style={pillBtnStyle}>
          <Plus size={12} /> Adicionar regra
        </button>
      </InspectorField>

      <InspectorField label="Caminho padrão (se nada casar)">
        <select
          value={defaultTo}
          onChange={(e) => onUpdateConfig({ default: e.target.value })}
          style={inputStyle}
        >
          <option value="">—</option>
          {nodeOptions.map(n => (
            <option key={n.id} value={n.id}>{n.label || n.id}</option>
          ))}
        </select>
      </InspectorField>
    </>
  );
}

function ToolCallInspector({ node, onUpdateConfig }) {
  const mcpId = node.config?.mcp_id || "clickmassa";
  const toolName = node.config?.tool_name || "";
  const params = node.config?.params || {};
  const saveAs = node.config?.save_as || "";

  const updateParam = (k, v) => {
    onUpdateConfig({ params: { ...params, [k]: v } });
  };
  const removeParam = (k) => {
    const newParams = { ...params };
    delete newParams[k];
    onUpdateConfig({ params: newParams });
  };
  const addParam = () => {
    const key = prompt("Nome do parâmetro:");
    if (key) onUpdateConfig({ params: { ...params, [key]: "" } });
  };

  return (
    <>
      <InspectorField label="MCP (provedor de ferramentas)">
        <select
          value={mcpId}
          onChange={(e) => onUpdateConfig({ mcp_id: e.target.value })}
          style={inputStyle}
        >
          <option value="clickmassa">ClickMassa CRM</option>
        </select>
      </InspectorField>

      <InspectorField label="Ação" hint="Qual função do CRM será executada.">
        <select
          value={toolName}
          onChange={(e) => onUpdateConfig({ tool_name: e.target.value })}
          style={inputStyle}
        >
          <option value="">— escolha —</option>
          {CLICKMASSA_TOOLS.map(t => (
            <option key={t.name} value={t.name}>{t.label}</option>
          ))}
        </select>
      </InspectorField>

      <InspectorField label="Parâmetros" hint={'Use {{variavel}} para inserir valores dinâmicos.'}>
        {Object.entries(params).length === 0 && (
          <div style={{ color: "#737373", fontSize: 12, marginBottom: 8 }}>Nenhum parâmetro.</div>
        )}
        {Object.entries(params).map(([k, v]) => (
          <div key={k} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <input value={k} readOnly style={{ ...inputStyle, flex: 1, background: "#0A0A0A" }} />
            <input
              value={v}
              onChange={(e) => updateParam(k, e.target.value)}
              style={{ ...inputStyle, flex: 2 }}
              placeholder="valor ou {{var}}"
            />
            <button onClick={() => removeParam(k)} style={iconBtnStyle} title="Remover">
              <X size={12} />
            </button>
          </div>
        ))}
        <button onClick={addParam} style={pillBtnStyle}>
          <Plus size={12} /> Adicionar parâmetro
        </button>
      </InspectorField>

      <InspectorField label="Salvar resultado em (opcional)" hint="Guarda o retorno da ação numa variável para usar nos próximos passos.">
        <input
          value={saveAs}
          onChange={(e) => onUpdateConfig({ save_as: e.target.value })}
          style={inputStyle}
          placeholder="ex: resultado_busca"
        />
      </InspectorField>
    </>
  );
}

function LLMReplyInspector({ node, onUpdateConfig }) {
  const system = node.config?.system || "";
  const user = node.config?.user || "";
  const output = node.config?.output || "reply";
  const temperature = node.config?.temperature ?? 0.3;

  return (
    <>
      <InspectorField label="Instrução para a IA (system prompt)" hint="Diga à IA como ela deve se comportar e o que responder.">
        <textarea
          value={system}
          onChange={(e) => onUpdateConfig({ system: e.target.value })}
          style={{ ...inputStyle, minHeight: 100, resize: "vertical", fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}
          placeholder="Você é um atendente simpático. Responda em português, curto e direto..."
        />
      </InspectorField>

      <InspectorField label="Mensagem do usuário (user)" hint="Use {{input}} para a mensagem do lead.">
        <textarea
          value={user}
          onChange={(e) => onUpdateConfig({ user: e.target.value })}
          style={{ ...inputStyle, minHeight: 60, resize: "vertical", fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}
          placeholder="{{input}}"
        />
      </InspectorField>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <InspectorField label="Salvar em">
          <input
            value={output}
            onChange={(e) => onUpdateConfig({ output: e.target.value })}
            style={inputStyle}
            placeholder="reply"
          />
        </InspectorField>
        <InspectorField label="Temperatura">
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            onChange={(e) => onUpdateConfig({ temperature: parseFloat(e.target.value) })}
            style={inputStyle}
          />
        </InspectorField>
      </div>
    </>
  );
}

function SendMessageInspector({ node, onUpdateConfig }) {
  const message = node.config?.message || "{{reply}}";
  return (
    <InspectorField label="Mensagem a enviar" hint="Use {{reply}} para pegar a resposta gerada por IA ou escreva um texto fixo.">
      <textarea
        value={message}
        onChange={(e) => onUpdateConfig({ message: e.target.value })}
        style={{ ...inputStyle, minHeight: 80, resize: "vertical", fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}
        placeholder="{{reply}}"
      />
    </InspectorField>
  );
}

/* ─────────────────────────────────────────────────────────────────
 * Modal — Node Palette
 * ───────────────────────────────────────────────────────────────── */
function NodePaletteModal({ onClose, onPick, workflow }) {
  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 680, width: "100%", maxHeight: "85vh", overflowY: "auto", background: "#0F0F0F", border: "1px solid #27272A", borderRadius: 14, padding: 24 }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
          <div>
            <h2 style={{ fontFamily: "Outfit, sans-serif", fontSize: 20, fontWeight: 800, color: "white", marginBottom: 4 }}>
              Adicionar um passo
            </h2>
            <p style={{ color: "#A3A3A3", fontSize: 12 }}>Escolha o que este passo do workflow deve fazer.</p>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "#737373", cursor: "pointer", fontSize: 22 }}>×</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
          {NODE_CATALOG.filter(cat => !(cat.unique && (workflow.nodes || []).some(n => n.type === cat.type))).map(cat => {
            const Icon = cat.icon;
            return (
              <button
                key={cat.type}
                onClick={() => onPick(cat.type)}
                style={{
                  textAlign: "left", padding: 14, borderRadius: 10,
                  background: "#121212", border: "1px solid #27272A",
                  cursor: "pointer", transition: "all 0.15s", color: "white",
                  display: "flex", gap: 10, alignItems: "flex-start",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = cat.color; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; }}
              >
                <div style={{ width: 34, height: 34, borderRadius: 8, background: `${cat.color}22`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon size={18} color={cat.color} />
                </div>
                <div>
                  <div style={{ fontFamily: "Outfit, sans-serif", fontSize: 14, fontWeight: 700, marginBottom: 2 }}>
                    {cat.label}
                  </div>
                  <div style={{ color: "#A3A3A3", fontSize: 12, lineHeight: 1.45 }}>
                    {cat.description}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
 * Modal — Test Run (sandbox)
 * ───────────────────────────────────────────────────────────────── */
function TestRunModal({ workflowId, onClose }) {
  const [input, setInput] = useState("Olá, gostaria de agendar um atendimento");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const run = async () => {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const { data } = await axios.post(
        `${API}/workflows/${workflowId}/test-run`,
        { input, contact_name: "Teste", contact_number: "5511999999999", ticket_id: "sandbox-123", contact_id: "sandbox-contact", variables: {} },
        { withCredentials: true },
      );
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao testar");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 720, width: "100%", maxHeight: "85vh", overflowY: "auto", background: "#0F0F0F", border: "1px solid #27272A", borderRadius: 14, padding: 24 }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
          <div>
            <h2 style={{ fontFamily: "Outfit, sans-serif", fontSize: 20, fontWeight: 800, color: "white", marginBottom: 4 }}>
              Testar workflow
            </h2>
            <p style={{ color: "#A3A3A3", fontSize: 12 }}>Roda o fluxo com input simulado. Nenhuma mensagem real é enviada.</p>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "#737373", cursor: "pointer", fontSize: 22 }}>×</button>
        </div>

        <InspectorField label="Mensagem simulada do lead">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            style={{ ...inputStyle, minHeight: 60, resize: "vertical" }}
          />
        </InspectorField>

        <button
          onClick={run}
          disabled={running}
          style={{
            width: "100%", padding: "10px 14px",
            background: "linear-gradient(135deg, #F97316, #EA580C)",
            border: "none", borderRadius: 8, color: "white", fontSize: 14,
            fontWeight: 700, cursor: running ? "wait" : "pointer",
            fontFamily: "Outfit, sans-serif",
            marginTop: 8,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            opacity: running ? 0.7 : 1,
          }}
        >
          <Play size={14} /> {running ? "Rodando..." : "Executar teste"}
        </button>

        {error && (
          <div style={{ marginTop: 16, padding: 12, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, color: "#F87171", fontSize: 13 }}>
            {typeof error === "string" ? error : JSON.stringify(error)}
          </div>
        )}

        {result && (
          <div style={{ marginTop: 20 }}>
            <div style={{ color: "#737373", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8, fontWeight: 700 }}>
              Resultado
            </div>
            {result.status === "invalid" ? (
              <div style={{ padding: 12, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, color: "#F87171", fontSize: 13 }}>
                Workflow inválido:
                <ul style={{ margin: "6px 0 0 16px" }}>
                  {(result.validation_errors || []).map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
                  <Pill label="Status" value={result.errors?.length ? "erros" : "ok"} color={result.errors?.length ? "#EF4444" : "#10B981"} />
                  <Pill label="Passos" value={(result.steps || []).length} color="#F97316" />
                  <Pill label="Duração" value={`${result.duration_ms || 0}ms`} color="#3B82F6" />
                </div>

                <div style={{ padding: 14, background: "#0A0A0A", border: "1px solid #27272A", borderRadius: 8, marginBottom: 10 }}>
                  <div style={{ color: "#A3A3A3", fontSize: 11, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.1em" }}>Output final</div>
                  <div style={{ color: "white", fontSize: 13, whiteSpace: "pre-wrap" }}>
                    {result.output || <em style={{ color: "#737373" }}>(vazio)</em>}
                  </div>
                </div>

                <div style={{ color: "#737373", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, fontWeight: 700 }}>
                  Trace de execução
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {(result.steps || []).map((s, i) => (
                    <div key={i} style={{ padding: 10, background: "#121212", border: "1px solid #27272A", borderRadius: 8, fontSize: 12, color: "#A3A3A3" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ color: "white", fontWeight: 700 }}>{i + 1}.</span>
                        <span style={{ color: "white", fontWeight: 600 }}>{s.node_label || s.node_id}</span>
                        <span style={{ color: "#737373", fontSize: 10 }}>({s.node_type})</span>
                        <span style={{ marginLeft: "auto", color: "#525252", fontSize: 10 }}>{s.duration_ms}ms</span>
                      </div>
                      {s.result && (
                        <pre style={{ margin: 0, color: "#A3A3A3", fontSize: 11, overflow: "auto" }}>
                          {JSON.stringify(s.result, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>

                {result.errors && result.errors.length > 0 && (
                  <div style={{ marginTop: 10, padding: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8, fontSize: 12, color: "#F87171" }}>
                    Erros: {result.errors.join(" | ")}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Pill({ label, value, color }) {
  return (
    <div style={{ padding: "6px 10px", background: `${color}11`, border: `1px solid ${color}44`, borderRadius: 6, color, fontSize: 11, fontWeight: 600 }}>
      {label}: {value}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
 * Helpers
 * ───────────────────────────────────────────────────────────────── */
function InspectorField({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", color: "#E4E4E7", fontSize: 12, fontWeight: 600, marginBottom: 4, fontFamily: "IBM Plex Sans, sans-serif" }}>
        {label}
      </label>
      {hint && <div style={{ color: "#737373", fontSize: 11, marginBottom: 6, lineHeight: 1.4 }}>{hint}</div>}
      {children}
    </div>
  );
}

const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  background: "#121212",
  border: "1px solid #27272A",
  borderRadius: 6,
  color: "white",
  fontSize: 13,
  fontFamily: "IBM Plex Sans, sans-serif",
  outline: "none",
};

const iconBtnStyle = {
  background: "transparent",
  border: "1px solid #27272A",
  borderRadius: 6,
  color: "#737373",
  padding: "4px 6px",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const pillBtnStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "5px 10px",
  background: "rgba(249,115,22,0.1)",
  border: "1px solid rgba(249,115,22,0.25)",
  borderRadius: 6,
  color: "#F97316",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

const codeTag = {
  background: "rgba(249,115,22,0.15)",
  color: "#F97316",
  padding: "1px 4px",
  borderRadius: 3,
  fontFamily: "IBM Plex Mono, monospace",
  fontSize: 11,
};

function defaultConfig(type) {
  switch (type) {
    case "set_variable":
      return { variables: {} };
    case "classify_intent":
      return { output: "intent", intents: [{ id: "opcao_1", description: "" }, { id: "opcao_2", description: "" }] };
    case "branch":
      return { on: "intent", cases: [], default: "" };
    case "tool_call":
      return { mcp_id: "clickmassa", tool_name: "", params: {}, save_as: "" };
    case "llm_reply":
      return { system: "Você é um assistente útil e responde em português.", user: "{{input}}", output: "reply", temperature: 0.3 };
    case "send_message":
      return { message: "{{reply}}" };
    default:
      return {};
  }
}

function summaryForNode(node) {
  switch (node.type) {
    case "classify_intent":
      return `${(node.config?.intents || []).length} categorias → ${node.config?.output || "intent"}`;
    case "branch":
      return `sobre "${node.config?.on || "intent"}" · ${(node.config?.cases || []).length} regras`;
    case "tool_call":
      return node.config?.tool_name ? `${node.config?.mcp_id}.${node.config.tool_name}` : "ação não definida";
    case "llm_reply":
      return node.config?.system ? node.config.system.slice(0, 60) + (node.config.system.length > 60 ? "…" : "") : "sem instrução";
    case "send_message":
      return `envia: "${(node.config?.message || "{{reply}}").slice(0, 60)}"`;
    case "set_variable":
      return `${Object.keys(node.config?.variables || {}).length} variáveis`;
    case "trigger":
      return "aguarda mensagem do webhook";
    case "end":
      return "encerra o fluxo";
    default:
      return "";
  }
}

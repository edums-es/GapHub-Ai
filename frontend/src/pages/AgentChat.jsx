import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Bot, Send, ChevronDown, ChevronRight, Wrench, AlertCircle, RefreshCw, MessageSquare, Plus, Sparkles, Wifi, Copy, Check } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// ── Renderizador de Markdown leve ──────────────────────────────────────────
function renderInline(text, keyPrefix) {
  const parts = [];
  const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let lastIndex = 0;
  let match;
  let idx = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`${keyPrefix}-t${idx++}`}>{text.slice(lastIndex, match.index)}</span>);
    }
    const raw = match[0];
    if (raw.startsWith("**")) {
      parts.push(<strong key={`${keyPrefix}-b${idx++}`} style={{ color: "#FFFFFF", fontWeight: 700 }}>{raw.slice(2, -2)}</strong>);
    } else if (raw.startsWith("*")) {
      parts.push(<em key={`${keyPrefix}-i${idx++}`} style={{ color: "#D4D4D4" }}>{raw.slice(1, -1)}</em>);
    } else if (raw.startsWith("`")) {
      parts.push(<code key={`${keyPrefix}-c${idx++}`} style={{ background: "#2A2A2A", padding: "2px 6px", borderRadius: 4, fontSize: "0.87em", fontFamily: "IBM Plex Mono, monospace", color: "#10B981" }}>{raw.slice(1, -1)}</code>);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(<span key={`${keyPrefix}-t${idx++}`}>{text.slice(lastIndex)}</span>);
  }
  return parts.length === 0 ? text : parts;
}

function MarkdownContent({ content }) {
  if (!content) return null;
  const lines = content.split("\n");
  const result = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // Heading
    const headingMatch = line.match(/^(#{1,3}) (.+)/);
    if (headingMatch) {
      const lvl = headingMatch[1].length;
      const szMap = [17, 15, 14]; const fwMap = [800, 700, 600];
      result.push(
        <div key={i} style={{ fontSize: szMap[lvl-1], fontWeight: fwMap[lvl-1], color: "#FFFFFF", margin: `${lvl === 1 ? 14 : 10}px 0 ${lvl === 1 ? 6 : 3}px`, fontFamily: "Outfit, sans-serif", lineHeight: 1.3 }}>
          {renderInline(headingMatch[2], `h${i}`)}
        </div>
      );
      i++; continue;
    }
    // Lista não-ordenada
    if (/^[-*] /.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) {
        items.push(<li key={i} style={{ marginBottom: 3, lineHeight: 1.65, color: "#E2E8F0" }}>{renderInline(lines[i].replace(/^[-*] /, ""), `li${i}`)}</li>);
        i++;
      }
      result.push(<ul key={`ul${i}`} style={{ margin: "6px 0", paddingLeft: 20, fontSize: 14 }}>{items}</ul>);
      continue;
    }
    // Lista ordenada
    if (/^\d+\. /.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(<li key={i} style={{ marginBottom: 3, lineHeight: 1.65, color: "#E2E8F0" }}>{renderInline(lines[i].replace(/^\d+\. /, ""), `li${i}`)}</li>);
        i++;
      }
      result.push(<ol key={`ol${i}`} style={{ margin: "6px 0", paddingLeft: 20, fontSize: 14 }}>{items}</ol>);
      continue;
    }
    // Separador
    if (/^---+$/.test(line.trim())) {
      result.push(<hr key={i} style={{ border: "none", borderTop: "1px solid #2A2A2A", margin: "10px 0" }} />);
      i++; continue;
    }
    // Linha vazia
    if (line.trim() === "") {
      if (result.length > 0) result.push(<div key={i} style={{ height: 6 }} />);
      i++; continue;
    }
    // Parágrafo
    result.push(
      <p key={i} style={{ margin: "0 0 1px", color: "#E2E8F0", fontSize: 14, lineHeight: 1.75 }}>
        {renderInline(line, `p${i}`)}
      </p>
    );
    i++;
  }
  return <div style={{ fontFamily: "IBM Plex Sans, sans-serif" }}>{result}</div>;
}
// ──────────────────────────────────────────────────────────────────────────────

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <button
      onClick={handleCopy}
      title="Copiar resposta"
      style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 10, padding: "3px 8px", background: "transparent", border: "1px solid #2A2A2A", borderRadius: 6, color: copied ? "#10B981" : "#525252", cursor: "pointer", fontSize: 11, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.15s" }}
      onMouseEnter={e => { if (!copied) { e.currentTarget.style.borderColor = "#404040"; e.currentTarget.style.color = "#A3A3A3"; } }}
      onMouseLeave={e => { if (!copied) { e.currentTarget.style.borderColor = "#2A2A2A"; e.currentTarget.style.color = "#525252"; } }}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? "Copiado!" : "Copiar"}
    </button>
  );
}

function ToolCallCard({ step, index }) {
  const [open, setOpen] = useState(false);
  const resultStr = typeof step.result === "object" ? JSON.stringify(step.result, null, 2) : String(step.result || "");

  return (
    <div style={{ background: "rgba(16,185,129,0.06)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 8, marginTop: 8, overflow: "hidden" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        {open ? <ChevronDown size={13} color="#10B981" /> : <ChevronRight size={13} color="#10B981" />}
        <Wrench size={13} color="#10B981" />
        <span style={{ fontSize: 12, color: "#10B981", fontFamily: "IBM Plex Mono, monospace", fontWeight: 600 }}>
          {step.tool}
        </span>
        <span style={{ fontSize: 10, color: "#737373", marginLeft: "auto" }}>ferramenta {index + 1}</span>
      </button>
      {open && (
        <div style={{ padding: "0 12px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
          {Object.keys(step.params || {}).length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "#737373", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Parâmetros</div>
              <pre style={{ fontSize: 11, color: "#A3A3A3", background: "#1A1A1A", padding: 8, borderRadius: 6, margin: 0, overflow: "auto", maxHeight: 120 }}>{JSON.stringify(step.params, null, 2)}</pre>
            </div>
          )}
          <div>
            <div style={{ fontSize: 10, color: "#737373", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Resultado</div>
            <pre style={{ fontSize: 11, color: "#E2E8F0", background: "#1A1A1A", padding: 8, borderRadius: 6, margin: 0, overflow: "auto", maxHeight: 160 }}>{resultStr.length > 800 ? resultStr.slice(0, 800) + "..." : resultStr}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

function ChatMessage({ msg }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <div style={{ maxWidth: "72%", background: "#F97316", borderRadius: "14px 14px 4px 14px", padding: "11px 16px" }}>
          <p style={{ margin: 0, color: "white", fontSize: 14, lineHeight: 1.6, fontFamily: "IBM Plex Sans, sans-serif", whiteSpace: "pre-wrap" }}>{msg.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "flex-start" }}>
      <div style={{ width: 32, height: 32, background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.3)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
        {msg.loading
          ? <div style={{ width: 14, height: 14, border: "2px solid rgba(59,130,246,0.3)", borderTopColor: "#3B82F6", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
          : <Bot size={15} color="#3B82F6" />}
      </div>
      <div style={{ flex: 1, maxWidth: "80%" }}>
        {msg.loading ? (
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: "4px 14px 14px 14px", padding: "12px 16px", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ display: "flex", gap: 4 }}>
              {[0, 1, 2].map(i => (
                <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: msg.pendingTool ? "#10B981" : "#3B82F6", animation: `bounce 1.2s infinite`, animationDelay: `${i * 0.2}s` }} />
              ))}
            </div>
            <span style={{ fontSize: 12, color: "#737373" }}>
              {msg.pendingTool
                ? <><Wrench size={11} style={{ display: "inline", marginRight: 4, color: "#10B981" }} />{msg.pendingTool.split("__")[1] || msg.pendingTool}...</>
                : "Processando..."}
            </span>
          </div>
        ) : msg.error ? (
          <div style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: "4px 14px 14px 14px", padding: "12px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <AlertCircle size={13} color="#EF4444" />
              <span style={{ fontSize: 12, color: "#EF4444", fontWeight: 600 }}>Erro na execução</span>
            </div>
            <p style={{ margin: 0, color: "#F87171", fontSize: 13, lineHeight: 1.5 }}>{msg.error}</p>
          </div>
        ) : (
          <div style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: "4px 14px 14px 14px", padding: "14px 16px" }}>
            <MarkdownContent content={msg.content} />
            {msg.steps?.length > 0 && (
              <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid #27272A" }}>
                <div style={{ fontSize: 10, color: "#525252", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                  {msg.steps.length} ferramenta{msg.steps.length !== 1 ? "s" : ""} utilizada{msg.steps.length !== 1 ? "s" : ""}
                </div>
                {msg.steps.map((step, i) => (
                  <ToolCallCard key={i} step={step} index={i} />
                ))}
              </div>
            )}
            {msg.content && (
              <CopyButton text={msg.content} />
            )}
          </div>
        )}
        <div style={{ fontSize: 10, color: "#404040", marginTop: 4, paddingLeft: 4 }}>
          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : ""}
        </div>
      </div>
    </div>
  );
}

const QUICK_PROMPTS = [
  "Liste os tickets pendentes e priorize por urgência",
  "Faça o pré-atendimento dos leads aguardando resposta",
  "Verifique os contatos sem resposta nos últimos 3 dias",
  "Gere um resumo das atividades do dia",
];

export default function AgentChat() {
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingAgents, setLoadingAgents] = useState(true);
  // session_id persiste enquanto a conversa não for limpa — garante memória contínua
  const [sessionId, setSessionId] = useState(() => `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const [streamingEnabled, setStreamingEnabled] = useState(true); // Bug Fix #4: SSE streaming
  // Histórico paginado — mostra apenas os últimos N messages; "Carregar mais" busca anteriores
  const PAGE_SIZE = 20;
  const [displayCount, setDisplayCount] = useState(PAGE_SIZE);
  const messagesEndRef = useRef(null);
  const messagesTopRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    axios.get(`${API}/agents`, { withCredentials: true })
      .then(r => {
        const list = (r.data.agents || []).filter(a => a.status === "active");
        setAgents(list);
        if (list.length > 0) setSelectedAgent(list[0]);
      })
      .finally(() => setLoadingAgents(false));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Bug Fix #4 — SSE streaming: recebe tokens à medida que são gerados,
  // eliminando o congelamento da tela durante processamento do agente.
  const handleSendStreaming = useCallback(async (msg) => {
    const agentId = selectedAgent.agent_id;
    const userMsgId = Date.now();
    const agentMsgId = userMsgId + 1;

    const userMsg = { id: userMsgId, role: "user", content: msg, timestamp: new Date() };
    const agentMsg = { id: agentMsgId, role: "agent", loading: true, content: "", steps: [], timestamp: new Date() };
    setMessages(m => [...m, userMsg, agentMsg]);

    // Cria AbortController para poder cancelar stream se necessário
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch(`${API}/agents/${agentId}/run/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ input: msg, session_id: sessionId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // Remove loading indicator assim que a resposta começa
      setMessages(m => m.map(x => x.id === agentMsgId ? { ...x, loading: false } : x));

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const event = JSON.parse(raw);
            if (event.type === "done") {
              // Mensagem final com output completo e steps
              setMessages(m => m.map(x =>
                x.id === agentMsgId
                  ? { ...x, loading: false, content: event.output, steps: event.steps || [] }
                  : x
              ));
            } else if (event.type === "error") {
              setMessages(m => m.map(x =>
                x.id === agentMsgId
                  ? { ...x, loading: false, error: event.error }
                  : x
              ));
            } else if (event.type === "token") {
              // Token streaming incremental
              setMessages(m => m.map(x =>
                x.id === agentMsgId
                  ? { ...x, content: (x.content || "") + event.text }
                  : x
              ));
            } else if (event.type === "tool_start") {
              // Show "running tool..." indicator while tool executes
              setMessages(m => m.map(x =>
                x.id === agentMsgId
                  ? { ...x, loading: true, pendingTool: event.tool }
                  : x
              ));
            } else if (event.type === "tool_done") {
              // Tool finished — append to steps list and clear loading
              setMessages(m => m.map(x =>
                x.id === agentMsgId
                  ? {
                      ...x,
                      loading: false,
                      pendingTool: null,
                      steps: [...(x.steps || []), {
                        tool: event.tool,
                        params: {},
                        result: event.result,
                      }],
                    }
                  : x
              ));
            }
          } catch (_) {
            // Linha não-JSON, ignora
          }
        }
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      const err = e.message || "Erro ao processar. Verifique se o agente tem credenciais configuradas.";
      setMessages(m => m.map(x =>
        x.id === agentMsgId ? { ...x, loading: false, error: err } : x
      ));
    }
  }, [selectedAgent, sessionId]);

  const handleSendFallback = useCallback(async (msg) => {
    const userMsgId = Date.now();
    const agentMsgId = userMsgId + 1;
    const userMsg = { id: userMsgId, role: "user", content: msg, timestamp: new Date() };
    const loadingMsg = { id: agentMsgId, role: "agent", loading: true, timestamp: new Date() };
    setMessages(m => [...m, userMsg, loadingMsg]);

    try {
      const { data } = await axios.post(
        `${API}/agents/${selectedAgent.agent_id}/run`,
        { input: msg, session_id: sessionId },
        { withCredentials: true }
      );
      setMessages(m => m.map(x =>
        x.id === agentMsgId
          ? { ...x, loading: false, content: data.output, steps: data.steps || [] }
          : x
      ));
    } catch (e) {
      const err = e.response?.data?.detail || "Erro ao processar. Verifique se o agente tem credenciais configuradas.";
      setMessages(m => m.map(x =>
        x.id === agentMsgId ? { ...x, loading: false, error: err } : x
      ));
    }
  }, [selectedAgent, sessionId]);

  const handleSend = useCallback(async (text) => {
    const msg = (text || input).trim();
    if (!msg || !selectedAgent || sending) return;
    setInput("");
    setSending(true);
    try {
      if (streamingEnabled) {
        await handleSendStreaming(msg);
      } else {
        await handleSendFallback(msg);
      }
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [input, selectedAgent, sending, streamingEnabled, handleSendStreaming, handleSendFallback]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const clearChat = () => {
    // Cancela qualquer stream em andamento
    if (abortControllerRef.current) abortControllerRef.current.abort();
    setMessages([]);
    setSending(false);
    setDisplayCount(PAGE_SIZE);
    // Nova conversa = novo session_id = histórico limpo no backend
    setSessionId(`session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  };

  // Carrega mais mensagens antigas (paginação client-side)
  const handleLoadMore = () => {
    const prevScrollHeight = messagesTopRef.current?.parentNode?.scrollHeight || 0;
    setDisplayCount(c => c + PAGE_SIZE);
    // Após render, mantém posição de scroll (não salta para o topo)
    setTimeout(() => {
      const node = messagesTopRef.current?.parentNode;
      if (node) node.scrollTop = node.scrollHeight - prevScrollHeight;
    }, 50);
  };

  return (
    <Layout>
      <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)", animation: "fadeIn 0.3s ease-out" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
            <div style={{ width: 36, height: 36, background: "rgba(249,115,22,0.15)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <MessageSquare size={18} color="#F97316" />
            </div>
            <div>
              <h1 style={{ fontFamily: "Outfit, sans-serif", fontSize: 18, fontWeight: 800, color: "white", margin: 0 }}>Chat com Agente</h1>
              <p style={{ fontSize: 11, color: "#737373", margin: 0 }}>Envie comandos diretamente sem precisar entrar no workflow</p>
            </div>
          </div>

          {/* Agent selector */}
          <div style={{ display: "flex", align: "center", gap: 8 }}>
            {loadingAgents ? (
              <div style={{ width: 180, height: 38, background: "#1A1A1A", borderRadius: 8, border: "1px solid #27272A" }} />
            ) : agents.length === 0 ? (
              <div style={{ fontSize: 13, color: "#737373", padding: "8px 14px", background: "#1A1A1A", borderRadius: 8, border: "1px solid #27272A" }}>
                Nenhum agente ativo
              </div>
            ) : (
              <select
                value={selectedAgent?.agent_id || ""}
                onChange={e => {
                  const a = agents.find(x => x.agent_id === e.target.value);
                  setSelectedAgent(a);
                  clearChat(); // limpa chat, gera novo session_id e reseta paginação
                }}
                style={{ padding: "8px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 13, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", minWidth: 180, cursor: "pointer" }}
              >
                {agents.map(a => <option key={a.agent_id} value={a.agent_id}>{a.name}</option>)}
              </select>
            )}
            {/* Streaming toggle */}
            <button
              onClick={() => setStreamingEnabled(s => !s)}
              title={streamingEnabled ? "Streaming ativo (clique para desativar)" : "Streaming inativo (clique para ativar)"}
              style={{
                padding: "8px 10px", background: streamingEnabled ? "rgba(16,185,129,0.08)" : "#1A1A1A",
                border: `1px solid ${streamingEnabled ? "rgba(16,185,129,0.4)" : "#27272A"}`,
                borderRadius: 8, color: streamingEnabled ? "#10B981" : "#404040",
                cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                transition: "all 0.2s",
              }}
            >
              <Wifi size={12} /> SSE
            </button>
            {messages.length > 0 && (
              <button
                onClick={clearChat}
                title="Limpar conversa"
                style={{ padding: "8px 12px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "#737373", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 13, transition: "all 0.2s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#737373"; }}
              >
                <Plus size={14} /> Nova conversa
              </button>
            )}
          </div>
        </div>

        {/* Chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#0A0A0A", border: "1px solid #27272A", borderRadius: 12, overflow: "hidden", minHeight: 0 }}>

          {/* Messages */}
          <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
            {messages.length === 0 ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 24 }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ width: 56, height: 56, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                    <Sparkles size={24} color="#F97316" />
                  </div>
                  <p style={{ fontSize: 16, fontWeight: 600, color: "white", fontFamily: "Outfit, sans-serif", margin: "0 0 6px" }}>
                    {selectedAgent ? `Converse com ${selectedAgent.name}` : "Selecione um agente"}
                  </p>
                  <p style={{ fontSize: 13, color: "#737373", margin: 0 }}>
                    {selectedAgent ? "Envie um comando ou escolha uma sugestão abaixo" : "Escolha um agente no seletor acima para começar"}
                  </p>
                </div>

                {selectedAgent && (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10, width: "100%", maxWidth: 700 }}>
                    {QUICK_PROMPTS.map((prompt, i) => (
                      <button
                        key={i}
                        onClick={() => handleSend(prompt)}
                        disabled={sending}
                        style={{ padding: "10px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, color: "#A3A3A3", cursor: "pointer", fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif", lineHeight: 1.5, textAlign: "left", transition: "all 0.2s" }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; e.currentTarget.style.color = "white"; e.currentTarget.style.background = "#1f1f1f"; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; e.currentTarget.style.background = "#1A1A1A"; }}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <>
                <div ref={messagesTopRef} />
                {/* Botão "Carregar mais" — aparece quando há mensagens além do displayCount */}
                {messages.length > displayCount && (
                  <div style={{ textAlign: "center", marginBottom: 12 }}>
                    <button
                      onClick={handleLoadMore}
                      style={{ padding: "6px 16px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 20, color: "#A3A3A3", cursor: "pointer", fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; e.currentTarget.style.color = "#F97316"; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "#A3A3A3"; }}
                    >
                      ↑ Carregar {Math.min(PAGE_SIZE, messages.length - displayCount)} mensagem(ns) anteriores
                    </button>
                  </div>
                )}
                {messages.slice(-displayCount).map(msg => <ChatMessage key={msg.id} msg={msg} />)}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input */}
          <div style={{ padding: "12px 16px", borderTop: "1px solid #27272A", display: "flex", gap: 10 }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!selectedAgent || sending}
              placeholder={selectedAgent ? `Envie um comando para ${selectedAgent.name}... (Enter para enviar)` : "Selecione um agente acima"}
              rows={2}
              style={{ flex: 1, padding: "10px 14px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", resize: "none", lineHeight: 1.5, transition: "border-color 0.2s" }}
              onFocus={e => e.target.style.borderColor = "#F97316"}
              onBlur={e => e.target.style.borderColor = "#27272A"}
            />
            <button
              onClick={() => handleSend()}
              disabled={!selectedAgent || sending || !input.trim()}
              style={{
                padding: "10px 18px",
                background: (!selectedAgent || sending || !input.trim()) ? "#1A1A1A" : "#F97316",
                color: (!selectedAgent || sending || !input.trim()) ? "#404040" : "white",
                border: "1px solid",
                borderColor: (!selectedAgent || sending || !input.trim()) ? "#27272A" : "#F97316",
                borderRadius: 10,
                cursor: (!selectedAgent || sending || !input.trim()) ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: 7,
                fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14,
                transition: "all 0.2s",
                boxShadow: (!selectedAgent || sending || !input.trim()) ? "none" : "0 0 12px rgba(249,115,22,0.3)",
                alignSelf: "flex-end",
              }}
            >
              {sending
                ? <RefreshCw size={16} style={{ animation: "spin 0.8s linear infinite" }} />
                : <Send size={16} />}
              {sending ? "Aguarde..." : "Enviar"}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </Layout>
  );
}

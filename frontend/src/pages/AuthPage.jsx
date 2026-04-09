import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Zap, Eye, EyeOff, ArrowRight, Mail, Lock, User } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

function formatError(detail) {
  if (!detail) return "Algo deu errado. Tente novamente.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(e => e?.msg || JSON.stringify(e)).filter(Boolean).join(" ");
  if (detail?.msg) return detail.msg;
  return String(detail);
}

export default function AuthPage({ mode = "login" }) {
  const [tab, setTab] = useState(mode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { login, register, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || "/dashboard";

  useEffect(() => { if (user) navigate(from, { replace: true }); }, [user, navigate, from]);
  useEffect(() => { setTab(mode); }, [mode]);
  useEffect(() => { setError(""); }, [tab]);

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogle = () => {
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        if (!name.trim()) { setError("Nome é obrigatório"); setLoading(false); return; }
        await register(name, email, password);
      }
      navigate(from, { replace: true });
    } catch (err) {
      setError(formatError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A", display: "flex" }}>
      {/* Left panel */}
      <div style={{ flex: 1, display: "none", background: "linear-gradient(135deg, rgba(249,115,22,0.1) 0%, #0A0A0A 100%)", borderRight: "1px solid #27272A", padding: 48, flexDirection: "column", justifyContent: "space-between", "@media (min-width: 768px)": { display: "flex" } }} className="auth-left">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 34, height: 34, background: "linear-gradient(135deg, #F97316, #EA580C)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Zap size={18} color="white" />
          </div>
          <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 18, color: "white" }}>GapHub <span style={{ color: "#F97316" }}>AI</span></span>
        </div>
        <div>
          <h2 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 40, color: "white", lineHeight: 1.1, letterSpacing: "-0.03em", marginBottom: 20 }}>
            Seus agentes de IA<br />trabalham enquanto<br /><span className="gradient-text">você descansa</span>
          </h2>
          <p style={{ color: "#737373", fontSize: 16, lineHeight: 1.7 }}>Automatize todo o seu CRM ClickMassa com agentes inteligentes conectados a múltiplas ferramentas.</p>
        </div>
        <div style={{ color: "#737373", fontSize: 13 }}>© 2025 GapHub AI</div>
      </div>

      {/* Right panel - form */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{ width: "100%", maxWidth: 400 }}>
          {/* Mobile logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 40, justifyContent: "center" }}>
            <div style={{ width: 34, height: 34, background: "linear-gradient(135deg, #F97316, #EA580C)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Zap size={18} color="white" />
            </div>
            <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 20, color: "white" }}>GapHub <span style={{ color: "#F97316" }}>AI</span></span>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", background: "#1A1A1A", borderRadius: 10, padding: 4, marginBottom: 28, border: "1px solid #27272A" }}>
            {["login", "register"].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                data-testid={`tab-${t}`}
                style={{ flex: 1, padding: "9px 0", borderRadius: 7, border: "none", cursor: "pointer", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, transition: "all 0.2s", background: tab === t ? "#F97316" : "transparent", color: tab === t ? "white" : "#737373" }}
              >
                {t === "login" ? "Entrar" : "Criar conta"}
              </button>
            ))}
          </div>

          {/* Google button */}
          <button
            onClick={handleGoogle}
            data-testid="google-auth-btn"
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, padding: "12px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 10, color: "white", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif", fontSize: 14, fontWeight: 500, marginBottom: 20, transition: "all 0.2s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.background = "#2A2A2A"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.background = "#1A1A1A"; }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            {tab === "login" ? "Entrar com Google" : "Registrar com Google"}
          </button>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <div style={{ flex: 1, height: 1, background: "#27272A" }} />
            <span style={{ fontSize: 12, color: "#737373" }}>ou</span>
            <div style={{ flex: 1, height: 1, background: "#27272A" }} />
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} data-testid="auth-form">
            {tab === "register" && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Nome</label>
                <div style={{ position: "relative" }}>
                  <User size={16} style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#737373" }} />
                  <input
                    data-testid="name-input"
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="Seu nome completo"
                    style={{ width: "100%", padding: "11px 14px 11px 40px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box", transition: "border-color 0.2s" }}
                    onFocus={e => e.target.style.borderColor = "#F97316"}
                    onBlur={e => e.target.style.borderColor = "#27272A"}
                  />
                </div>
              </div>
            )}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Email</label>
              <div style={{ position: "relative" }}>
                <Mail size={16} style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#737373" }} />
                <input
                  data-testid="email-input"
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  required
                  style={{ width: "100%", padding: "11px 14px 11px 40px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box", transition: "border-color 0.2s" }}
                  onFocus={e => e.target.style.borderColor = "#F97316"}
                  onBlur={e => e.target.style.borderColor = "#27272A"}
                />
              </div>
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#A3A3A3", marginBottom: 6 }}>Senha</label>
              <div style={{ position: "relative" }}>
                <Lock size={16} style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#737373" }} />
                <input
                  data-testid="password-input"
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={6}
                  style={{ width: "100%", padding: "11px 40px 11px 40px", background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 8, color: "white", fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif", outline: "none", boxSizing: "border-box", transition: "border-color 0.2s" }}
                  onFocus={e => e.target.style.borderColor = "#F97316"}
                  onBlur={e => e.target.style.borderColor = "#27272A"}
                />
                <button type="button" onClick={() => setShowPass(s => !s)} style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#737373", cursor: "pointer" }}>
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div data-testid="auth-error" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, color: "#EF4444", fontSize: 13 }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              data-testid="auth-submit-btn"
              disabled={loading}
              style={{ width: "100%", padding: "12px", background: loading ? "#404040" : "#F97316", color: "white", border: "none", borderRadius: 10, fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 15, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "all 0.2s", boxShadow: loading ? "none" : "0 0 16px rgba(249,115,22,0.3)" }}
            >
              {loading ? (
                <div style={{ width: 18, height: 18, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
              ) : (
                <>{tab === "login" ? "Entrar na plataforma" : "Criar minha conta"} <ArrowRight size={16} /></>
              )}
            </button>
          </form>

          <p style={{ textAlign: "center", marginTop: 20, fontSize: 13, color: "#737373" }}>
            {tab === "login" ? "Não tem conta? " : "Já tem conta? "}
            <button onClick={() => setTab(tab === "login" ? "register" : "login")} style={{ background: "none", border: "none", color: "#F97316", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
              {tab === "login" ? "Criar agora" : "Entrar"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

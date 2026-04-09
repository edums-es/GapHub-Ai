import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Zap, ArrowRight, Bot, Database, Layers, Shield, CheckCircle, Star, ChevronRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const FEATURES = [
  { icon: Bot, title: "Agentes Autônomos", desc: "IA que opera o CRM sozinha — lê tickets, responde leads, cria tarefas e muito mais sem intervenção humana." },
  { icon: Database, title: "ClickMassa CRM Nativo", desc: "Integração total via API administrativa. Envie mensagens sem consumir créditos, gerencie funis e automações." },
  { icon: Layers, title: "Flow Builder Visual", desc: "Conecte MCPs e ferramentas em um canvas visual. Configure LLMs, tools e triggers com drag & drop." },
  { icon: Shield, title: "Multi-tenant Seguro", desc: "Cada cliente tem seu workspace isolado com credenciais criptografadas e histórico de execuções separado." },
];

const STATS = [
  { value: "20+", label: "Tools ClickMassa" },
  { value: "3", label: "Providers de LLM" },
  { value: "100%", label: "Admin Mode" },
  { value: "Multi", label: "Tenant Ready" },
];

export default function LandingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0A0A0A", fontFamily: "IBM Plex Sans, sans-serif" }}>
      {/* Header */}
      <header style={{ position: "sticky", top: 0, zIndex: 50, background: "rgba(10,10,10,0.85)", backdropFilter: "blur(16px)", borderBottom: "1px solid #27272A" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 24px", height: 64, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 34, height: 34, background: "linear-gradient(135deg, #F97316, #EA580C)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 16px rgba(249,115,22,0.4)" }}>
              <Zap size={18} color="white" />
            </div>
            <span style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 18, color: "white", letterSpacing: "-0.03em" }}>GapHub <span style={{ color: "#F97316" }}>AI</span></span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {user ? (
              <button onClick={() => navigate("/dashboard")} data-testid="goto-dashboard-btn" style={{ padding: "8px 20px", background: "#F97316", color: "white", border: "none", borderRadius: 8, fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, cursor: "pointer" }}>
                Dashboard
              </button>
            ) : (
              <>
                <Link to="/login" data-testid="login-link" style={{ color: "#A3A3A3", textDecoration: "none", fontSize: 14, fontWeight: 500 }}>Entrar</Link>
                <Link to="/register" data-testid="register-link" style={{ padding: "8px 20px", background: "#F97316", color: "white", borderRadius: 8, textDecoration: "none", fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 14, boxShadow: "0 0 10px rgba(249,115,22,0.3)" }}>
                  Começar grátis
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section style={{ position: "relative", minHeight: "90vh", display: "flex", alignItems: "center", overflow: "hidden" }}>
        {/* BG */}
        <div style={{ position: "absolute", inset: 0, backgroundImage: `url(https://images.unsplash.com/photo-1698847036555-3fbd00ec6946?crop=entropy&cs=srgb&fm=jpg&q=85&w=1920)`, backgroundSize: "cover", backgroundPosition: "center", opacity: 0.06 }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 60% 50%, rgba(249,115,22,0.08) 0%, transparent 70%)" }} />

        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "80px 24px" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 100, padding: "6px 14px", marginBottom: 32 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: "#F97316" }}>Novo</span>
            <span style={{ fontSize: 13, color: "#A3A3A3" }}>Agentes de IA para o ClickMassa CRM</span>
          </div>

          <h1 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 900, fontSize: "clamp(40px, 6vw, 72px)", lineHeight: 1.05, letterSpacing: "-0.04em", color: "white", maxWidth: 800, marginBottom: 24 }}>
            Transforme seu CRM em um{" "}
            <span className="gradient-text">Motor de IA</span>
            {" "}Autônomo
          </h1>

          <p style={{ fontSize: "clamp(16px, 2vw, 20px)", color: "#A3A3A3", maxWidth: 560, lineHeight: 1.7, marginBottom: 48 }}>
            Crie agentes de IA com ultrapoderes que operam o ClickMassa sozinhos — gerenciam tickets, enviam mensagens, movem leads e muito mais, 24/7.
          </p>

          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <button
              onClick={() => navigate("/register")}
              data-testid="hero-cta-btn"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 28px", background: "#F97316", color: "white", border: "none", borderRadius: 10, fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, cursor: "pointer", boxShadow: "0 0 24px rgba(249,115,22,0.4)", transition: "all 0.2s" }}
              onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 0 36px rgba(249,115,22,0.6)"; }}
              onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "0 0 24px rgba(249,115,22,0.4)"; }}
            >
              Criar meu agente <ArrowRight size={18} />
            </button>
            <button
              onClick={handleGoogleLogin}
              data-testid="hero-google-btn"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 28px", background: "transparent", color: "white", border: "1px solid #27272A", borderRadius: 10, fontFamily: "Outfit, sans-serif", fontWeight: 600, fontSize: 15, cursor: "pointer", transition: "all 0.2s" }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "#F97316"; e.currentTarget.style.color = "#F97316"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.color = "white"; }}
            >
              Entrar com Google
            </button>
          </div>

          {/* Stats */}
          <div style={{ display: "flex", gap: 40, marginTop: 64, flexWrap: "wrap" }}>
            {STATS.map(({ value, label }) => (
              <div key={label}>
                <div style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 32, color: "#F97316", lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 13, color: "#737373", marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 24px" }}>
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.2em", textTransform: "uppercase", color: "#F97316", marginBottom: 12 }}>Funcionalidades</div>
          <h2 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: "clamp(28px, 4vw, 44px)", color: "white", letterSpacing: "-0.03em" }}>
            Poder total no CRM
          </h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          {FEATURES.map(({ icon: Icon, title, desc }, i) => (
            <div
              key={title}
              style={{ background: "#1A1A1A", border: "1px solid #27272A", borderRadius: 12, padding: 28, transition: "all 0.2s ease", animationDelay: `${i * 0.1}s` }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; e.currentTarget.style.transform = "translateY(-4px)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#27272A"; e.currentTarget.style.transform = ""; }}
            >
              <div style={{ width: 44, height: 44, background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
                <Icon size={22} color="#F97316" />
              </div>
              <h3 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 18, color: "white", marginBottom: 10 }}>{title}</h3>
              <p style={{ fontSize: 14, color: "#737373", lineHeight: 1.7 }}>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "0 24px 80px" }}>
        <div style={{ background: "linear-gradient(135deg, rgba(249,115,22,0.15) 0%, rgba(249,115,22,0.05) 100%)", border: "1px solid rgba(249,115,22,0.2)", borderRadius: 16, padding: "48px 40px", textAlign: "center" }}>
          <h2 style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: "clamp(24px, 3vw, 36px)", color: "white", letterSpacing: "-0.03em", marginBottom: 16 }}>
            Pronto para automatizar com IA?
          </h2>
          <p style={{ fontSize: 16, color: "#A3A3A3", marginBottom: 32 }}>Comece agora e crie seu primeiro agente em minutos.</p>
          <button
            onClick={() => navigate("/register")}
            data-testid="bottom-cta-btn"
            style={{ padding: "14px 36px", background: "#F97316", color: "white", border: "none", borderRadius: 10, fontFamily: "Outfit, sans-serif", fontWeight: 700, fontSize: 16, cursor: "pointer", boxShadow: "0 0 20px rgba(249,115,22,0.4)", transition: "all 0.2s" }}
            onMouseEnter={e => e.currentTarget.style.transform = "translateY(-2px)"}
            onMouseLeave={e => e.currentTarget.style.transform = ""}
          >
            Começar agora — é grátis
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: "1px solid #27272A", padding: "24px", textAlign: "center" }}>
        <p style={{ fontSize: 13, color: "#737373" }}>© 2025 GapHub AI — Plataforma de Agentes para ClickMassa CRM</p>
      </footer>
    </div>
  );
}

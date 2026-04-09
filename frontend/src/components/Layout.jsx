import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  LayoutDashboard, Bot, Store, Play, Settings, LogOut,
  ChevronLeft, ChevronRight, Zap, User, Menu, X, Calendar, Shield, MessageSquare
} from "lucide-react";

const NAV_ITEMS = [
  { path: "/dashboard",  label: "Dashboard",    icon: LayoutDashboard },
  { path: "/agents",     label: "Meus Agentes", icon: Bot },
  { path: "/chat",       label: "Chat",         icon: MessageSquare },
  { path: "/marketplace",label: "Marketplace",  icon: Store },
  { path: "/schedules",  label: "Agendamentos", icon: Calendar },
  { path: "/runs",       label: "Execuções",    icon: Play },
  { path: "/settings",   label: "Configurações",icon: Settings },
];

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  const sidebarContent = (
    <>
      {/* Logo */}
      <div style={{ padding: collapsed ? "20px 16px" : "20px 20px", borderBottom: "1px solid #27272A", display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, background: "linear-gradient(135deg, #F97316, #EA580C)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 0 12px rgba(249,115,22,0.4)" }}>
          <Zap size={18} color="white" />
        </div>
        {!collapsed && (
          <div>
            <div style={{ fontFamily: "Outfit, sans-serif", fontWeight: 800, fontSize: 16, color: "white", letterSpacing: "-0.03em" }}>GapHub</div>
            <div style={{ fontSize: 10, color: "#F97316", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase" }}>AI Platform</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "12px 8px", display: "flex", flexDirection: "column", gap: 4 }}>
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path || (path !== "/dashboard" && location.pathname.startsWith(path));
          return (
            <Link
              key={path}
              to={path}
              data-testid={`nav-${path.replace("/", "")}`}
              onClick={() => setMobileOpen(false)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: collapsed ? "10px 12px" : "10px 12px",
                borderRadius: 8,
                textDecoration: "none",
                transition: "all 0.2s ease",
                background: active ? "rgba(249, 115, 22, 0.15)" : "transparent",
                border: active ? "1px solid rgba(249, 115, 22, 0.3)" : "1px solid transparent",
                color: active ? "#F97316" : "#A3A3A3",
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = "#1A1A1A"; e.currentTarget.style.color = "white"; }}}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#A3A3A3"; }}}
            >
              <Icon size={18} style={{ flexShrink: 0 }} />
              {!collapsed && <span style={{ fontFamily: "IBM Plex Sans, sans-serif", fontSize: 14, fontWeight: 500 }}>{label}</span>}
            </Link>
          );
        })}
        {/* Admin link — only for super_admin */}
        {user?.role === "super_admin" && (() => {
          const active = location.pathname === "/admin";
          return (
            <Link
              to="/admin"
              data-testid="nav-admin"
              onClick={() => setMobileOpen(false)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px",
                borderRadius: 8,
                textDecoration: "none",
                transition: "all 0.2s ease",
                background: active ? "rgba(249, 115, 22, 0.15)" : "transparent",
                border: active ? "1px solid rgba(249, 115, 22, 0.3)" : "1px solid transparent",
                color: active ? "#F97316" : "#A3A3A3",
                marginTop: 4,
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = "#1A1A1A"; e.currentTarget.style.color = "white"; }}}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#A3A3A3"; }}}
            >
              <Shield size={18} style={{ flexShrink: 0 }} />
              {!collapsed && <span style={{ fontFamily: "IBM Plex Sans, sans-serif", fontSize: 14, fontWeight: 500 }}>Admin Panel</span>}
            </Link>
          );
        })()}
      </nav>

      {/* User */}
      <div style={{ padding: "12px 8px", borderTop: "1px solid #27272A" }}>
        {!collapsed && (
          <div style={{ padding: "8px 12px", marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, background: "linear-gradient(135deg, #F97316, #EA580C)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              {user?.avatar ? <img src={user.avatar} alt="" style={{ width: 28, height: 28, borderRadius: "50%" }} /> : <User size={14} color="white" />}
            </div>
            <div style={{ overflow: "hidden" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "white", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{user?.name || "Usuário"}</div>
              <div style={{ fontSize: 10, color: "#737373", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{user?.email}</div>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          data-testid="logout-btn"
          style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: collapsed ? "10px 12px" : "10px 12px", borderRadius: 8, background: "transparent", border: "1px solid transparent", color: "#A3A3A3", cursor: "pointer", transition: "all 0.2s ease" }}
          onMouseEnter={e => { e.currentTarget.style.background = "rgba(239, 68, 68, 0.1)"; e.currentTarget.style.color = "#EF4444"; e.currentTarget.style.borderColor = "rgba(239, 68, 68, 0.2)"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#A3A3A3"; e.currentTarget.style.borderColor = "transparent"; }}
        >
          <LogOut size={18} style={{ flexShrink: 0 }} />
          {!collapsed && <span style={{ fontFamily: "IBM Plex Sans, sans-serif", fontSize: 14, fontWeight: 500 }}>Sair</span>}
        </button>
      </div>
    </>
  );

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0A0A0A", overflow: "hidden" }}>
      {/* Desktop Sidebar */}
      <div style={{
        width: collapsed ? 60 : 220,
        background: "#0A0A0A",
        borderRight: "1px solid #27272A",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.25s ease",
        position: "relative",
        flexShrink: 0,
        zIndex: 40,
      }}>
        {sidebarContent}
        <button
          onClick={() => setCollapsed(c => !c)}
          style={{ position: "absolute", right: -12, top: 72, width: 24, height: 24, background: "#1A1A1A", border: "1px solid #27272A", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#A3A3A3", zIndex: 50 }}
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100 }} onClick={() => setMobileOpen(false)}>
          <div style={{ width: 240, height: "100%", background: "#0A0A0A", borderRight: "1px solid #27272A", display: "flex", flexDirection: "column" }} onClick={e => e.stopPropagation()}>
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Main content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {/* Top header */}
        <div style={{ height: 56, background: "rgba(10,10,10,0.8)", backdropFilter: "blur(12px)", borderBottom: "1px solid #27272A", display: "flex", alignItems: "center", padding: "0 20px", gap: 16, flexShrink: 0 }}>
          <button onClick={() => setMobileOpen(true)} style={{ background: "none", border: "none", color: "#A3A3A3", cursor: "pointer", display: "none" }}>
            <Menu size={20} />
          </button>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(249, 115, 22, 0.1)", border: "1px solid rgba(249, 115, 22, 0.2)", borderRadius: 6, padding: "4px 10px" }}>
            <div style={{ width: 6, height: 6, background: "#F97316", borderRadius: "50%", boxShadow: "0 0 6px #F97316" }} />
            <span style={{ fontSize: 12, color: "#F97316", fontFamily: "Outfit, sans-serif", fontWeight: 600 }}>
              {user?.workspace?.name || "Workspace"}
            </span>
          </div>
        </div>

        {/* Page content */}
        <div style={{ flex: 1, overflow: "auto", padding: 24 }}>
          {children}
        </div>
      </div>
    </div>
  );
}

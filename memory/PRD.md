# GapHub AI — PRD

## Problem Statement
Plataforma web multi-tenant para criar Agentes de IA autônomos que se comunicam diretamente com o CRM ClickMassa via MCP (Model Context Protocol), conectando-se a outras ferramentas via flow builder híbrido. Cada tenant (cliente do franqueado) fornece suas credenciais do ClickMassa e pode criar agentes que operam o CRM de forma autônoma com diferentes providers de LLM.

## Architecture
- **Frontend**: React (Vite-like CRA) — dark mode, orange theme (#F97316), Outfit + IBM Plex Sans
- **Backend**: FastAPI (Python) — `/app/backend/`
- **Database**: MongoDB — DB: `gaphub_ai`
- **Auth**: JWT email/password + Emergent Google OAuth

## Core Requirements (Static)
- Multi-tenant workspaces isolados
- Auth dual: email/senha + Google OAuth
- Agent Builder com flow builder visual (canvas drag-and-drop)
- MCP Marketplace estilo Cline
- Múltiplos providers de LLM: OpenAI, Anthropic, Gemini
- Credenciais criptografadas por workspace por MCP
- Execução de agentes com ferramenta ClickMassa CRM
- Histórico de execuções com steps detalhados
- ClickMassa: acesso completo via email/senha admin

## What's Been Implemented (2025-04)

### Backend
- `server.py` — FastAPI app, CORS, lifespan, health endpoint
- `auth.py` — JWT email/senha, Google OAuth (Emergent), brute force protection, admin seeding
- `agents.py` — Agent CRUD, Credential CRUD (criptografado Fernet), Agent Execution (LiteLLM multi-provider com tool calling), Run history, Dashboard stats, Workspace routes
- `marketplace.py` — Catálogo estático de 11 MCPs (3 ativos: ClickMassa, Web Search, HTTP Request; 8 coming soon)
- `tools.py` — Executor de ferramentas ClickMassa (23 tools), Web Search, HTTP Request; builder de tool_definitions para LiteLLM

### Frontend
- `LandingPage.jsx` — Marketing page com hero, features, stats, CTA
- `AuthPage.jsx` — Login/Register com email+senha e Google OAuth
- `Dashboard.jsx` — Stats cards + recentes agentes + recentes execuções
- `AgentBuilder.jsx` — Canvas visual drag-and-drop, nodes coloridos (Trigger/LLM/Tool/Output), SVG bezier connections, painel config lateral, modal de execução
- `Marketplace.jsx` — Grid de MCPs com categorias, busca, modal de instalação/credenciais
- `MyAgents.jsx` — Cards com status, LLM badge, toggle ativo/inativo, CRUD
- `RunHistory.jsx` — Accordion com steps de ferramentas, input, output, duração
- `Settings.jsx` — Perfil, workspace stats, credenciais por MCP
- `Layout.jsx` — Sidebar colapsável, header com workspace badge

## Prioritized Backlog

### P0 — Crítico
- [ ] Adicionar agente direto ao painel de agente sem precisar ir via "Novo Agente"

### P1 — Importante
- [ ] Execução periódica/agendada de agentes (scheduler)
- [ ] Webhook trigger (agent ativado por webhook externo)
- [ ] N8N MCP integration (orquestração externa)
- [ ] WhatsApp Evolution API (MCP ativo)
- [ ] Google Calendar (MCP ativo)
- [ ] Gmail (MCP ativo)
- [ ] Agent templates (pre-built para casos de uso comuns)
- [ ] Admin Panel (super admin — gerenciar todos tenants)
- [ ] Billing/planos (free/pro/enterprise)

### P2 — Melhorias
- [ ] Streaming de respostas (Server-Sent Events)
- [ ] Logs em tempo real durante execução
- [ ] Partilha de agentes entre workspaces
- [ ] Export/import de agentes como JSON
- [ ] Rate limiting por workspace
- [ ] Brute force threshold: baixar de 10 para 5

## Next Tasks
1. Implementar N8N Webhook MCP
2. Adicionar WhatsApp Evolution API como MCP ativo
3. Criar admin panel para super admin gerenciar tenants
4. Adicionar scheduler para execuções automáticas

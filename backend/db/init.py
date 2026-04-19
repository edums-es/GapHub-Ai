"""
backend/db/init.py — Inicialização do banco MongoDB com índices e coleções.

Execute diretamente:
    python backend/db/init.py

Ou importe e chame create_indexes(db) no startup do FastAPI (já feito em server.py).
Também insere os 6 templates de agentes do marketplace se ainda não existirem.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Permite execução standalone fora do contexto do servidor
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
import pymongo

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def create_indexes(db):
    """
    Cria todos os índices necessários para o GapHub AI.
    Seguro para rodar múltiplas vezes (idempotente).
    """
    logger.info("Criando índices MongoDB...")

    # ── users ──────────────────────────────────────────────────────────────
    await db.users.create_index("email", unique=True, name="users_email_unique")
    await db.users.create_index("workspace_id", name="users_workspace_id")

    # ── agents ─────────────────────────────────────────────────────────────
    await db.agents.create_index(
        [("workspace_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
        name="agents_workspace_status"
    )
    await db.agents.create_index(
        [("workspace_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        name="agents_workspace_created"
    )
    await db.agents.create_index("agent_id", unique=True, name="agents_agent_id_unique")

    # ── marketplace_templates ───────────────────────────────────────────────
    await db.marketplace_templates.create_index(
        [("category", pymongo.ASCENDING), ("active", pymongo.ASCENDING)],
        name="marketplace_category_active"
    )
    await db.marketplace_templates.create_index("id", unique=True, name="marketplace_id_unique")

    # ── mcp_credentials ────────────────────────────────────────────────────
    await db.mcp_credentials.create_index(
        "agent_id", unique=True, name="mcp_credentials_agent_id_unique"
    )
    await db.mcp_credentials.create_index("workspace_id", name="mcp_credentials_workspace_id")

    # ── credentials (legado — workspace-level) ─────────────────────────────
    await db.credentials.create_index(
        [("workspace_id", pymongo.ASCENDING), ("mcp_id", pymongo.ASCENDING)],
        name="credentials_workspace_mcp"
    )

    # ── conversations / chat_sessions ──────────────────────────────────────
    await db.chat_sessions.create_index(
        [("agent_id", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)],
        name="chat_sessions_agent_created"
    )
    # TTL de 90 dias para conversas antigas
    await db.chat_sessions.create_index(
        "updated_at",
        expireAfterSeconds=90 * 24 * 3600,
        name="chat_sessions_ttl_90d"
    )

    # ── webhook_locks — lock atômico por ticket (evita race condition) ────
    # Lock único por (agent_id + ticket). TTL de 90s garante limpeza automática.
    await db.webhook_locks.create_index(
        "lock_key", unique=True, name="webhook_locks_key_unique"
    )
    await db.webhook_locks.create_index(
        "expires_at",
        expireAfterSeconds=0,  # MongoDB deleta quando expires_at < now
        name="webhook_locks_ttl"
    )

    # ── webhook_dedup — deduplicação de mensagens (TTL 24h) ───────────────
    await db.webhook_dedup.create_index(
        [("msg_id", pymongo.ASCENDING), ("agent_id", pymongo.ASCENDING)],
        unique=True, name="webhook_dedup_msg_agent"
    )
    await db.webhook_dedup.create_index(
        "created_at",
        expireAfterSeconds=24 * 3600,  # remove automaticamente após 24h
        name="webhook_dedup_ttl_24h"
    )

    # ── runs ───────────────────────────────────────────────────────────────
    await db.runs.create_index(
        [("agent_id", pymongo.ASCENDING), ("started_at", pymongo.DESCENDING)],
        name="runs_agent_started"
    )
    await db.runs.create_index(
        [("workspace_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
        name="runs_workspace_status"
    )

    # ── schedules ──────────────────────────────────────────────────────────
    await db.schedules.create_index(
        [("workspace_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        name="schedules_workspace_created"
    )
    await db.schedules.create_index("active", name="schedules_active")

    # ── workflows ──────────────────────────────────────────────────────────
    await db.workflows.create_index("workflow_id", unique=True, name="workflows_id_unique")
    await db.workflows.create_index(
        [("workspace_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        name="workflows_workspace_created"
    )

    # ── user_sessions / login_attempts (auth) ──────────────────────────────
    await db.user_sessions.create_index("session_token", name="user_sessions_token")
    await db.login_attempts.create_index("identifier", name="login_attempts_identifier")

    logger.info("✅ Índices criados com sucesso.")


async def seed_marketplace_templates(db):
    """
    Insere os 6 templates de agentes padrão no MongoDB se não existirem.
    Lê o arquivo seeds/marketplace.json.
    """
    seeds_path = Path(__file__).parent / "seeds" / "marketplace.json"
    if not seeds_path.exists():
        logger.warning(f"Arquivo de seeds não encontrado: {seeds_path}")
        return

    with open(seeds_path, "r", encoding="utf-8") as f:
        templates = json.load(f)

    inserted = 0
    for tmpl in templates:
        existing = await db.marketplace_templates.find_one({"id": tmpl["id"]})
        if not existing:
            tmpl["created_at"] = datetime.now(timezone.utc)
            tmpl["updated_at"] = datetime.now(timezone.utc)
            tmpl.setdefault("active", True)
            tmpl.setdefault("installs", 0)
            tmpl.setdefault("rating", 0)
            await db.marketplace_templates.insert_one(tmpl)
            inserted += 1

    if inserted > 0:
        logger.info(f"✅ {inserted} template(s) de marketplace inserido(s).")
    else:
        logger.info("Templates de marketplace já existem — nenhum inserido.")


async def init_db():
    """Ponto de entrada standalone para inicialização completa do banco."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "gaphub_ai")

    logger.info(f"Conectando ao MongoDB: {mongo_url} / {db_name}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    await create_indexes(db)
    await seed_marketplace_templates(db)

    client.close()
    logger.info("Inicialização do banco concluída.")


if __name__ == "__main__":
    asyncio.run(init_db())

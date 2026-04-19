from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from auth import auth_router, seed_admin
from agents import agents_router
from marketplace import marketplace_router
from admin import admin_router
from scheduler import scheduler_router, init_scheduler, stop_scheduler
from workflows_api import workflows_router, workflow_templates_router
from db.init import create_indexes as _create_indexes_full, seed_marketplace_templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

allowed_origins = {
    FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://gap-hub-ai.vercel.app",
    "https://gap-hub-ai-git-main-tarotbgs.vercel.app",
}

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db
    # Usa init.py completo com todos os índices e TTL
    await _create_indexes_full(db)
    await seed_admin(db)
    await seed_marketplace_templates(db)  # Insere os 6 templates padrão se ausentes
    await init_scheduler(db)
    logger.info("GapHub AI backend started")
    yield
    stop_scheduler()
    mongo_client.close()


app = FastAPI(title="GapHub AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(marketplace_router)
app.include_router(admin_router)
app.include_router(scheduler_router)
app.include_router(workflows_router)
app.include_router(workflow_templates_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "GapHub AI"}

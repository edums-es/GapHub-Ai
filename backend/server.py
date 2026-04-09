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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db
    await create_indexes(db)
    await seed_admin(db)
    logger.info("GapHub AI backend started")
    yield
    mongo_client.close()


async def create_indexes(db):
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token")
    await db.login_attempts.create_index("identifier")
    await db.agents.create_index([("workspace_id", 1), ("created_at", -1)])
    await db.credentials.create_index([("workspace_id", 1), ("mcp_id", 1)])
    await db.runs.create_index([("agent_id", 1), ("started_at", -1)])


app = FastAPI(title="GapHub AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(marketplace_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "GapHub AI"}

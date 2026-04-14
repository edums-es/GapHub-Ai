import os
import uuid
import bcrypt
import jwt
import secrets
import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

auth_router = APIRouter(prefix="/api/auth")


# ── Models ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    session_id: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Helpers ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request):
    db = request.app.state.db
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(request: Request):
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def seed_admin(db):
    email = os.environ.get("ADMIN_EMAIL", "admin@gaphub.ai")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing is None:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": "Admin",
            "password_hash": hash_password(password),
            "role": "super_admin",
            "workspace_id": ws_id,
            "auth_type": "email",
            "avatar": None,
            "created_at": datetime.now(timezone.utc),
        })
        await db.workspaces.insert_one({
            "workspace_id": ws_id,
            "name": "GapHub Admin",
            "owner_id": user_id,
            "plan": "enterprise",
            "created_at": datetime.now(timezone.utc),
        })
        logger.info(f"Admin seeded: {email}")

        # Write test credentials
        import pathlib
        creds_path = pathlib.Path("/app/memory/test_credentials.md")
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        creds_path.write_text(f"""# GapHub AI Test Credentials

## Admin Account
- Email: {email}
- Password: {password}
- Role: super_admin

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- POST /api/auth/refresh
- POST /api/auth/google-session
""")
    elif not verify_password(password, existing.get("password_hash", "")):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})


# ── Routes ───────────────────────────────────────────────────────────────────

@auth_router.post("/register")
async def register(request: Request, response: Response, body: RegisterRequest):
    db = request.app.state.db
    email = body.email.lower()
    if await db.users.find_one({"email": email}, {"_id": 0}):
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    ws_id = f"ws_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": body.name,
        "password_hash": hash_password(body.password),
        "role": "user",
        "workspace_id": ws_id,
        "auth_type": "email",
        "avatar": None,
        "created_at": datetime.now(timezone.utc),
    })
    await db.workspaces.insert_one({
        "workspace_id": ws_id,
        "name": f"Workspace de {body.name}",
        "owner_id": user_id,
        "plan": "free",
        "created_at": datetime.now(timezone.utc),
    })

    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    set_auth_cookies(response, access_token, refresh_token)
    return {"user_id": user_id, "email": email, "name": body.name, "role": "user", "workspace_id": ws_id}


@auth_router.post("/login")
async def login(request: Request, response: Response, body: LoginRequest):
    db = request.app.state.db
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"

    # Check brute force
    recent = await db.login_attempts.count_documents({
        "identifier": identifier,
        "attempted_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=15)},
    })
    if recent >= 10:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await db.login_attempts.insert_one({"identifier": identifier, "attempted_at": datetime.now(timezone.utc)})
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")

    await db.login_attempts.delete_many({"identifier": identifier})
    access_token = create_access_token(user["user_id"], email)
    refresh_token = create_refresh_token(user["user_id"])
    set_auth_cookies(response, access_token, refresh_token)
    user.pop("password_hash", None)
    return user


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Deslogado com sucesso"}


@auth_router.get("/me")
async def me(request: Request):
    user = await get_current_user(request)
    db = request.app.state.db
    workspace = await db.workspaces.find_one({"workspace_id": user.get("workspace_id")}, {"_id": 0})
    user["workspace"] = workspace
    return user


@auth_router.post("/refresh")
async def refresh(request: Request, response: Response):
    db = request.app.state.db
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(user["user_id"], user["email"])
        response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
        return {"message": "Token refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@auth_router.post("/google-session")
async def google_session(request: Request, response: Response, body: GoogleSessionRequest):
    db = request.app.state.db
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_id},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid session")
        data = resp.json()

    email = data["email"].lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user = existing
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "password_hash": None,
            "role": "user",
            "workspace_id": ws_id,
            "auth_type": "google",
            "avatar": data.get("picture"),
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one({**user})
        await db.workspaces.insert_one({
            "workspace_id": ws_id,
            "name": f"Workspace de {user['name']}",
            "owner_id": user_id,
            "plan": "free",
            "created_at": datetime.now(timezone.utc),
        })

    access_token = create_access_token(user["user_id"], email)
    refresh_token = create_refresh_token(user["user_id"])
    set_auth_cookies(response, access_token, refresh_token)
    user.pop("password_hash", None)
    user.pop("_id", None)
    return user


@auth_router.put("/profile")
async def update_profile(request: Request, body: dict):
    db = request.app.state.db
    user = await get_current_user(request)
    allowed = {k: v for k, v in body.items() if k in ["name", "avatar"]}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": allowed})
    return {"message": "Perfil atualizado"}

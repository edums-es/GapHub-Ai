"""
GapHub AI Backend API Tests
Tests for: health, auth, agents, marketplace, dashboard
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

EMAIL = "admin@gaphub.ai"
PASSWORD = "GapHub@2024"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_session(session):
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    return session


# ── Health ──────────────────────────────────────────────────────────────────

def test_health(session):
    resp = session.get(f"{BASE_URL}/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print("✓ Health check OK")


# ── Auth ──────────────────────────────────────────────────────────────────

def test_login_success(session):
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == EMAIL
    assert "user_id" in data
    assert "workspace_id" in data
    print(f"✓ Login OK: {data['email']}")


def test_login_invalid(session):
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": "wrongpassword"})
    assert resp.status_code == 401
    print("✓ Invalid login returns 401")


def test_me(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == EMAIL
    assert "workspace" in data
    print(f"✓ /me OK: {data['email']}")


def test_logout(session):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    resp = s.post(f"{BASE_URL}/api/auth/logout")
    assert resp.status_code == 200
    print("✓ Logout OK")


# ── Agents ──────────────────────────────────────────────────────────────────

def test_list_agents(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)
    print(f"✓ List agents OK: {len(data['agents'])} agents")


def test_create_agent(auth_session):
    resp = auth_session.post(f"{BASE_URL}/api/agents", json={"name": "TEST_Agent", "description": "Test agent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "TEST_Agent"
    assert "agent_id" in data
    assert "nodes" in data
    assert len(data["nodes"]) > 0
    print(f"✓ Create agent OK: {data['agent_id']}")
    return data["agent_id"]


def test_create_and_get_agent(auth_session):
    # Create
    resp = auth_session.post(f"{BASE_URL}/api/agents", json={"name": "TEST_GetAgent"})
    assert resp.status_code == 200
    agent_id = resp.json()["agent_id"]

    # Get
    resp2 = auth_session.get(f"{BASE_URL}/api/agents/{agent_id}")
    assert resp2.status_code == 200
    assert resp2.json()["agent_id"] == agent_id
    print(f"✓ Get agent OK: {agent_id}")


def test_update_agent(auth_session):
    resp = auth_session.post(f"{BASE_URL}/api/agents", json={"name": "TEST_UpdateAgent"})
    agent_id = resp.json()["agent_id"]

    resp2 = auth_session.put(f"{BASE_URL}/api/agents/{agent_id}", json={"description": "Updated description"})
    assert resp2.status_code == 200
    assert resp2.json()["description"] == "Updated description"
    print(f"✓ Update agent OK")


def test_delete_agent(auth_session):
    resp = auth_session.post(f"{BASE_URL}/api/agents", json={"name": "TEST_DeleteAgent"})
    agent_id = resp.json()["agent_id"]

    resp2 = auth_session.delete(f"{BASE_URL}/api/agents/{agent_id}")
    assert resp2.status_code == 200

    resp3 = auth_session.get(f"{BASE_URL}/api/agents/{agent_id}")
    assert resp3.status_code == 404
    print(f"✓ Delete agent OK")


# ── Dashboard Stats ──────────────────────────────────────────────────────────

def test_dashboard_stats(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data
    assert "active_agents" in data
    assert "total_runs" in data
    assert "success_rate" in data
    print(f"✓ Dashboard stats OK: {data['total_agents']} agents, {data['total_runs']} runs")


# ── Marketplace ──────────────────────────────────────────────────────────────

def test_marketplace_list(session):
    resp = session.get(f"{BASE_URL}/api/marketplace")
    assert resp.status_code == 200
    data = resp.json()
    assert "mcps" in data
    assert "categories" in data
    assert len(data["mcps"]) == 11
    assert len(data["categories"]) == 8
    print(f"✓ Marketplace OK: {len(data['mcps'])} MCPs, {len(data['categories'])} categories")


def test_marketplace_filter_by_category(session):
    resp = session.get(f"{BASE_URL}/api/marketplace?category=crm")
    assert resp.status_code == 200
    data = resp.json()
    assert all(m["category"] == "crm" for m in data["mcps"])
    print(f"✓ Marketplace filter OK")


def test_marketplace_get_mcp(session):
    resp = session.get(f"{BASE_URL}/api/marketplace/clickmassa")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "clickmassa"
    assert len(data["tools"]) > 0
    print(f"✓ Get MCP OK: {data['name']}")


# ── Runs ──────────────────────────────────────────────────────────────────

def test_list_runs(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    print(f"✓ List runs OK: {len(data['runs'])} runs")


# ── Credentials ──────────────────────────────────────────────────────────────

def test_list_credentials(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert "credentials" in data
    print(f"✓ List credentials OK")


def test_workspace(auth_session):
    resp = auth_session.get(f"{BASE_URL}/api/workspace")
    assert resp.status_code == 200
    data = resp.json()
    assert "workspace_id" in data
    print(f"✓ Workspace OK: {data.get('name')}")

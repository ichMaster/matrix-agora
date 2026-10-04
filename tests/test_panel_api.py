import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from panel.app import create_app

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client():
    return TestClient(create_app(token=TOKEN))


def test_the_panel_refuses_to_start_without_a_token():
    for bad in ("", "short"):
        with pytest.raises(RuntimeError, match="PANEL_TOKEN"):
            create_app(token=bad)


@pytest.mark.parametrize("path", ["/api/simulations", "/api/simulations/agora", "/api/agents", "/api/agents/ada",
                                  "/api/nonexistent"])
def test_every_api_path_needs_the_owner_token(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": TOKEN}).status_code == 401  # no "Bearer "


def test_with_the_token_the_registry_is_served(client):
    sims = client.get("/api/simulations", headers=AUTH).json()
    assert [s["id"] for s in sims] == ["agora"] and sims[0]["kind"] == "matrix-chat"
    agents = {a["name"]: a for a in client.get("/api/agents", headers=AUTH).json()}
    assert set(agents) == {"ada", "bruno"}
    assert (agents["ada"]["display"], agents["ada"]["role"]) == ("Ada", "editor, 32, Lviv")
    assert agents["bruno"]["simulation"] == "agora"


@pytest.mark.parametrize("path", ["/api/simulations/nowhere", "/api/agents/carol", "/api/agents/..%2F..%2Fetc"])
def test_unknown_names_are_404(client, path):
    assert client.get(path, headers=AUTH).status_code == 404


def test_no_route_mutates_anything(client):
    for route in client.app.routes:
        if isinstance(route, APIRoute):
            assert route.methods <= {"GET", "HEAD"}, route.path
    assert client.post("/api/agents/ada", headers=AUTH).status_code == 405
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404

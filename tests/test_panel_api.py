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
    assert set(agents) == {"ada", "bruno", "kit"}
    assert (agents["ada"]["display"], agents["ada"]["role"]) == ("Ada", "editor, 32, Lviv")
    assert agents["bruno"]["simulation"] == "agora"


@pytest.mark.parametrize("path", ["/api/simulations/nowhere", "/api/agents/carol", "/api/agents/..%2F..%2Fetc"])
def test_unknown_names_are_404(client, path):
    assert client.get(path, headers=AUTH).status_code == 404


def test_the_only_mutating_routes_are_the_v34_actions(client):
    mutating = {(route.path, frozenset(route.methods)) for route in client.app.routes
                if isinstance(route, APIRoute) and not route.methods <= {"GET", "HEAD"}}
    assert mutating == {("/api/agents/{name}/forget", frozenset({"POST"})),
                        ("/api/agents/{name}/{action}", frozenset({"POST"})),
                        ("/api/simulations/{sim_id}/services/{service}/{action}", frozenset({"POST"}))}
    assert client.put("/api/agents/ada/stop", headers=AUTH).status_code == 405
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


# --- v4.1: the agent view carries type, engine and capabilities ----------------------------------------------------
def test_the_agent_view_carries_type_engine_and_capabilities(client):
    ada = client.get("/api/agents/ada", headers=AUTH).json()
    assert (ada["type"], ada["engine"]) == ("persona", "gemini")
    assert ada["capabilities"] == sorted(["canon", "life", "summary", "chronicle", "plans", "today", "world"])
    assert {a["name"]: a["type"] for a in client.get("/api/agents", headers=AUTH).json()} == {
        "ada": "persona", "bruno": "persona", "kit": "creature"}


def _registry_with(tmp_path, kit_toml):
    from panel.registry import Registry
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "ada.toml").write_text('name = "Ада"\nuser_id = "@ada:agora.lan"\n[panel]\nname = "Ada"\n')
    (agents / "kit.toml").write_text(kit_toml)
    reg = tmp_path / "simulations.toml"
    reg.write_text('[agora]\nkind = "matrix-chat"\ntitle = "Agora"\nservices = ["homeserver"]\nagents = ["ada", "kit"]\n'
                   '[agora.health]\nservice = "homeserver"\nport = 8008\npath = "/x"\n'
                   '[agora.endpoints]\nhomeserver = "HOMESERVER"\nroom = "ROOM_ID"\n')
    return Registry(reg, agents)


def test_a_capability_less_agent_shows_no_memory_capabilities(tmp_path):
    reg = _registry_with(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\n'
                                   '[capabilities]\nsummary = false\nchronicle = false\nplans = false\ntoday = false\n'
                                   '[panel]\nname = "Kit"\npronoun = "it"\n')
    c = TestClient(create_app(token=TOKEN, registry=reg))
    kit = c.get("/api/agents/kit", headers=AUTH).json()
    assert kit["capabilities"] == ["canon", "life", "world"] and kit["pronoun"] == "it"
    assert c.get("/api/agents/kit").status_code == 401  # still token-gated
    assert c.get("/api/agents/nobody", headers=AUTH).status_code == 404


def test_a_broken_agent_toml_greys_its_card_not_the_panel(tmp_path):
    reg = _registry_with(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "dragon"\n')
    c = TestClient(create_app(token=TOKEN, registry=reg))
    kit = c.get("/api/agents/kit", headers=AUTH).json()
    assert kit["type"] == "unknown" and kit["capabilities"] == []
    assert c.get("/api/agents/ada", headers=AUTH).json()["type"] == "persona"

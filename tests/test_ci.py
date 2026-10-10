"""CI (v3.2): no secret but GITHUB_TOKEN, publishing only on push, the tag scheme the server relies on."""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
TEXT = WORKFLOW.read_text()
CI = yaml.safe_load(TEXT)


def test_the_only_secret_is_github_token():
    assert set(re.findall(r"secrets\.([A-Za-z_]+)", TEXT)) == {"GITHUB_TOKEN"}


def test_triggers_and_least_privilege():
    on = CI[True] if True in CI else CI["on"]  # YAML 1.1 reads the bare key `on` as True
    assert on["push"]["branches"] == ["main"] and on["push"]["tags"] == ["v*.*.*"] and "pull_request" in on
    assert CI["permissions"] == {"contents": "read"}
    assert CI["jobs"]["image"]["permissions"] == {"contents": "read", "packages": "write"}
    assert CI["jobs"]["image"]["needs"] == "gates"


def test_the_gates_match_the_mac():
    runs = " ".join(step.get("run", "") for step in CI["jobs"]["gates"]["steps"])
    for gate in ("uv run ruff check .", "uv run pytest",
                 "REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q"):
        assert gate in runs


def test_the_image_and_its_tags():
    steps = {s.get("id") or s["uses"].split("@")[0]: s for s in CI["jobs"]["image"]["steps"] if "uses" in s}
    meta = steps["meta"]["with"]
    assert meta["images"] == "ghcr.io/ichmaster/matrix-agora-${{ matrix.name }}"  # what server/docker-compose.yml pulls
    matrix = {m["name"]: (m["file"], m["target"]) for m in CI["jobs"]["image"]["strategy"]["matrix"]["include"]}
    assert matrix == {"agent": ("agents/Dockerfile", "agent"), "agent-claude": ("agents/Dockerfile", "claude"),
                      "panel": ("panel/Dockerfile", "")}  # v4.4: Claude's image is the `claude` target
    for tag in ("type=ref,event=tag", "value=latest", "value=edge", "type=sha"):
        assert tag in meta["tags"]
    build = steps["docker/build-push-action"]["with"]
    assert build["file"] == "${{ matrix.file }}" and build["push"] == "${{ github.event_name == 'push' }}"
    assert build["target"] == "${{ matrix.target }}"

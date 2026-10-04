"""The image holds no secrets and no lived state (v3.2): pinned through .dockerignore and the Dockerfile."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORED = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()
           if line.strip() and not line.startswith("#")}


def test_secrets_and_state_never_enter_the_build_context():
    for path in (".env", "server/.env", "server_con.yaml", "state/", "reports/", ".git/", ".claude/"):
        assert path in IGNORED, path


def test_the_dockerfile_copies_only_code_and_never_secrets():
    copies = [line.split()[1:] for line in (ROOT / "agents" / "Dockerfile").read_text().splitlines()
              if line.startswith("COPY ") and "--from=" not in line]
    sources = {src for args in copies for src in args[:-1]}
    assert sources == {"pyproject.toml", "uv.lock", "agents/"}

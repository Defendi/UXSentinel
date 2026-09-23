"""Testes herméticos para segurança do servidor e token efêmero (UXS-48 / UXS-49)."""

import pytest
from fastapi.testclient import TestClient

from uxsentinel_studio.server import (
    create_app,
    get_session_token,
)


@pytest.fixture
def client(tmp_path):
    app = create_app(project_dir=tmp_path)
    return TestClient(app)


def test_status_endpoint_is_public(client):
    """Garante que /api/status é acessível sem autenticação."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "studio_version" in data
    assert "core_version" in data


def test_index_injects_session_token(client):
    """Valida se o index.html recebe o token da URL para persistência no sessionStorage."""
    token = get_session_token()
    resp = client.get(f"/?token={token}")
    assert resp.status_code == 200
    assert token in resp.text
    assert "sessionStorage.setItem('studio_token'" in resp.text


def test_protected_routes_require_valid_token(client):
    """Testa rejeição 401 para requisições sem token ou com token inválido."""
    from fastapi import Depends

    from uxsentinel_studio.server import verify_studio_token

    # Registra endpoint de teste protegido
    app = client.app

    @app.get("/api/test-protected")
    async def protected_endpoint(token: str = Depends(verify_studio_token)):
        return {"authorized": True}

    # 1. Sem token -> 401
    r1 = client.get("/api/test-protected")
    assert r1.status_code == 401

    # 2. Token incorreto -> 401
    r2 = client.get("/api/test-protected", headers={"X-Studio-Token": "token_invalido"})
    assert r2.status_code == 401

    # 3. Token correto -> 200
    token = get_session_token()
    r3 = client.get("/api/test-protected", headers={"X-Studio-Token": token})
    assert r3.status_code == 200
    assert r3.json()["authorized"] is True


def test_spa_serves_index_with_full_layout(client):
    """Valida se o index.html da SPA carrega os elementos essenciais da interface em 3 colunas e o splitter redimensionável."""
    token = get_session_token()
    resp = client.get(f"/?token={token}")
    assert resp.status_code == 200
    assert "app-layout" in resp.text
    assert "yaml-code-editor" in resp.text
    assert "terminal-logs-window" in resp.text
    assert "sidebar" in resp.text
    assert "inspector-col" in resp.text
    assert "splitter-col2-col3" in resp.text


def test_spa_static_assets_delivery(client):
    """Valida entrega dos assets estáticos style.css e app.js com suporte a redimensionamento."""
    resp_css = client.get("/static/style.css")
    assert resp_css.status_code == 200
    assert "var(--bg-base)" in resp_css.text
    assert "col-splitter" in resp_css.text
    assert "--inspector-width" in resp_css.text

    resp_js = client.get("/static/app.js")
    assert resp_js.status_code == 200
    assert "initSessionToken" in resp_js.text
    assert "initColumnSplitter" in resp_js.text

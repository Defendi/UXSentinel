"""Testes unitários herméticos para o Motor de Crawling e Gerador de Cenários (UXS-12)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from uxsentinel.crawler.crawler import (
    Crawler,
    CrawlOptions,
    is_destructive_element,
    is_same_origin,
    normalize_url,
)
from uxsentinel.crawler.generator import ScenarioGenerator
from uxsentinel.scenarios.parser import load_scenario

# ==============================================================================
# 1. Same-Origin Policy e Normalização de URLs
# ==============================================================================


def test_is_same_origin():
    """Valida estritamente a conformidade com a Same-Origin Policy (esquema + host + porta)."""
    base = "https://app.empresa.com.br"

    assert is_same_origin(base, "https://app.empresa.com.br/dashboard") is True
    assert is_same_origin(base, "https://app.empresa.com.br:443/login") is True
    assert is_same_origin("http://localhost:8000", "http://localhost:8000/api/v1") is True

    # Diferente esquema
    assert is_same_origin(base, "http://app.empresa.com.br/dashboard") is False

    # Diferente subdomínio ou domínio
    assert is_same_origin(base, "https://auth.empresa.com.br") is False
    assert is_same_origin(base, "https://google.com") is False
    assert is_same_origin(base, "https://empresa.com.br") is False

    # Diferente porta
    assert is_same_origin("http://localhost:8000", "http://localhost:3000") is False

    # URLs malformadas
    assert is_same_origin(base, "invalid-url") is False


def test_normalize_url():
    """Valida normalização de URLs removendo fragmentos e padronizando trailing slashes."""
    assert normalize_url("https://exemplo.com/pagina/#secao") == "https://exemplo.com/pagina"
    assert normalize_url("https://exemplo.com/pagina/") == "https://exemplo.com/pagina"
    assert normalize_url("https://exemplo.com/") == "https://exemplo.com/"
    assert normalize_url("HTTPS://Exemplo.COM/Rota?a=1&b=2") == "https://exemplo.com/Rota?a=1&b=2"
    assert normalize_url("https://exemplo.com/rota#topo") == "https://exemplo.com/rota"


# ==============================================================================
# 2. Guardrails Anti-Ações Destrutivas
# ==============================================================================


@pytest.mark.parametrize(
    "text,classes,href,expected",
    [
        ("Excluir Usuário", "btn btn-primary", "/users/1", True),
        ("Delete account", "", "/account", True),
        ("Remover item", "table-action", "/items/1", True),
        ("Cancelar assinatura", "", "/billing", True),
        ("Mover para o Trash", "", "/docs/1", True),
        ("Logout do Sistema", "", "/auth/logout", True),
        ("Sair", "menu-item", "/logout", True),
        ("Desconectar conta", "", "/session", True),
        ("Apagar registro", "", "/record/1", True),
        ("Salvar Dados", "btn-danger", "/users/save", True),
        ("Excluir", ".btn-danger", "/remove", True),
        ("Dashboard Geral", "nav-link", "/dashboard", False),
        ("Clientes", "btn btn-secondary", "/clientes", False),
        ("Configurações", "settings-icon", "/config", False),
        ("Próxima Página", "pagination-next", "/page/2", False),
    ],
)
def test_is_destructive_element(text, classes, href, expected):
    """Garante que elementos com termos destrutivos ou classes de risco sejam bloqueados."""
    assert is_destructive_element(text=text, classes=classes, href=href) is expected


# ==============================================================================
# 3. Algoritmo BFS e Limites de Profundidade / Páginas
# ==============================================================================


@pytest.mark.asyncio
async def test_crawler_bfs_depth_and_page_limits(tmp_path: Path):
    """Testa se o BFS respeita rigorosamente max_depth e max_pages de forma hermética."""
    options = CrawlOptions(
        start_url="https://app.teste.local",
        max_depth=2,
        max_pages=3,
        generate_scenarios=False,
        output_dir=str(tmp_path / "crawl_out"),
        screenshot_evidence=False,
    )

    crawler = Crawler(options)

    # Simula mock do Playwright Page
    mock_page = AsyncMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    mock_page.title.return_value = "Página de Teste"

    # evaluate para checar saúde do body e depois extrair links
    # health check 1: body_text_len > 0
    # links evaluation: retorna 5 links em nível 1
    async def mock_evaluate(script, *args):
        if "innerText" in script and "document.body" in script:
            return 100
        if "children.length" in script:
            return 5
        if "querySelectorAll('a[href]')" in script:
            return [
                {"href": "/link1", "text": "Link 1", "className": ""},
                {"href": "/link2", "text": "Link 2", "className": ""},
                {"href": "/link3", "text": "Link 3", "className": ""},
                {"href": "/link4", "text": "Link 4", "className": ""},
            ]
        return None

    mock_page.evaluate.side_effect = mock_evaluate

    result = await crawler.run(page=mock_page)

    assert result["status"] == "completed"
    # Respeita o limite estrito de max_pages = 3
    assert result["visited_count"] == 3
    assert len(crawler.visited_urls) == 3
    assert "https://app.teste.local" in crawler.visited_urls


# ==============================================================================
# 4. Detecção de Falhas Graves e Rotina de Backtrack com Escalonamento
# ==============================================================================


@pytest.mark.asyncio
async def test_crawler_handles_http_500_with_successful_backtrack(tmp_path: Path):
    """Falha HTTP 500 com recuo bem-sucedido deve manter severidade 'alta'."""
    options = CrawlOptions(
        start_url="https://app.teste.local",
        max_depth=1,
        max_pages=5,
        generate_scenarios=False,
        output_dir=str(tmp_path),
        screenshot_evidence=False,
    )
    crawler = Crawler(options)

    mock_page = AsyncMock()
    # Primeira navegação: 200 OK com links
    # Segunda navegação: 500 Server Error
    resp_200 = MagicMock()
    resp_200.status = 200
    resp_500 = MagicMock()
    resp_500.status = 500

    mock_page.goto.side_effect = [resp_200, resp_500]
    mock_page.title.return_value = "Home"

    # go_back bem-sucedido
    back_resp = MagicMock()
    back_resp.status = 200
    mock_page.go_back.return_value = back_resp

    async def mock_evaluate(script, *args):
        if "querySelectorAll('a[href]')" in script:
            return [{"href": "/erro500", "text": "Erro 500", "className": ""}]
        if "innerText" in script:
            return 50
        return None

    mock_page.evaluate.side_effect = mock_evaluate

    result = await crawler.run(page=mock_page)

    assert len(result["errors"]) == 1
    err = result["errors"][0]
    assert err["error_type"] == "http_500"
    assert err["severity"] == "alta"
    assert err["backtrack_attempted"] is True
    assert err["backtrack_success"] is True


@pytest.mark.asyncio
async def test_crawler_escalates_to_bloqueante_when_backtrack_fails(tmp_path: Path):
    """Se o backtrack falhar ou travar, a severidade deve ser escalonada para 'bloqueante'."""
    options = CrawlOptions(
        start_url="https://app.teste.local",
        max_depth=1,
        max_pages=2,
        generate_scenarios=False,
        output_dir=str(tmp_path),
        screenshot_evidence=False,
    )
    crawler = Crawler(options)

    mock_page = AsyncMock()
    # Simula erro de navegação catastrófico (exceção Playwright)
    mock_page.goto.side_effect = Exception("net::ERR_CONNECTION_REFUSED")
    # go_back também falha / lança exceção
    mock_page.go_back.side_effect = Exception("Backtrack timeout / broken session")

    result = await crawler.run(page=mock_page)

    assert len(result["errors"]) == 1
    err = result["errors"][0]
    assert err["error_type"] == "navigation_error"
    # Escalonado para bloqueante porque o backtrack falhou!
    assert err["severity"] == "bloqueante"
    assert err["backtrack_attempted"] is True
    assert err["backtrack_success"] is False


@pytest.mark.asyncio
async def test_crawler_detects_blank_page(tmp_path: Path):
    """Detecta tela branca / corpo vazio e registra falha com rotina de recuo."""
    options = CrawlOptions(
        start_url="https://app.teste.local",
        max_depth=1,
        max_pages=1,
        generate_scenarios=False,
        output_dir=str(tmp_path),
        screenshot_evidence=False,
    )
    crawler = Crawler(options)

    mock_page = AsyncMock()
    resp_ok = MagicMock()
    resp_ok.status = 200
    mock_page.goto.return_value = resp_ok

    # Simula body vazio
    async def mock_evaluate(script, *args):
        if "innerText" in script:
            return 0
        if "children.length" in script:
            return 0
        return None

    mock_page.evaluate.side_effect = mock_evaluate
    mock_page.go_back.return_value = MagicMock()

    result = await crawler.run(page=mock_page)

    assert len(result["errors"]) == 1
    err = result["errors"][0]
    assert err["error_type"] == "blank_page"
    assert err["severity"] == "alta"


# ==============================================================================
# 5. Geração de Cenários YAML Válidos (ScenarioGenerator)
# ==============================================================================


def test_scenario_generator_produces_valid_yaml(tmp_path: Path):
    """Valida se os cenários gerados são válidos perante o parser do UXSentinel."""
    out_dir = tmp_path / "scenarios" / "generated"
    generator = ScenarioGenerator(output_dir=out_dir, profile="generic")

    nodes = [
        {"url": "https://app.teste.local/inicio", "title": "Início"},
        {"url": "https://app.teste.local/clientes", "title": "Clientes"},
    ]

    generated_paths = generator.generate_from_crawl(
        visited_nodes=nodes,
        base_url="https://app.teste.local/inicio",
    )

    assert len(generated_paths) >= 2

    for p in generated_paths:
        raw_yaml = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert raw_yaml.get("version") == "1.0"

        # Carrega com o parser oficial
        sc = load_scenario(str(p))
        assert sc.id.startswith("crawl_")
        assert sc.profile == "generic"
        assert len(sc.steps) >= 3

        # Verifica passos
        step_actions = [step.action for step in sc.steps]
        assert "goto" in step_actions
        assert "wait_until_ready" in step_actions
        assert "checkpoint" in step_actions


def test_crawler_cancellation():
    """Valida o cancelamento cooperativo do Crawler."""
    options = CrawlOptions(start_url="https://app.teste.local")
    crawler = Crawler(options)

    assert crawler.is_cancelled is False
    crawler.cancel()
    assert crawler.is_cancelled is True
    st = crawler.get_status()
    assert st["status"] == "cancelled"

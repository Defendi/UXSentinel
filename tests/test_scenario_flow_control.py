"""Testes de conformidade e hermeticidade para controle de fluxo condicional e desvio de passos (UXS-101).

Cobre os 5 critérios de aceite:
1. Identificador de Passos (id / step_id e detecção de duplicidade).
2. Ação de Desvio Incondicional (jump_to e validação estática de target).
3. Controle Condicional (branch com then_jump_to / else_jump_to e cláusula 'if' no passo).
4. Salvaguarda contra Loops Infinitos (contador jump_count e ScenarioLoopOverflowError).
5. Retrocompatibilidade com cenários legados.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.browser.actions.flow import evaluate_condition
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CheckpointResult,
    Scenario,
    ScenarioLoopOverflowError,
    StepAction,
)
from uxsentinel.scenarios.parser import load_scenario
from uxsentinel.service.scenario_service import ScenarioService


def _create_temp_scenario(yaml_content: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(yaml_content)
        return Path(f.name)


def _mock_inspect(**kwargs):
    return CheckpointResult(
        name=kwargs.get("checkpoint_name", "cp"),
        expected_behavior=kwargs.get("expected_behavior", "ok"),
        screenshot_path=kwargs.get("screenshot_path"),
        status="ok",
        issues=[],
    )


def _setup_mock_driver(executed_actions: list[str]) -> AsyncMock:
    driver = AsyncMock()
    driver.healing_events = []
    driver.page = AsyncMock()

    async def fake_goto(url, *args, **kwargs):
        executed_actions.append(f"goto:{url}")

    async def fake_click(selector, *args, **kwargs):
        executed_actions.append(f"click:{selector}")

    async def fake_fill(selector, value, *args, **kwargs):
        executed_actions.append(f"fill:{selector}={value}")

    driver.goto = AsyncMock(side_effect=fake_goto)
    driver.click = AsyncMock(side_effect=fake_click)
    driver.fill = AsyncMock(side_effect=fake_fill)
    return driver


# ==============================================================================
# Critério 1: Identificador de Passos (`id` / `step_id`)
# ==============================================================================


def test_parser_accepts_step_ids():
    yaml_content = """
id: "cenario_com_ids"
title: "Cenário com IDs de passo"
steps:
  - id: "passo_1"
    action: "goto"
    url: "/login"
  - step_id: "passo_2"
    action: "fill"
    selector: "#user"
    value: "admin"
"""
    p = _create_temp_scenario(yaml_content)
    try:
        sc = load_scenario(str(p))
        assert len(sc.steps) == 2
        assert sc.steps[0].id == "passo_1"
        assert sc.steps[0].step_id == "passo_1"
        assert sc.steps[1].id == "passo_2"
        assert sc.steps[1].step_id == "passo_2"
    finally:
        p.unlink(missing_ok=True)


def test_parser_rejects_duplicate_step_ids():
    yaml_content = """
id: "cenario_duplicado"
title: "IDs Duplicados"
steps:
  - id: "etapa_alfa"
    action: "goto"
    url: "/inicio"
  - id: "etapa_alfa"
    action: "click"
    selector: "#btn"
"""
    p = _create_temp_scenario(yaml_content)
    try:
        with pytest.raises(ValueError, match="identificador de passo duplicado 'etapa_alfa'"):
            load_scenario(str(p))
    finally:
        p.unlink(missing_ok=True)


def test_scenario_service_rejects_duplicate_step_ids():
    service = ScenarioService()
    yaml_content = """
id: "cenario_duplicado_servico"
title: "IDs Duplicados Serviço"
steps:
  - id: "meu_passo"
    action: "goto"
    url: "/inicio"
  - step_id: "meu_passo"
    action: "click"
    selector: "#btn"
"""
    result = service.validate_scenario(yaml_content)
    assert result.valid is False
    errors_id = [e for e in result.errors if e.field == "id"]
    assert len(errors_id) == 1
    assert "identificador duplicado 'meu_passo'" in errors_id[0].message


# ==============================================================================
# Critério 2: Ação de Desvio Incondicional (`jump_to`)
# ==============================================================================


def test_parser_rejects_jump_to_without_target():
    yaml_content = """
id: "cenario_sem_target"
title: "Jump sem target"
steps:
  - action: "jump_to"
"""
    p = _create_temp_scenario(yaml_content)
    try:
        with pytest.raises(ValueError, match="não possui 'target' especificado"):
            load_scenario(str(p))
    finally:
        p.unlink(missing_ok=True)


def test_parser_rejects_jump_to_nonexistent_target():
    yaml_content = """
id: "cenario_target_inexistente"
title: "Jump com target inexistente"
steps:
  - id: "inicio"
    action: "goto"
    url: "/home"
  - action: "jump_to"
    target: "passo_fantasma"
"""
    p = _create_temp_scenario(yaml_content)
    try:
        with pytest.raises(ValueError, match="aponta para target 'passo_fantasma' inexistente"):
            load_scenario(str(p))
    finally:
        p.unlink(missing_ok=True)


def test_scenario_service_validates_jump_to_targets():
    service = ScenarioService()

    # Sem target
    yaml_no_target = """
id: "sem_target"
steps:
  - action: "jump_to"
"""
    res1 = service.validate_scenario(yaml_no_target)
    assert res1.valid is False
    assert any("requer 'target'" in e.message for e in res1.errors)

    # Target inexistente
    yaml_invalid_target = """
id: "invalid_target"
steps:
  - id: "step1"
    action: "goto"
    url: "/home"
  - action: "jump_to"
    target: "nao_existe"
"""
    res2 = service.validate_scenario(yaml_invalid_target)
    assert res2.valid is False
    assert any("alvo inexistente 'nao_existe'" in e.message for e in res2.errors)


@pytest.mark.asyncio
async def test_jump_to_skips_intervening_steps(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed_actions: list[str] = []
    mock_driver = _setup_mock_driver(executed_actions)

    scenario = Scenario(
        id="cenario_jump_real",
        title="Salto funcional",
        steps=[
            StepAction(id="p1", action="goto", url="/primeiro"),
            StepAction(action="jump_to", target="p3"),
            StepAction(id="p2", action="click", selector="#deve-ser-ignorado"),
            StepAction(id="p3", action="click", selector="#alvo-atingido"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "goto:/primeiro" in executed_actions
    assert "click:#deve-ser-ignorado" not in executed_actions
    assert "click:#alvo-atingido" in executed_actions


@pytest.mark.asyncio
async def test_agent_validates_jump_target_before_running():
    agent = UXSentinelAgent(GlobalConfig())
    invalid_scenario = Scenario(
        id="cenario_estatico_invalido",
        title="Alvo inexistente",
        steps=[
            StepAction(id="s1", action="goto", url="/home"),
            StepAction(action="jump_to", target="alvo_que_nao_existe"),
        ],
    )

    with pytest.raises(ValueError, match=r"aponta para target 'alvo_que_nao_existe' inexistente"):
        await agent.run_scenario(invalid_scenario)


# ==============================================================================
# Critério 3: Controle Condicional (`branch` / `if`)
# ==============================================================================


@pytest.mark.asyncio
async def test_condition_evaluation_element_present():
    driver = AsyncMock()
    driver.page = AsyncMock()

    # Caso 1: Elemento presente (count > 0)
    driver.page.locator.return_value.count = AsyncMock(return_value=1)
    cond1 = {"element_present": "#modal"}
    assert await evaluate_condition(cond1, driver) is True

    # Caso 2: Elemento ausente (count == 0)
    driver.page.locator.return_value.count = AsyncMock(return_value=0)
    assert await evaluate_condition(cond1, driver) is False


@pytest.mark.asyncio
async def test_condition_evaluation_text_visible():
    driver = AsyncMock()
    driver.page = AsyncMock()

    # Caso 1: Texto visível
    text_loc = AsyncMock()
    text_loc.count = AsyncMock(return_value=1)
    text_loc.first.is_visible = AsyncMock(return_value=True)
    driver.page.get_by_text.return_value = text_loc

    assert await evaluate_condition({"text_visible": "Bem-vindo"}, driver) is True

    # Caso 2: Texto oculto ou não encontrado
    text_loc.count = AsyncMock(return_value=0)
    driver.page.content = AsyncMock(return_value="<html>Outro texto</html>")
    assert await evaluate_condition({"text_visible": "Bem-vindo"}, driver) is False


@pytest.mark.asyncio
async def test_condition_evaluation_url_contains():
    driver = AsyncMock()
    driver.page = AsyncMock()
    driver.page.url = "https://empresa.com/dashboard/pedidos"

    assert await evaluate_condition({"url_contains": "/dashboard"}, driver) is True
    assert await evaluate_condition({"url_contains": "/login"}, driver) is False


@pytest.mark.asyncio
async def test_condition_evaluation_javascript():
    driver = AsyncMock()
    driver.page = AsyncMock()
    driver.page.evaluate = AsyncMock(return_value=True)

    assert await evaluate_condition({"javascript": "window.hasPromo === true"}, driver) is True

    driver.page.evaluate = AsyncMock(return_value=False)
    assert await evaluate_condition({"javascript": "window.hasPromo === true"}, driver) is False


@pytest.mark.asyncio
async def test_branch_when_condition_true_jumps_to_then(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)
    # Simula modal presente
    mock_driver.page.locator.return_value.count = AsyncMock(return_value=1)

    scenario = Scenario(
        id="cenario_branch_true",
        title="Branch Verdadeiro",
        steps=[
            StepAction(
                action="branch",
                element_present="#banner-modal",
                then_jump_to="fechar_banner",
                else_jump_to="fluxo_normal",
            ),
            StepAction(id="fluxo_normal", action="click", selector="#btn-comprar"),
            StepAction(action="jump_to", target="fim"),
            StepAction(id="fechar_banner", action="click", selector="#btn-fechar-banner"),
            StepAction(id="fim", action="click", selector="#btn-final"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "click:#btn-fechar-banner" in executed
    assert "click:#btn-comprar" not in executed
    assert "click:#btn-final" in executed


@pytest.mark.asyncio
async def test_branch_when_condition_false_jumps_to_else(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)
    # Simula banner ausente
    mock_driver.page.locator.return_value.count = AsyncMock(return_value=0)

    scenario = Scenario(
        id="cenario_branch_false",
        title="Branch Falso com Else",
        steps=[
            StepAction(
                action="branch",
                element_present="#banner-modal",
                then_jump_to="fechar_banner",
                else_jump_to="fluxo_normal",
            ),
            StepAction(id="fechar_banner", action="click", selector="#btn-fechar-banner"),
            StepAction(action="jump_to", target="fim"),
            StepAction(id="fluxo_normal", action="click", selector="#btn-comprar"),
            StepAction(id="fim", action="click", selector="#btn-final"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "click:#btn-fechar-banner" not in executed
    assert "click:#btn-comprar" in executed
    assert "click:#btn-final" in executed


@pytest.mark.asyncio
async def test_branch_when_condition_false_without_else_continues_sequentially(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)
    # Condição falsa
    mock_driver.page.locator.return_value.count = AsyncMock(return_value=0)

    scenario = Scenario(
        id="cenario_branch_no_else",
        title="Branch Falso sem Else",
        steps=[
            StepAction(
                action="branch",
                element_present="#banner-modal",
                then_jump_to="fechar_banner",
            ),
            StepAction(id="passo_sequencial", action="click", selector="#passo-seguinte"),
            StepAction(action="jump_to", target="fim"),
            StepAction(id="fechar_banner", action="click", selector="#btn-fechar-banner"),
            StepAction(id="fim", action="click", selector="#btn-final"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "click:#passo-seguinte" in executed
    assert "click:#btn-fechar-banner" not in executed


@pytest.mark.asyncio
async def test_step_with_if_condition_executes_when_true_and_skips_when_false(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)

    def locator_mock(selector):
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=1 if selector == "#presente" else 0)
        return loc

    mock_driver.page.locator = locator_mock

    scenario = Scenario(
        id="cenario_if_no_passo",
        title="Passos com cláusula if",
        steps=[
            StepAction(
                action="click",
                selector="#btn-1",
                condition={"element_present": "#presente"},
            ),
            StepAction(
                action="click",
                selector="#btn-2",
                condition={"element_present": "#ausente"},
            ),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "click:#btn-1" in executed
    assert "click:#btn-2" not in executed


@pytest.mark.asyncio
async def test_jump_to_with_if_condition(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)
    mock_driver.page.url = "https://app.com/login"

    # Cenário com jump_to condicional: url contem /dashboard (Falso -> não salta)
    scenario = Scenario(
        id="cenario_jump_if",
        title="Jump com if",
        steps=[
            StepAction(
                action="jump_to",
                target="dashboard_view",
                condition={"url_contains": "/dashboard"},
            ),
            StepAction(id="login_step", action="click", selector="#btn-login"),
            StepAction(id="dashboard_view", action="click", selector="#btn-dashboard"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert "click:#btn-login" in executed
    assert "click:#btn-dashboard" in executed


# ==============================================================================
# Critério 4: Salvaguarda contra Loops Infinitos (`ScenarioLoopOverflowError`)
# ==============================================================================


@pytest.mark.asyncio
async def test_infinite_loop_triggers_scenario_loop_overflow_error(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)

    # Loop infinito: passo 1 salta para passo 2, passo 2 salta para passo 1
    scenario = Scenario(
        id="cenario_loop_infinito",
        title="Loop Infinito",
        steps=[
            StepAction(id="loop_a", action="jump_to", target="loop_b"),
            StepAction(id="loop_b", action="jump_to", target="loop_a"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        with pytest.raises(ScenarioLoopOverflowError, match="Limite máximo de 50 saltos excedido"):
            await agent.run_scenario(scenario)


@pytest.mark.asyncio
async def test_custom_max_jumps_triggers_overflow_error(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    executed: list[str] = []
    mock_driver = _setup_mock_driver(executed)

    # Cenário com max_jumps = 5
    scenario = Scenario(
        id="cenario_loop_custom",
        title="Loop com Limite Customizado",
        max_jumps=5,
        steps=[
            StepAction(id="step_a", action="jump_to", target="step_b"),
            StepAction(id="step_b", action="jump_to", target="step_a"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        with pytest.raises(ScenarioLoopOverflowError, match="Limite máximo de 5 saltos excedido"):
            await agent.run_scenario(scenario)


def test_parser_parses_custom_max_jumps():
    yaml_content = """
id: "cenario_max_jumps"
title: "Cenário com Max Jumps"
max_jumps: 15
steps:
  - id: "p1"
    action: "goto"
    url: "/login"
"""
    p = _create_temp_scenario(yaml_content)
    try:
        sc = load_scenario(str(p))
        assert sc.max_jumps == 15
    finally:
        p.unlink(missing_ok=True)


# ==============================================================================
# Critério 5: Retrocompatibilidade com Cenários Legados
# ==============================================================================


@pytest.mark.asyncio
async def test_legacy_scenarios_execute_sequentially_without_ids(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conectado"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    actions_executed: list[str] = []
    mock_driver = _setup_mock_driver(actions_executed)

    # Cenário clássico 100% sequencial sem id nem desvios
    scenario = Scenario(
        id="cenario_legado",
        title="Cenário Legado Sequencial",
        steps=[
            StepAction(action="goto", url="/login"),
            StepAction(action="fill", selector="#user", value="admin"),
            StepAction(action="click", selector="#submit"),
        ],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    assert actions_executed == [
        "goto:/login",
        "fill:#user=admin",
        "click:#submit",
    ]

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.core.agent import Agent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    ScenarioExceptions,
    StepAction,
    TestReport,
)
from uxsentinel.scenarios.parser import load_scenario, parse_scenario_exceptions
from uxsentinel.vision.evaluators.base import EvaluatorContext
from uxsentinel.vision.evaluators.domain import DomainQAAgent
from uxsentinel.vision.inspector import ScreenInspector


def test_parse_scenario_exceptions_dict():
    raw = {
        "allowed_texts": ["By Gotryx", "Powered by"],
        "ignored_selectors": ["#btn-x", "button.ignorar"],
        "ignored_elements": ["o botão x", "banner beta"],
        "ignored_categories": ["cosmetico"],
        "custom_rules": ["Manter a frase By Gotryx no rodapé"],
    }
    exc = parse_scenario_exceptions(raw)
    assert exc is not None
    assert "By Gotryx" in exc.allowed_texts
    assert "Powered by" in exc.allowed_texts
    assert "#btn-x" in exc.ignored_selectors
    assert "o botão x" in exc.ignored_elements
    assert "cosmetico" in exc.ignored_categories
    assert "Manter a frase By Gotryx no rodapé" in exc.custom_rules


def test_parse_scenario_exceptions_pt_br():
    raw = {
        "textos_permitidos": ["By Gotryx"],
        "seletores_ignorados": ["#botao-x"],
        "elementos_ignorados": ["botão de feedback"],
        "regras": ["Não testar o botão x"],
    }
    exc = parse_scenario_exceptions(raw)
    assert exc is not None
    assert "By Gotryx" in exc.allowed_texts
    assert "#botao-x" in exc.ignored_selectors
    assert "botão de feedback" in exc.ignored_elements
    assert "Não testar o botão x" in exc.custom_rules


def test_parse_scenario_exceptions_list():
    raw = [
        '"By Gotryx"',
        "#botao-x",
        "Não testar o botão x e manter frase 'Powered by'",
    ]
    exc = parse_scenario_exceptions(raw)
    assert exc is not None
    assert "By Gotryx" in exc.allowed_texts
    assert "#botao-x" in exc.ignored_selectors
    assert any("Powered by" in t for t in exc.allowed_texts)
    assert any("Não testar o botão x" in r for r in exc.custom_rules)


def test_scenario_exceptions_matches_issue():
    exc = ScenarioExceptions(
        allowed_texts=["By Gotryx"],
        ignored_selectors=["#btn-x"],
        ignored_elements=["o botão x"],
        ignored_categories=["cosmetico"],
    )

    issue_allowed_text = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Termo em inglês detectado: 'By Gotryx'",
        elemento_alvo="div.footer-gotryx",
    )
    assert exc.matches_issue(issue_allowed_text) is True

    issue_ignored_selector = Issue(
        categoria=IssueCategory.LAYOUT,
        severidade=IssueSeverity.MEDIA,
        descricao="Botão desalinhado",
        elemento_alvo="#btn-x",
    )
    assert exc.matches_issue(issue_ignored_selector) is True

    issue_ignored_element = Issue(
        categoria=IssueCategory.REGRA_NEGOCIO,
        severidade=IssueSeverity.ALTA,
        descricao="Falha ao renderizar o botão x na tela",
        elemento_alvo="button",
    )
    assert exc.matches_issue(issue_ignored_element) is True

    issue_real_problem = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Botão 'Submit' não está traduzido para o português",
        elemento_alvo="button#btn-submit",
    )
    assert exc.matches_issue(issue_real_problem) is False


def test_scenario_exceptions_merge():
    exc1 = ScenarioExceptions(
        allowed_texts=["By Gotryx"],
        ignored_selectors=["#btn-1"],
    )
    exc2 = ScenarioExceptions(
        allowed_texts=["Powered by"],
        ignored_selectors=["#btn-2"],
    )
    merged = exc1.merge(exc2)
    assert "By Gotryx" in merged.allowed_texts
    assert "Powered by" in merged.allowed_texts
    assert "#btn-1" in merged.ignored_selectors
    assert "#btn-2" in merged.ignored_selectors


def test_load_scenario_with_exceptions_and_skip():
    yaml_content = """
id: cenario_com_excecoes
title: Cenário com Exceções Homologadas
exceptions:
  allowed_texts:
    - "By Gotryx"
  ignored_selectors:
    - "#botao-ignorado"
  custom_rules:
    - "Não testar o botão x"

steps:
  - action: "click"
    selector: "#botao-ignorado"
    skip: true
    description: "Não testar o botão x temporariamente"

  - action: "checkpoint"
    name: "home_page"
    expected_behavior: "Dashboard sem erros"
    exceptions:
      allowed_texts:
        - "Powered by"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        scenario = load_scenario(temp_path)
        assert scenario.id == "cenario_com_excecoes"
        assert scenario.exceptions is not None
        assert "By Gotryx" in scenario.exceptions.allowed_texts
        assert "#botao-ignorado" in scenario.exceptions.ignored_selectors

        assert len(scenario.steps) == 2
        assert scenario.steps[0].skip is True
        assert scenario.steps[1].exceptions is not None
        assert "Powered by" in scenario.steps[1].exceptions.allowed_texts
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_evaluator_prompt_includes_exceptions():
    client_mock = MagicMock()
    evaluator = DomainQAAgent(client_mock)
    context = EvaluatorContext(
        checkpoint_name="cp_teste",
        expected_behavior="Tudo em conformidade",
        image_base64="fake_b64",
        exceptions=ScenarioExceptions(
            allowed_texts=["By Gotryx"],
            ignored_selectors=["#btn-x"],
            custom_rules=["Não testar o botão x"],
        ),
    )
    prompt = evaluator.build_user_prompt(context)
    assert "CLÁUSULA DE EXCEÇÕES E TOLERÂNCIAS HOMOLOGADAS" in prompt
    assert "'By Gotryx'" in prompt
    assert "#btn-x" in prompt
    assert "Não testar o botão x" in prompt


@pytest.mark.asyncio
async def test_screen_inspector_filters_exceptions(monkeypatch):
    config = GlobalConfig()
    config.vision.use_mixture_of_evaluators = False
    config.vision.enable_devils_advocate = False

    inspector = ScreenInspector(config)

    raw_lmm_response = """
    {
      "status": "problemas_encontrados",
      "issues": [
        {
          "categoria": "traducao",
          "severidade": "alta",
          "descricao": "Texto em inglês não traduzido: By Gotryx",
          "elemento_alvo": "footer"
        },
        {
          "categoria": "layout",
          "severidade": "media",
          "descricao": "Botão desalinhado",
          "elemento_alvo": "#btn-x"
        },
        {
          "categoria": "traducao",
          "severidade": "alta",
          "descricao": "Botão Save em inglês",
          "elemento_alvo": "button#save"
        }
      ]
    }
    """
    inspector.client.analyze = AsyncMock(return_value=raw_lmm_response)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        screenshot_path = f.name

    try:
        exceptions = ScenarioExceptions(
            allowed_texts=["By Gotryx"],
            ignored_selectors=["#btn-x"],
        )
        res = await inspector.inspect(
            checkpoint_name="cp_filtro",
            expected_behavior="Tela sem erros",
            screenshot_path=screenshot_path,
            exceptions=exceptions,
        )

        assert len(res.issues) == 1
        assert "Save" in res.issues[0].descricao
    finally:
        Path(screenshot_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_agent_skips_step():
    config = GlobalConfig()
    agent = Agent(config)

    mock_driver = MagicMock()
    mock_driver.click = AsyncMock()
    mock_driver.healing_events = []

    scenario = Scenario(
        id="cenario_skip",
        title="Cenário de Skip",
        steps=[
            StepAction(action="click", selector="#btn-normal"),
            StepAction(action="click", selector="#btn-pulado", skip=True),
        ],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    await agent._execute_step(
        index=2,
        step=scenario.steps[1],
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
    )

    mock_driver.click.assert_not_called()


@pytest.mark.asyncio
async def test_agent_skips_ignored_selector():
    config = GlobalConfig()
    agent = Agent(config)

    mock_driver = MagicMock()
    mock_driver.click = AsyncMock()
    mock_driver.healing_events = []

    scenario = Scenario(
        id="cenario_ignored_selector",
        title="Cenário Seletor Ignorado",
        exceptions=ScenarioExceptions(ignored_selectors=["#btn-nao-testar"]),
        steps=[
            StepAction(action="click", selector="#btn-nao-testar"),
        ],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    await agent._execute_step(
        index=1,
        step=scenario.steps[0],
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
    )

    mock_driver.click.assert_not_called()

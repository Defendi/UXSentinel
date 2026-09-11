import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uxsentinel.browser.session import open_browser_session
from uxsentinel.core.config import load_config
from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity, TestReport
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.json_builder import save_json_report
from uxsentinel.scenarios.parser import load_scenario


def test_config_and_scenarios():
    cfg = load_config("config/config.yaml")
    assert cfg.active_provider is not None
    assert "anthropic_cloud" in cfg.providers
    assert "ollama_local" in cfg.providers
    assert "corporate_gateway" in cfg.providers

    sc = load_scenario("uxsentinel/scenarios/library/exemplo_web_geral.yaml")
    assert sc.id == "login_e_dashboard_geral"
    assert len(sc.steps) > 0

    sc_odoo = load_scenario("uxsentinel/scenarios/library/exemplo_odoo.yaml")
    assert sc_odoo.profile == "odoo"
    assert len(sc_odoo.steps) > 0
    print("✓ Teste de Configuração e Parser de Cenários passou!")


def test_reporting():
    report = TestReport(
        scenario_id="teste_unitario",
        scenario_title="Teste Unitário de Relatórios",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="Tudo em português",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.TRADUCAO,
                        severidade=IssueSeverity.MEDIA,
                        descricao="Botão 'Save' em inglês",
                        sugestao_correcao="Substituir por 'Salvar'",
                        elemento_alvo="button#btn-save",
                    )
                ],
            )
        ],
    )
    report.compute_totals()
    assert report.total_issues == 1
    assert report.total_medias == 1

    json_path = save_json_report(report, "report_test")
    assert json_path.is_file()

    html_path = save_html_report(report, "report_test")
    assert html_path.is_file()

    # Limpeza
    json_path.unlink()
    html_path.unlink()
    Path("report_test").rmdir()
    print("✓ Teste de Geração de Relatórios JSON e HTML passou!")


async def test_browser_session_headless():
    cfg = load_config("config/config.yaml")
    cfg.browser.headless = True
    async with open_browser_session(cfg.browser, profile="generic") as driver:
        await driver.goto("https://example.com")
        dom_text = await driver.get_clean_dom_text()
        assert "Example Domain" in dom_text
    print("✓ Teste de Navegação Playwright e Extração DOM passou!")


if __name__ == "__main__":
    test_config_and_scenarios()
    test_reporting()
    asyncio.run(test_browser_session_headless())
    print("\n🎉 TODOS OS TESTES INTERNOS PASSARAM COM SUCESSO!")

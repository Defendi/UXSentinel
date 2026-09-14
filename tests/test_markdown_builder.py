"""Testes unitários herméticos para o gerador de relatórios Markdown compatível com MarkText."""

from datetime import datetime
from pathlib import Path

from uxsentinel.core.config import resolve_markdown_mode
from uxsentinel.core.models import (
    AxeViolation,
    BoundingBox,
    CheckpointResult,
    HealingEvent,
    Issue,
    IssueCategory,
    IssueSeverity,
    SemanticStepResult,
    SemanticStrategy,
    TestReport,
    VisualDiffResult,
)
from uxsentinel.reporter.markdown_builder import (
    _calc_rel_path,
    build_markdown_report,
    save_markdown_report,
)


def test_resolve_markdown_mode_hierarchy() -> None:
    """Testa a precedência da resolução do modo markdown: CLI > YAML > Config > Padrão."""
    # 1. CLI tem precedência absoluta
    assert resolve_markdown_mode(cli_markdown=True, scenario_markdown=False, config_markdown=False) is True
    assert resolve_markdown_mode(cli_markdown=False, scenario_markdown=True, config_markdown=True) is False

    # 2. Cenário YAML quando CLI é None
    assert resolve_markdown_mode(cli_markdown=None, scenario_markdown=True, config_markdown=False) is True
    assert resolve_markdown_mode(cli_markdown=None, scenario_markdown=False, config_markdown=True) is False

    # 3. Config global quando CLI e Cenário são None
    assert resolve_markdown_mode(cli_markdown=None, scenario_markdown=None, config_markdown=True) is True
    assert resolve_markdown_mode(cli_markdown=None, scenario_markdown=None, config_markdown=False) is False

    # 4. Fallback padrão é False
    assert resolve_markdown_mode(cli_markdown=None, scenario_markdown=None, config_markdown=None) is False


def test_calc_rel_path() -> None:
    """Testa o cálculo de caminhos relativos para o MarkText."""
    assert _calc_rel_path(None, Path("/tmp")) == ""

    base = Path("/workspace/report")
    target = Path("/workspace/report/screenshots/cp1.png")
    rel = _calc_rel_path(str(target), base)
    assert rel == "screenshots/cp1.png"


def test_build_markdown_report_success() -> None:
    """Testa a geração de relatório Markdown para um cenário aprovado com 100% de conformidade."""
    report = TestReport(
        scenario_id="cenario_ok",
        scenario_title="Fluxo de Acesso com Sucesso",
        profile="generic",
        provider_used="gemini_cloud",
        started_at=datetime(2026, 9, 14, 10, 0, 0),
        finished_at=datetime(2026, 9, 14, 10, 0, 15),
        duration_seconds=15.0,
        success=True,
    )
    report.compute_totals()

    md = build_markdown_report(report)

    assert "# 🛡️ Relatório de Auditoria Visual & UX — Fluxo de Acesso com Sucesso" in md
    assert "CONFORME (Aprovado)" in md
    assert "15.0s" in md
    assert "gemini_cloud" in md
    assert "Nenhuma inconformidade visual, de UX ou de idioma foi detectada" in md


def test_build_markdown_report_with_issues_and_a11y(tmp_path: Path) -> None:
    """Testa a geração de relatório completo com issues, violações WCAG, autocura e diffs."""
    cp_img = tmp_path / "screenshots" / "checkpoint_01.png"
    cp_img.parent.mkdir(parents=True, exist_ok=True)
    cp_img.write_text("fake_png")

    diff_img = tmp_path / "diffs" / "checkpoint_01_diff.png"
    diff_img.parent.mkdir(parents=True, exist_ok=True)
    diff_img.write_text("fake_diff")

    base_img = tmp_path / "baselines" / "checkpoint_01_base.png"
    base_img.parent.mkdir(parents=True, exist_ok=True)
    base_img.write_text("fake_base")

    issue1 = Issue(
        severidade=IssueSeverity.BLOQUEANTE,
        categoria=IssueCategory.REGRA_NEGOCIO,
        descricao="Botão de finalização de pedido desabilitado indevidamente.",
        elemento_seletor="button#btn-finish",
        sugestao_correcao="Remover atributo disabled após validação de formulário.",
        evaluator="Domain QA Agent",
    )

    issue2 = Issue(
        severidade=IssueSeverity.MEDIA,
        categoria=IssueCategory.TRADUCAO,
        descricao="Rótulo 'Submit Order' exibido em inglês.",
        elemento_seletor="button#btn-finish",
        sugestao_correcao="Substituir por 'Confirmar Pedido'.",
        evaluator="Linguist Agent",
    )

    violation = AxeViolation(
        id="color-contrast",
        impact="serious",
        description="Elementos devem ter contraste de cor suficiente.",
        help_url="https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        tags=["wcag2aa", "wcag143"],
        nodes=[{"target": ["button#btn-finish"]}],
    )

    diff_res = VisualDiffResult(
        baseline_path=str(base_img),
        current_path=str(cp_img),
        diff_image_path=str(diff_img),
        diff_percentage=1.45,
        has_diff=True,
        threshold=0.1,
        bounding_boxes=[BoundingBox(x=10, y=20, width=100, height=40)],
    )

    healing = HealingEvent(
        step_index=1,
        action="click",
        original_selector="#btn-submit-old",
        healed_selector="button[type='submit']",
        strategy="accessibility_match",
        success=True,
        timestamp=datetime(2026, 9, 14, 10, 0, 5),
    )

    semantic = SemanticStepResult(
        step_index=2,
        action="ai_click",
        target="o botão azul de confirmar",
        strategy=SemanticStrategy.ACCESSIBILITY,
        resolved_selector="button.btn-primary",
        passed=True,
        confidence=0.98,
        reasoning="Localizado via árvore de acessibilidade pelo label 'Confirmar'.",
    )

    cp = CheckpointResult(
        name="tela_checkout",
        description="Página de confirmação de pedido",
        expected_behavior="Todos os botões traduzidos e contrastes adequados.",
        status="problemas_encontrados",
        screenshot_path=str(cp_img),
        issues=[issue1, issue2],
        a11y_score=82.5,
        a11y_violations=[violation],
        visual_diff=diff_res,
        viewport="desktop (1440x900)",
    )

    report = TestReport(
        scenario_id="cenario_checkout",
        scenario_title="Auditoria de Checkout e Acessibilidade",
        profile="odoo",
        provider_used="claude_sso",
        started_at=datetime(2026, 9, 14, 10, 0, 0),
        finished_at=datetime(2026, 9, 14, 10, 0, 30),
        duration_seconds=30.0,
        checkpoints=[cp],
        healed_steps=[healing],
        semantic_steps=[semantic],
        video_path=str(tmp_path / "videos" / "session.mp4"),
        gif_path=str(tmp_path / "videos" / "session.gif"),
        viewports_tested=["desktop (1440x900)"],
        a11y_score=82.5,
        a11y_violations=[violation],
        success=False,
    )
    report.compute_totals()

    # Gera Markdown
    md = build_markdown_report(report, output_dir=tmp_path)

    # Asserções de conteúdo
    assert "PROBLEMAS ENCONTRADOS (Requer Atenção)" in md
    assert "BLOQUEANTE (Crítico)" in md
    assert "MÉDIA (Moderada)" in md
    assert "🔴" in md
    assert "🟡" in md
    assert "Botão de finalização de pedido desabilitado indevidamente" in md
    assert "color-contrast" in md
    assert "https://dequeuniversity.com/rules/axe/4.10/color-contrast" in md
    assert "Seletores Auto-Curados (Self-Healing)" in md
    assert "#btn-submit-old" in md
    assert "Auditoria de Regressão Visual (Baseline)" in md
    assert "Divergência Detectada" in md
    assert "1.45%" in md

    # Salva em arquivo
    saved_file = save_markdown_report(report, output_dir=tmp_path)
    assert saved_file.is_file()
    assert saved_file.name == "cenario_checkout_report.md"
    assert saved_file.read_text(encoding="utf-8") == md

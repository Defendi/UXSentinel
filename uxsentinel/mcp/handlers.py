"""Handlers para as ferramentas (tools) e recursos (resources) do servidor MCP do UXSentinel.

Implementa a lógica de negócio exposta para agentes de IA:
- list_scenarios
- validate_scenario
- run_scenario
- inspect_url
- get_last_report
- Recursos: uxsentinel://scenarios e uxsentinel://reports/latest
"""

import json
import logging
from pathlib import Path
from typing import Any

from uxsentinel.core.config import GlobalConfig, load_config
from uxsentinel.core.models import (
    AxeViolation,
    TestReport,
    parse_viewport_spec,
)
from uxsentinel.mcp.protocol import (
    CallToolResult,
    ResourceContent,
    ResourceDefinition,
    TextContent,
    ToolDefinition,
)
from uxsentinel.scenarios.parser import is_valid_scenario_file, load_scenario
from uxsentinel.service.scenario_service import ScenarioService

logger = logging.getLogger("uxsentinel.mcp.handlers")

# Definição das 5 ferramentas expostas pelo UXSentinel via MCP
TOOLS_REGISTRY: list[ToolDefinition] = [
    ToolDefinition(
        name="list_scenarios",
        description="Lista todos os cenários YAML disponíveis (locais em ./scenarios e na biblioteca embutida do UXSentinel).",
        inputSchema={
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Filtro opcional por tag de cenário (ex: 'smoke', 'login').",
                },
                "profile": {
                    "type": "string",
                    "description": "Filtro opcional por perfil ('generic' ou 'odoo').",
                },
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="validate_scenario",
        description="Valida sintaxe e semântica de um cenário YAML sem abrir o navegador.",
        inputSchema={
            "type": "object",
            "properties": {
                "scenario_path": {
                    "type": "string",
                    "description": "Caminho do arquivo YAML do cenário a ser validado.",
                }
            },
            "required": ["scenario_path"],
        },
    ),
    ToolDefinition(
        name="run_scenario",
        description="Dispara a execução de um cenário YAML de QA Visual com o UXSentinel.",
        inputSchema={
            "type": "object",
            "properties": {
                "scenario_path": {
                    "type": "string",
                    "description": "Caminho do arquivo YAML do cenário.",
                },
                "profile": {
                    "type": "string",
                    "description": "Perfil de execução ('generic' ou 'odoo').",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Executar sem abrir janela gráfica do navegador (padrão true).",
                },
                "slowmo": {
                    "type": "integer",
                    "description": "Atraso em milissegundos entre ações (padrão 0 para automação).",
                },
                "devtools": {
                    "type": "boolean",
                    "description": "Abrir com Chromium DevTools acoplado (padrão false).",
                },
                "viewport": {
                    "type": "string",
                    "description": "Configuração de viewport ('desktop', 'tablet', 'mobile' ou 'LARGURAxALTURA').",
                },
                "ai_provider": {
                    "type": "string",
                    "description": "Provedor de IA para inspeção visual (ex: 'gemini_sso', 'claude_sso', 'ollama_local').",
                },
            },
            "required": ["scenario_path"],
        },
    ),
    ToolDefinition(
        name="inspect_url",
        description="Executa inspeção rápida e ad-hoc de QA Visual e Acessibilidade em uma URL sem exigir arquivo YAML prévio.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL da aplicação web a ser auditada.",
                },
                "viewport": {
                    "type": "string",
                    "description": "Preset de viewport ('desktop', 'tablet', 'mobile' ou 'LARGURAxALTURA', padrão 'desktop').",
                },
                "check_a11y": {
                    "type": "boolean",
                    "description": "Habilitar auditoria de acessibilidade Axe-Core WCAG 2.2 AA (padrão true).",
                },
                "check_visual": {
                    "type": "boolean",
                    "description": "Habilitar análise de usabilidade e integridade visual (padrão true).",
                },
            },
            "required": ["url"],
        },
    ),
    ToolDefinition(
        name="get_last_report",
        description="Obtém o resultado resumido ou completo da última auditoria executada pelo UXSentinel.",
        inputSchema={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "markdown", "json"],
                    "description": "Formato de saída ('summary', 'markdown' ou 'json', padrão 'summary').",
                }
            },
            "required": [],
        },
    ),
]

# Definição dos recursos expostos pelo UXSentinel via MCP
RESOURCES_REGISTRY: list[ResourceDefinition] = [
    ResourceDefinition(
        uri="uxsentinel://scenarios",
        name="Cenários Disponíveis",
        description="Catálogo descritivo dos cenários registrados no UXSentinel.",
        mimeType="application/json",
    ),
    ResourceDefinition(
        uri="uxsentinel://reports/latest",
        name="Último Relatório de Execução",
        description="Conteúdo estruturado completo do último relatório de teste gerado.",
        mimeType="application/json",
    ),
]


def _find_all_scenario_files(base_dir: Path | None = None) -> list[Path]:
    """Descobre arquivos de cenário no projeto atual e na biblioteca interna."""
    cwd = base_dir or Path.cwd()
    search_dirs = [
        cwd / "scenarios",
        cwd / "scenarios" / "generated",
        cwd / ".uxsentinel" / "scenarios",
        cwd / "tests" / "scenarios",
        cwd,
    ]
    pkg_lib_dir = Path(__file__).resolve().parent.parent / "scenarios" / "library"

    results: list[Path] = []
    seen: set[Path] = set()

    for sdir in search_dirs:
        if sdir.is_dir():
            for ext in ("*.yaml", "*.yml"):
                for yml in sdir.glob(ext):
                    if is_valid_scenario_file(yml):
                        res = yml.resolve()
                        if res not in seen:
                            seen.add(res)
                            results.append(yml)

    if pkg_lib_dir.is_dir():
        for ext in ("*.yaml", "*.yml"):
            for yml in pkg_lib_dir.glob(ext):
                if is_valid_scenario_file(yml):
                    res = yml.resolve()
                    if res not in seen:
                        seen.add(res)
                        results.append(yml)

    return sorted(results, key=lambda p: p.name.lower())


async def list_scenarios(tag: str | None = None, profile: str | None = None) -> CallToolResult:
    """Varre cenários locais e da biblioteca interna com filtros opcionais por tag e profile."""
    try:
        files = _find_all_scenario_files()
        scenarios_data: list[dict[str, Any]] = []

        for f in files:
            try:
                sc = load_scenario(str(f), auto_register=False)
            except Exception as err:
                logger.warning(f"Erro ao carregar cenário {f}: {err}")
                continue

            if tag:
                tag_lower = tag.strip().lower()
                if not any(tag_lower == t.lower() for t in sc.tags):
                    continue

            if profile:
                profile_lower = profile.strip().lower()
                if (sc.profile or "generic").lower() != profile_lower:
                    continue

            try:
                rel_path = str(f.relative_to(Path.cwd()))
            except ValueError:
                rel_path = str(f)

            scenarios_data.append(
                {
                    "id": sc.id,
                    "title": sc.title,
                    "profile": sc.profile,
                    "path": rel_path,
                    "tags": sc.tags,
                    "steps_count": len(sc.steps),
                    "description": sc.description,
                }
            )

        output_text = json.dumps(scenarios_data, indent=2, ensure_ascii=False)
        return CallToolResult(
            content=[TextContent(text=output_text)],
            isError=False,
        )
    except Exception as exc:
        logger.exception("Falha inesperada ao listar cenários")
        return CallToolResult(
            content=[TextContent(text=f"Erro ao listar cenários: {exc}")],
            isError=True,
        )


async def validate_scenario(scenario_path: str) -> CallToolResult:
    """Valida a sintaxe e a integridade de um cenário YAML sem abrir o navegador."""
    try:
        path = Path(scenario_path)
        if not path.is_file():
            # Tenta resolver relativo à biblioteca de cenários se não encontrado localmente
            pkg_lib = Path(__file__).resolve().parent.parent / "scenarios" / "library" / scenario_path
            if pkg_lib.is_file():
                path = pkg_lib
            else:
                return CallToolResult(
                    content=[
                        TextContent(
                            text=json.dumps(
                                {
                                    "valid": False,
                                    "scenario_path": scenario_path,
                                    "errors": [
                                        {
                                            "field": "file",
                                            "message": f"Arquivo não encontrado: {scenario_path}",
                                        }
                                    ],
                                },
                                indent=2,
                                ensure_ascii=False,
                            )
                        )
                    ],
                    isError=True,
                )

        raw_yaml = path.read_text(encoding="utf-8")
        service = ScenarioService()
        validation = service.validate_scenario(raw_yaml)

        if not validation.valid:
            errors_payload = [
                {
                    "step_index": err.step_index,
                    "field": err.field,
                    "message": err.message,
                }
                for err in validation.errors
            ]
            res = {
                "valid": False,
                "scenario_path": str(path),
                "errors": errors_payload,
            }
            return CallToolResult(
                content=[TextContent(text=json.dumps(res, indent=2, ensure_ascii=False))],
                isError=False,
            )

        # Validação de segundo nível através do carregamento completo do modelo
        try:
            scenario = load_scenario(str(path), auto_register=False)
            res = {
                "valid": True,
                "scenario_path": str(path),
                "id": scenario.id,
                "title": scenario.title,
                "profile": scenario.profile,
                "steps_count": len(scenario.steps),
                "tags": scenario.tags,
                "description": scenario.description,
                "errors": [],
            }
            return CallToolResult(
                content=[TextContent(text=json.dumps(res, indent=2, ensure_ascii=False))],
                isError=False,
            )
        except Exception as load_err:
            res = {
                "valid": False,
                "scenario_path": str(path),
                "errors": [{"field": "model", "message": str(load_err)}],
            }
            return CallToolResult(
                content=[TextContent(text=json.dumps(res, indent=2, ensure_ascii=False))],
                isError=False,
            )

    except Exception as exc:
        logger.exception("Falha inesperada ao validar cenário")
        return CallToolResult(
            content=[TextContent(text=f"Erro ao validar cenário: {exc}")],
            isError=True,
        )


async def run_scenario(
    scenario_path: str,
    profile: str | None = None,
    headless: bool = True,
    slowmo: int = 0,
    devtools: bool = False,
    viewport: str | None = None,
    ai_provider: str | None = None,
    config: GlobalConfig | None = None,
) -> CallToolResult:
    """Executa um cenário YAML de QA Visual com segurança e retorna resultados estruturados."""
    try:
        path = Path(scenario_path)
        if not path.is_file():
            pkg_lib = Path(__file__).resolve().parent.parent / "scenarios" / "library" / scenario_path
            if pkg_lib.is_file():
                path = pkg_lib
            else:
                return CallToolResult(
                    content=[TextContent(text=f"Arquivo de cenário não encontrado: {scenario_path}")],
                    isError=True,
                )

        cfg = config or load_config()
        if ai_provider:
            cfg.active_provider = ai_provider

        scenario = load_scenario(str(path), auto_register=True)
        if profile:
            scenario.profile = profile

        # Importa UXSentinelAgent internamente para viabilizar mocking nos testes
        from uxsentinel.core.agent import UXSentinelAgent

        agent = UXSentinelAgent(
            config=cfg,
            headless_override=headless,
            devtools_override=devtools,
            viewports_override=viewport,
        )

        report: TestReport = await agent.run_scenario(
            scenario=scenario,
            headless_override=headless,
            devtools_override=devtools,
            viewports_override=viewport,
        )

        issues_summary: list[dict[str, Any]] = []
        for cp in report.checkpoints:
            for issue in cp.issues:
                cat_val = issue.categoria.value if hasattr(issue.categoria, "value") else str(issue.categoria)
                sev_val = (
                    issue.severidade.value if hasattr(issue.severidade, "value") else str(issue.severidade)
                )
                issues_summary.append(
                    {
                        "checkpoint": cp.name,
                        "categoria": cat_val,
                        "severidade": sev_val,
                        "descricao": issue.descricao,
                        "sugestao_correcao": issue.sugestao_correcao,
                        "elemento_alvo": issue.elemento_alvo,
                    }
                )

        reports_dir = Path.cwd() / "reports"
        json_path = reports_dir / f"{report.scenario_id}_report.json"
        html_path = reports_dir / f"{report.scenario_id}_report.html"

        result_payload = {
            "scenario_id": report.scenario_id,
            "scenario_title": report.scenario_title,
            "success": report.success,
            "status": "passed" if report.success else "failed",
            "duration_seconds": round(report.duration_seconds, 2),
            "checkpoints_count": len(report.checkpoints),
            "total_issues": report.total_issues,
            "severities": {
                "bloqueante": report.total_bloqueantes,
                "alta": report.total_altas,
                "media": report.total_medias,
                "baixa": report.total_baixas,
            },
            "a11y_score": report.a11y_score,
            "reports": {
                "html": str(html_path) if html_path.exists() else report.archived_report_path,
                "json": str(json_path) if json_path.exists() else None,
                "markdown": report.markdown_path,
            },
            "issues": issues_summary,
            "error_message": report.error_message,
        }

        output_text = json.dumps(result_payload, indent=2, ensure_ascii=False)
        return CallToolResult(
            content=[TextContent(text=output_text)],
            isError=not report.success,
        )

    except Exception as exc:
        logger.exception("Falha inesperada ao executar cenário")
        return CallToolResult(
            content=[TextContent(text=f"Erro na execução do cenário: {exc}")],
            isError=True,
        )


async def inspect_url(
    url: str,
    viewport: str = "desktop",
    check_a11y: bool = True,
    check_visual: bool = True,
    config: GlobalConfig | None = None,
) -> CallToolResult:
    """Executa inspeção ad-hoc rápida de QA Visual e Acessibilidade em uma URL."""
    if not (url.startswith("http://") or url.startswith("https://")):
        return CallToolResult(
            content=[TextContent(text="URL inválida. A URL deve iniciar com http:// ou https://")],
            isError=True,
        )

    try:
        cfg = config or load_config()
        vp = parse_viewport_spec(viewport)

        from uxsentinel.browser.axe_runner import AxeRunner, calculate_a11y_score
        from uxsentinel.browser.session import open_browser_session

        a11y_violations_data: list[dict[str, Any]] = []
        a11y_score: float | None = None
        visual_issues: list[dict[str, Any]] = []

        async with open_browser_session(cfg.browser, headless=True) as (_browser, context):
            page = await context.new_page()
            await page.set_viewport_size({"width": vp.width, "height": vp.height})
            await page.goto(url, wait_until="load", timeout=30000)

            # 1. Auditoria de Acessibilidade Axe-Core WCAG 2.2 AA
            if check_a11y:
                axe = AxeRunner()
                violations: list[AxeViolation] = await axe.run(page)
                a11y_score = calculate_a11y_score(violations)
                for v in violations:
                    a11y_violations_data.append(
                        {
                            "id": v.id,
                            "impact": v.impact,
                            "description": v.description,
                            "help": v.help,
                            "help_url": v.help_url,
                            "nodes_count": len(v.nodes),
                        }
                    )

            # 2. Inspeção de integridade visual e heurísticas de usabilidade
            if check_visual:
                # Análise estrutural de heurísticas no DOM da página
                dom_checks = await page.evaluate(
                    """() => {
                        const issues = [];
                        // Heurística: Elemento <html> deve declarar idioma
                        if (!document.documentElement.lang) {
                            issues.push({
                                categoria: "acessibilidade",
                                severidade: "media",
                                descricao: "A tag <html> não possui atributo 'lang' definido.",
                                sugestao_correcao: "Defina lang='pt-BR' ou o idioma principal da aplicação."
                            });
                        }
                        // Heurística: Imagens devem possuir atributo alt
                        const imgs = Array.from(document.querySelectorAll('img:not([alt])'));
                        if (imgs.length > 0) {
                            issues.push({
                                categoria: "acessibilidade",
                                severidade: "alta",
                                descricao: `${imgs.length} imagem(ns) encontrada(s) sem atributo 'alt'.`,
                                sugestao_correcao: "Adicione atributos alt descritivos nas tags <img>."
                            });
                        }
                        // Heurística: Botões devem conter texto legível ou aria-label
                        const emptyButtons = Array.from(document.querySelectorAll('button')).filter(b => {
                            const text = b.innerText || b.getAttribute('aria-label') || b.getAttribute('title');
                            return !text || !text.trim();
                        });
                        if (emptyButtons.length > 0) {
                            issues.push({
                                categoria: "regra_negocio",
                                severidade: "alta",
                                descricao: `${emptyButtons.length} botão(ões) interativo(s) sem rótulo ou texto descritivo.`,
                                sugestao_correcao: "Adicione texto visível ou aria-label nos botões identificados."
                            });
                        }
                        return issues;
                    }"""
                )
                visual_issues.extend(dom_checks)

        result_payload = {
            "url": url,
            "viewport": vp.label,
            "a11y_score": a11y_score,
            "a11y_violations_count": len(a11y_violations_data),
            "a11y_violations": a11y_violations_data,
            "visual_issues_count": len(visual_issues),
            "visual_issues": visual_issues,
            "status": "ok"
            if (not visual_issues and (a11y_score is None or a11y_score >= 80.0))
            else "issues_found",
        }

        output_text = json.dumps(result_payload, indent=2, ensure_ascii=False)
        return CallToolResult(
            content=[TextContent(text=output_text)],
            isError=False,
        )

    except Exception as exc:
        logger.exception("Falha inesperada ao inspecionar URL")
        return CallToolResult(
            content=[TextContent(text=f"Erro durante inspeção da URL: {exc}")],
            isError=True,
        )


def _find_latest_report_file(base_dir: Path | None = None) -> Path | None:
    """Busca o relatório de teste JSON mais recente gravado no sistema."""
    cwd = base_dir or Path.cwd()
    search_dirs = [cwd / "reports", cwd / "output", cwd]

    candidate_files: list[Path] = []
    for d in search_dirs:
        if d.is_dir():
            candidate_files.extend(d.glob("*_report.json"))

    if not candidate_files:
        return None

    # Ordena pelo timestamp de modificação mais recente
    candidate_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return candidate_files[0]


async def get_last_report(
    format: str = "summary",
    config: GlobalConfig | None = None,
) -> CallToolResult:
    """Retorna o resumo executivo, JSON integral ou markdown do último relatório de auditoria."""
    try:
        report_file = _find_latest_report_file()
        if not report_file or not report_file.is_file():
            return CallToolResult(
                content=[TextContent(text="Nenhum relatório de auditoria foi encontrado.")],
                isError=False,
            )

        raw_content = report_file.read_text(encoding="utf-8")
        data = json.loads(raw_content)

        if format == "json":
            return CallToolResult(
                content=[TextContent(text=raw_content)],
                isError=False,
            )

        if format == "markdown":
            md_file = report_file.with_suffix(".md")
            if md_file.is_file():
                return CallToolResult(
                    content=[TextContent(text=md_file.read_text(encoding="utf-8"))],
                    isError=False,
                )
            # Se não houver arquivo .md, converte os dados em markdown legível
            md_text = _format_report_markdown(data)
            return CallToolResult(
                content=[TextContent(text=md_text)],
                isError=False,
            )

        # Formato 'summary' (padrão)
        summary_text = _format_report_summary(data, str(report_file))
        return CallToolResult(
            content=[TextContent(text=summary_text)],
            isError=False,
        )

    except Exception as exc:
        logger.exception("Falha inesperada ao obter último relatório")
        return CallToolResult(
            content=[TextContent(text=f"Erro ao obter último relatório: {exc}")],
            isError=True,
        )


def _format_report_summary(data: dict[str, Any], filepath: str) -> str:
    """Gera um resumo executivo textual do relatório."""
    scenario_title = data.get("scenario_title") or data.get("scenario_id") or "Cenário Desconhecido"
    success = data.get("success", False)
    status_str = (
        "APROVADO (Sem inconformidades impeditivas)" if success else "REPROVADO (Inconformidades detectadas)"
    )
    duration = data.get("duration_seconds", 0.0)
    total_issues = data.get("total_issues", 0)
    bloqueantes = data.get("total_bloqueantes", 0)
    altas = data.get("total_altas", 0)
    medias = data.get("total_medias", 0)
    baixas = data.get("total_baixas", 0)
    a11y_score = data.get("a11y_score")

    lines = [
        f"📊 Relatório de Auditoria: {scenario_title}",
        f"• Status: {status_str}",
        f"• Duração: {duration:.2f}s",
        f"• Total de Problemas: {total_issues}",
        f"  - Bloqueantes: {bloqueantes}",
        f"  - Altas: {altas}",
        f"  - Médias: {medias}",
        f"  - Baixas: {baixas}",
    ]
    if a11y_score is not None:
        lines.append(f"• A11y Score: {a11y_score:.1f}/100")

    lines.append(f"• Arquivo: {filepath}")
    return "\n".join(lines)


def _format_report_markdown(data: dict[str, Any]) -> str:
    """Converte os dados do relatório em documento Markdown."""
    scenario_title = data.get("scenario_title") or data.get("scenario_id") or "Cenário Desconhecido"
    success = data.get("success", False)
    status_icon = "✅" if success else "❌"

    lines = [
        f"# {status_icon} Relatório UXSentinel: {scenario_title}",
        "",
        f"- **Status:** {'Aprovado' if success else 'Reprovado'}",
        f"- **Duração:** {data.get('duration_seconds', 0.0):.2f}s",
        f"- **Total de Inconformidades:** {data.get('total_issues', 0)}",
        f"- **A11y Score:** {data.get('a11y_score', 'N/A')}",
        "",
        "## Resumo de Severidades",
        f"- **Bloqueantes:** {data.get('total_bloqueantes', 0)}",
        f"- **Altas:** {data.get('total_altas', 0)}",
        f"- **Médias:** {data.get('total_medias', 0)}",
        f"- **Baixas:** {data.get('total_baixas', 0)}",
    ]
    return "\n".join(lines)


async def handle_resource_read(uri: str) -> ResourceContent:
    """Lê o conteúdo do recurso MCP solicitado."""
    if uri == "uxsentinel://scenarios":
        files = _find_all_scenario_files()
        scenarios_catalog: list[dict[str, Any]] = []
        for f in files:
            try:
                sc = load_scenario(str(f), auto_register=False)
                scenarios_catalog.append(
                    {
                        "id": sc.id,
                        "title": sc.title,
                        "profile": sc.profile,
                        "path": str(f),
                        "tags": sc.tags,
                        "steps_count": len(sc.steps),
                    }
                )
            except Exception:
                continue
        return ResourceContent(
            uri=uri,
            mimeType="application/json",
            text=json.dumps(scenarios_catalog, indent=2, ensure_ascii=False),
        )

    if uri == "uxsentinel://reports/latest":
        report_file = _find_latest_report_file()
        if not report_file:
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps({"message": "Nenhum relatório encontrado"}, ensure_ascii=False),
            )
        content = report_file.read_text(encoding="utf-8")
        return ResourceContent(
            uri=uri,
            mimeType="application/json",
            text=content,
        )

    raise ValueError(f"Recurso MCP não encontrado para a URI: '{uri}'")

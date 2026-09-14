import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from uxsentinel import __version__
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import (
    load_config,
    resolve_axe_mode,
    resolve_baseline_mode,
    resolve_devtools_mode,
    resolve_display_mode,
    resolve_markdown_mode,
    resolve_video_mode,
    resolve_viewports,
)
from uxsentinel.scenarios.parser import load_scenario

console = Console()


def find_project_scenarios() -> list[Path]:
    """Descobre cenários YAML no projeto corrente (onde o comando foi invocado)."""
    cwd = Path.cwd()
    candidates: list[Path] = []

    search_dirs = [
        cwd / "scenarios",
        cwd / ".uxsentinel" / "scenarios",
        cwd / "tests" / "scenarios",
        cwd,
    ]

    seen: set[Path] = set()
    for sdir in search_dirs:
        if sdir.is_dir():
            for ext in ("*.yaml", "*.yml"):
                for yml in sdir.glob(ext):
                    if yml.name in (
                        "config.yaml",
                        "config.example.yaml",
                        "uxsentinel.yaml",
                        ".uxsentinel.yaml",
                    ):
                        continue
                    resolved = yml.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(yml)

    return candidates


def list_available_scenarios() -> None:
    project_scenarios = find_project_scenarios()
    pkg_lib_dir = Path(__file__).resolve().parent / "scenarios" / "library"

    table = Table(title="Cenários Detectados para Execução")
    table.add_column("Origem", style="dim")
    table.add_column("Caminho / Arquivo", style="cyan")
    table.add_column("Título", style="white")
    table.add_column("Perfil", style="magenta")
    table.add_column("Tags", style="green")

    for yml in project_scenarios:
        try:
            sc = load_scenario(str(yml))
            rel = yml.relative_to(Path.cwd()) if yml.is_relative_to(Path.cwd()) else yml
            table.add_row("📍 Projeto Atual", str(rel), sc.title, sc.profile, ", ".join(sc.tags))
        except Exception as err:
            table.add_row("📍 Projeto Atual", yml.name, f"[red]Erro: {err}[/red]", "-", "-")

    if pkg_lib_dir.is_dir():
        for yml in sorted(pkg_lib_dir.glob("*.yaml")):
            try:
                sc = load_scenario(str(yml))
                table.add_row("📦 Biblioteca Interna", yml.name, sc.title, sc.profile, ", ".join(sc.tags))
            except Exception as err:
                table.add_row("📦 Biblioteca Interna", yml.name, f"[red]Erro: {err}[/red]", "-", "-")

    console.print(table)


def resolve_scenario_path(scenario_arg: str | None = None) -> Path:
    """Resolve o arquivo de cenário obrigatório.

    1. Primeiro verifica se a pasta 'scenarios/' existe no projeto atual.
    2. Se a pasta não existir, verifica se o cenário foi passado como parâmetro.
    3. Se em nenhum dos casos, levanta FileNotFoundError.
    """
    cwd = Path.cwd()
    scenarios_dir = cwd / "scenarios"
    pkg_lib = Path(__file__).resolve().parent / "scenarios" / "library"

    # Caso 1: A pasta scenarios/ NÃO existe no projeto atual
    if not scenarios_dir.is_dir():
        if not scenario_arg:
            raise FileNotFoundError(
                "A pasta de cenários 'scenarios/' não existe no diretório atual e nenhum cenário foi informado como parâmetro (-s / --scenario)."
            )

        candidates = [
            cwd / scenario_arg,
            Path(scenario_arg),
            pkg_lib / scenario_arg,
        ]
        for c in candidates:
            if c.is_file():
                return c
            if c.with_suffix(".yaml").is_file():
                return c.with_suffix(".yaml")
            if c.with_suffix(".yml").is_file():
                return c.with_suffix(".yml")

        raise FileNotFoundError(
            f"A pasta 'scenarios/' não existe e o arquivo de cenário '{scenario_arg}' informado como parâmetro não foi encontrado."
        )

    # Caso 2: A pasta scenarios/ EXISTE no projeto atual
    if scenario_arg:
        candidates = [
            cwd / scenario_arg,
            scenarios_dir / scenario_arg,
            Path(scenario_arg),
            pkg_lib / scenario_arg,
        ]
        for c in candidates:
            if c.is_file():
                return c
            if c.with_suffix(".yaml").is_file():
                return c.with_suffix(".yaml")
            if c.with_suffix(".yml").is_file():
                return c.with_suffix(".yml")

        raise FileNotFoundError(
            f"Arquivo de cenário '{scenario_arg}' informado como parâmetro não foi encontrado no projeto nem na pasta 'scenarios/'."
        )

    # A pasta scenarios/ existe e nenhum parâmetro foi passado: busca arquivos dentro dela
    found_scenarios: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        for yml in scenarios_dir.glob(ext):
            if yml.name not in (
                "config.yaml",
                "config.example.yaml",
                "uxsentinel.yaml",
                ".uxsentinel.yaml",
            ):
                found_scenarios.append(yml)

    if not found_scenarios:
        raise FileNotFoundError(
            f"A pasta de cenários '{scenarios_dir}' existe, mas não contém nenhum arquivo de cenário (.yaml/.yml) válido."
        )

    found_scenarios.sort()
    if len(found_scenarios) > 1:
        names = ", ".join(f"'{f.name}'" for f in found_scenarios)
        raise ValueError(
            f"A pasta de cenários '{scenarios_dir}' contém múltiplos cenários ({names}). "
            "É obrigatório informar o parâmetro (-s / --scenario) para especificar qual cenário executar."
        )

    return found_scenarios[0]


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        description="""UXSentinel 🛡️👁️ - Agente Universal de QA Visual, UX e Proteção de Regras de Negócio

Audita aplicações web (Odoo, React, Vue, Angular, Django) navegando com ritmo humano
visível na tela e inspecionando cada checkpoint com Inteligência Artificial Multimodal.""",
        epilog="""Exemplos de Execução:
  uxsentinel                                           # Executa o cenário único em ./scenarios/
  uxsentinel -s scenarios/fluxo_vendas.yaml            # Executa um cenário específico
  uxsentinel scenarios/fluxo_vendas.yaml               # Executa passando o cenário como argumento direto
  uxsentinel -s scenarios/teste.yaml --devtools        # Inspeciona ao vivo com DevTools/Console Chromium acoplado
  uxsentinel -s scenarios/teste.yaml --md              # Gera relatório em Markdown (.md) para MarkText e Obsidian
  uxsentinel -s scenarios/teste.yaml --viewports desktop,tablet,mobile # Auditoria de responsividade multi-viewport
  uxsentinel -s scenarios/teste.yaml --update-baseline # Homologa e atualiza a baseline visual de referência
  uxsentinel -s scenarios/teste.yaml --video           # Grava a sessão completa de navegação em vídeo
  uxsentinel -s scenarios/teste.yaml --axe             # Executa auditoria de acessibilidade Axe-Core WCAG 2.2
  uxsentinel -s scenarios/teste.yaml -p gemini_sso     # Executa com Google Gemini via SSO
  uxsentinel -s scenarios/teste.yaml -p claude_sso     # Executa com Anthropic Claude via SSO
  uxsentinel -s scenarios/teste.yaml -p ollama_local  # Executa com IA 100% local (Ollama)
  uxsentinel -s scenarios/odoo_teste.yaml --profile odoo # Executa com driver especializado para Odoo OWL
  uxsentinel -s scenarios/teste.yaml --slowmo 500       # Executa com delay de 500ms entre passos
  uxsentinel -s scenarios/teste.yaml --headless        # Executa sem interface gráfica (modo CI/CD / headless)
  uxsentinel -s scenarios/teste.yaml --headed          # Força abertura visual da janela (modo headed / gui)
  uxsentinel -s scenarios/teste.yaml --no-gui          # Alias para --headless / --silent
  uxsentinel -s scenarios/teste.yaml --gui             # Alias para --headed / --visible
  uxsentinel --check-ai                                # Testa a conexão com o provedor de IA configurado
  uxsentinel --check-ai -p gemini_sso                  # Testa a conexão com o Gemini via SSO
  uxsentinel --login-sso -p gemini_sso                 # Abre o navegador para autenticar no Gemini via SSO
  uxsentinel --login-sso -p claude_sso                 # Abre o navegador para autenticar no Claude via SSO
  uxsentinel --logout-sso                              # Remove a sessão SSO salva em cache
  uxsentinel -s scenarios/teste.yaml --fix-prompt      # Gera prompt técnico de correção para IAs (Claude, Cursor, etc.)
  uxsentinel -s scenarios/teste.yaml --jira            # Cria issues automaticamente no Jira para inconformidades
  uxsentinel --set-jira-token                          # Configura token e URL do Jira interativamente
  uxsentinel --list-scenarios                          # Lista todos os cenários disponíveis no projeto e biblioteca
  uxsentinel --version                                 # Exibe a versão instalada (ou -v)
  uxsentinel --init-config                             # Cria o arquivo de configuração em ~/.config/uxsentinel/config.yaml

Documentação completa: https://github.com/Defendi/UXSentinel""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Exibe a versão do UXSentinel e encerra.",
    )
    parser.add_argument(
        "scenario_pos",
        nargs="?",
        default=None,
        metavar="SCENARIO",
        help="Caminho do arquivo YAML do cenário (opcional se passado via -s/--scenario ou se existir a pasta scenarios/).",
    )
    parser.add_argument(
        "-s",
        "--scenario",
        help="Caminho do arquivo YAML do cenário (busca no projeto corrente ou na biblioteca).",
        default=None,
    )
    parser.add_argument(
        "-p",
        "--provider",
        help="Sobrescreve o provedor de IA ativo (ex: gemini_cloud, gemini_sso, claude_sso, anthropic_cloud, openai_cloud, ollama_local, corporate_gateway).",
    )
    parser.add_argument(
        "--profile",
        help="Sobrescreve o perfil de framework (ex: generic, odoo).",
    )
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--headless",
        "--no-gui",
        "--silent",
        dest="headless",
        action="store_true",
        default=None,
        help="Força execução do navegador em modo invisível / background (sem GUI).",
    )
    display_group.add_argument(
        "--headed",
        "--gui",
        "--visible",
        dest="headless",
        action="store_false",
        default=None,
        help="Força abertura visual da janela do Chromium mesmo se o cenário/config indicar headless.",
    )
    devtools_group = parser.add_mutually_exclusive_group()
    devtools_group.add_argument(
        "--devtools",
        "--console",
        "--inspect",
        dest="devtools",
        action="store_true",
        default=None,
        help="Abre o navegador Chromium com o painel DevTools / Console acoplado para inspeção ao vivo de logs, erros e rede.",
    )
    devtools_group.add_argument(
        "--no-devtools",
        "--no-console",
        dest="devtools",
        action="store_false",
        default=None,
        help="Desativa a abertura automática da janela do DevTools do Chromium.",
    )
    video_group = parser.add_mutually_exclusive_group()
    video_group.add_argument(
        "--record-video",
        "--video",
        dest="record_video",
        action="store_true",
        default=None,
        help="Grava a sessão completa de navegação em vídeo (.webm/.mp4).",
    )
    video_group.add_argument(
        "--no-video",
        dest="record_video",
        action="store_false",
        default=None,
        help="Desativa a gravação de vídeo da sessão.",
    )
    viewport_group = parser.add_mutually_exclusive_group()
    viewport_group.add_argument(
        "--viewports",
        type=str,
        default=None,
        help="Lista de viewports separadas por vírgula para auditoria de responsividade (ex: 'desktop,tablet,mobile' ou '1920x1080,375x812').",
    )
    viewport_group.add_argument(
        "--viewport",
        type=str,
        default=None,
        help="Preset ou resolução única de viewport (ex: 'desktop', 'mobile', '1280x720').",
    )
    axe_group = parser.add_mutually_exclusive_group()
    axe_group.add_argument(
        "--axe",
        dest="enable_axe",
        action="store_true",
        default=None,
        help="Ativa a auditoria de acessibilidade automatizada com motor Axe-Core (WCAG 2.2 AA).",
    )
    axe_group.add_argument(
        "--no-axe",
        dest="enable_axe",
        action="store_false",
        default=None,
        help="Desativa a auditoria de acessibilidade Axe-Core.",
    )
    baseline_group = parser.add_argument_group("Baseline Visual e Regressão")
    baseline_group.add_argument(
        "--update-baseline",
        action="store_true",
        dest="update_baseline",
        default=None,
        help="Salva/sobrescreve os screenshots homologados como nova referência (baseline visual).",
    )
    baseline_group.add_argument(
        "--baseline-dir",
        type=str,
        default=None,
        help="Diretório de baselines de referência (padrão: scenarios/baselines).",
    )
    baseline_group.add_argument(
        "--diff-threshold",
        type=float,
        default=None,
        help="Limiar percentual de tolerância para divergência visual (default: 0.1%%).",
    )
    parser.add_argument(
        "--slowmo",
        type=int,
        help="Delay em milissegundos entre passos (ex: 350, 500) para acompanhamento humano.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        "--report-dir",
        dest="output_dir",
        default=None,
        help="Diretório onde relatórios e screenshots serão salvos (opcional; se não informado, usa 'scenarios/report').",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Caminho do arquivo de configuração (padrão: busca no projeto atual ou no pacote).",
    )
    parser.add_argument(
        "--fix-prompt",
        "--generate-fix-prompt",
        action="store_true",
        dest="fix_prompt",
        help="Gera um documento Markdown com prompt técnico de correção para agentes de IA (Claude Code, Cursor, Copilot).",
    )
    markdown_group = parser.add_mutually_exclusive_group()
    markdown_group.add_argument(
        "--markdown",
        "--md",
        "--report-md",
        dest="markdown",
        action="store_true",
        default=None,
        help="Gera relatório de auditoria em documento Markdown (.md) formatado para o editor MarkText e Obsidian.",
    )
    markdown_group.add_argument(
        "--no-markdown",
        "--no-md",
        dest="markdown",
        action="store_false",
        default=None,
        help="Desativa a geração do relatório de auditoria em Markdown.",
    )
    parser.add_argument(
        "--jira",
        "--create-jira-cards",
        action="store_true",
        dest="jira",
        help="Cria cards/issues automaticamente no Atlassian Jira para as inconformidades encontradas.",
    )
    parser.add_argument(
        "--jira-project",
        type=str,
        default=None,
        help="Sobrescreve a chave do projeto no Jira (ex: PROJ, UXS) para criação dos cards.",
    )
    parser.add_argument(
        "--set-jira-token",
        action="store_true",
        help="Configura interativamente o token e credenciais do Jira no arquivo global (~/.config/uxsentinel/config.yaml).",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Cria o arquivo de configuração padrão do usuário em ~/.config/uxsentinel/config.yaml (sem precisar de sudo).",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Lista os cenários do projeto atual e da biblioteca interna e encerra.",
    )
    parser.add_argument(
        "--check-ai",
        action="store_true",
        help="Testa a conectividade com o provedor de IA configurado e encerra.",
    )
    parser.add_argument(
        "--login-sso",
        action="store_true",
        help="Abre o navegador para autenticação SSO com o serviço de LLM e salva a sessão em cache.",
    )
    parser.add_argument(
        "--logout-sso",
        action="store_true",
        help="Remove as credenciais SSO em cache do provedor e encerra.",
    )

    args = parser.parse_args()

    if args.init_config:
        from uxsentinel.core.config import ensure_user_config, get_user_config_dir

        cfg_file = ensure_user_config()
        cfg_dir = get_user_config_dir()
        console.print(f"[bold green]✓[/bold green] Diretório de configuração: [cyan]{cfg_dir}[/cyan]")
        console.print(
            f"[bold green]✓[/bold green] Arquivo de configuração criado/pronto: [cyan]{cfg_file}[/cyan]"
        )
        console.print(
            "[dim]Você pode editar este arquivo livremente sem privilégios de administrador (sudo).[/dim]"
        )
        return 0

    if args.list_scenarios:
        list_available_scenarios()
        return 0

    cfg = load_config(args.config)

    if args.set_jira_token:
        from uxsentinel.core.config import JiraSettings, get_user_config_path, save_jira_config
        from uxsentinel.integrations.jira import JiraClient

        cfg_path = get_user_config_path()
        console.print("\n[bold cyan]🔧 Configuração Global do Atlassian Jira[/bold cyan]")
        console.print(f"[dim]Arquivo: {cfg_path}[/dim]\n")

        current_jira = cfg.jira
        default_url = current_jira.url or "https://sua-empresa.atlassian.net"
        jira_url = console.input(f"URL do Jira [{default_url}]: ").strip() or default_url

        default_email = (
            current_jira.email if current_jira.email and not current_jira.email.startswith("${") else ""
        )
        email_prompt = f"E-mail Atlassian [{default_email}]: " if default_email else "E-mail Atlassian: "
        jira_email = console.input(email_prompt).strip() or default_email

        token_prompt = "API Token / PAT (Personal Access Token)"
        has_existing_token = bool(current_jira.api_token and not current_jira.api_token.startswith("${"))
        if has_existing_token:
            token_prompt += " [pressione Enter para manter atual]"
        token_prompt += ": "

        jira_token = console.input(token_prompt, password=True).strip()
        if not jira_token and has_existing_token:
            jira_token = current_jira.api_token

        if not jira_token:
            console.print("[bold red]❌ Erro:[/bold red] O API Token do Jira é obrigatório.")
            return 1

        default_proj = (
            current_jira.project_key
            if current_jira.project_key and not current_jira.project_key.startswith("${")
            else ""
        )
        proj_prompt = (
            f"Chave do Projeto [{default_proj}]: " if default_proj else "Chave do Projeto (ex: PROJ): "
        )
        jira_proj = console.input(proj_prompt).strip() or default_proj

        saved_file = save_jira_config(
            url=jira_url,
            email=jira_email,
            api_token=jira_token,
            project_key=jira_proj,
            enabled=True,
        )
        console.print(
            f"\n[bold green]✓ Configurações do Jira salvas com sucesso em:[/bold green] [cyan]{saved_file}[/cyan]"
        )
        console.print(
            "[dim]Permissões do arquivo restritas a 0600 (somente leitura/escrita pelo seu usuário).[/dim]\n"
        )

        # Teste rápido de conectividade
        console.print("🔍 Testando conectividade com o Jira...")
        test_settings = JiraSettings(
            enabled=True,
            url=jira_url,
            email=jira_email,
            api_token=jira_token,
            project_key=jira_proj,
        )
        test_client = JiraClient(test_settings)
        ok, msg = await test_client.test_connection()
        if ok:
            console.print(f"[bold green]✓ Conexão com o Jira estabelecida com sucesso:[/bold green] {msg}\n")
        else:
            console.print(f"[yellow]⚠️ Aviso de conectividade:[/yellow] {msg}\n")
        return 0

    if args.provider:
        cfg.active_provider = args.provider

    if args.logout_sso:
        from uxsentinel.core.sso import clear_cached_token

        target = args.provider or cfg.active_provider
        cleared = clear_cached_token(target)
        if cleared:
            console.print(
                f"[bold green]✓[/bold green] Credenciais SSO do provedor [bold yellow]{target}[/bold yellow] removidas com sucesso."
            )
        else:
            console.print(f"[dim]Nenhuma credencial SSO em cache encontrada para '{target}'.[/dim]")
        return 0

    if args.login_sso:
        from uxsentinel.core.sso import login_via_browser

        target_provider_name = args.provider or cfg.active_provider
        if target_provider_name not in cfg.providers:
            console.print(
                f"[bold red]Erro:[/bold red] Provedor '{target_provider_name}' não encontrado no arquivo de configuração."
            )
            return 1
        provider = cfg.providers[target_provider_name]
        try:
            login_via_browser(target_provider_name, provider)
            return 0
        except Exception as exc:
            console.print(f"[bold red]❌ Falha no login SSO:[/bold red] {exc}")
            return 1

    if args.check_ai:
        from uxsentinel.vision.client import UnifiedVisionClient

        client = UnifiedVisionClient(cfg)
        console.print(
            f"🔍 Testando conexão com o provedor de IA: [bold yellow]{cfg.active_provider}[/bold yellow]..."
        )
        ok, msg = await client.test_connection(check_fallback=(args.provider is None))
        if ok:
            console.print(f"[bold green]✓ Conexão bem-sucedida:[/bold green] {msg}")
            return 0
        else:
            console.print(f"[bold red]❌ Falha na conexão com a IA:[/bold red] {msg}")
            return 1

    if args.fix_prompt:
        cfg.reporting.generate_fix_prompt = True
    if args.jira:
        cfg.jira.enabled = True
    if args.jira_project:
        cfg.jira.project_key = args.jira_project

    if args.slowmo is not None:
        cfg.browser.slow_mo_ms = args.slowmo
    if args.output_dir:
        cfg.reporting.output_dir = args.output_dir
    elif not cfg.reporting.output_dir or cfg.reporting.output_dir == "report":
        cfg.reporting.output_dir = "scenarios/report"

    scenario_arg = args.scenario or args.scenario_pos
    try:
        scenario_path = resolve_scenario_path(scenario_arg)
    except (FileNotFoundError, ValueError) as err:
        console.print(f"[bold red]Erro de Cenário:[/bold red] {err}")
        console.print(
            "[yellow]Dica:[/yellow] Especifique o cenário usando [bold]-s caminho/do/cenario.yaml[/bold] ou liste os cenários com [bold]--list-scenarios[/bold]."
        )
        return 1

    scenario = load_scenario(str(scenario_path))
    if args.profile:
        scenario.profile = args.profile
    if args.provider:
        cfg.active_provider = args.provider
    elif scenario.provider:
        cfg.active_provider = scenario.provider

    # Hierarquia de resolução do modo de visualização (Headless vs Headed):
    # 1. CLI flag (--headless/--no-gui/--silent vs --headed/--gui/--visible)
    # 2. Cenário YAML (campo 'headless' no arquivo do cenário)
    # 3. Config global config.yaml (BrowserSettings.headless)
    # 4. Fallback padrão: False (visível com ritmo humano)
    cfg.browser.headless = resolve_display_mode(
        cli_headless=args.headless,
        scenario_headless=scenario.headless,
        config_headless=cfg.browser.headless,
    )

    # Hierarquia de resolução da gravação de vídeo:
    # 1. CLI flag (--record-video/--video vs --no-video)
    # 2. Cenário YAML (campo 'video' no arquivo do cenário)
    # 3. Config global config.yaml (BrowserSettings.record_video)
    # 4. Fallback padrão: False
    cfg.browser.record_video = resolve_video_mode(
        cli_video=args.record_video,
        scenario_video=scenario.video,
        config_video=cfg.browser.record_video,
    )

    # Hierarquia de resolução de viewports:
    # 1. CLI flag (--viewports / --viewport)
    # 2. Cenário YAML (campo 'viewports' no arquivo do cenário)
    # 3. Config global config.yaml (BrowserSettings.viewports)
    # 4. Fallback padrão: desktop padrão 1280x800
    cli_viewport_arg = args.viewports or args.viewport
    cfg.browser.viewports = resolve_viewports(
        cli_viewports=cli_viewport_arg,
        scenario_viewports=scenario.viewports,
        config_viewports=cfg.browser.viewports,
    )

    # Hierarquia de resolução do modo Axe-Core:
    # 1. CLI flag (--axe / --no-axe)
    # 2. Cenário YAML (campo 'axe')
    # 3. Config global (BrowserSettings.enable_axe)
    # 4. Fallback padrão: True
    cfg.browser.enable_axe = resolve_axe_mode(
        cli_axe=args.enable_axe,
        scenario_axe=scenario.axe,
        config_axe=cfg.browser.enable_axe,
    )

    # Hierarquia de resolução do Baseline Visual:
    # 1. CLI flag (--update-baseline, --baseline-dir, --diff-threshold)
    # 2. Cenário YAML (campos 'update_baseline', 'baseline_dir', 'diff_threshold')
    # 3. Config global (cfg.baseline)
    if args.baseline_dir:
        cfg.baseline.baseline_dir = args.baseline_dir
    elif scenario.baseline_dir:
        cfg.baseline.baseline_dir = scenario.baseline_dir

    if args.diff_threshold is not None:
        cfg.baseline.diff_threshold = args.diff_threshold
    elif scenario.diff_threshold is not None:
        cfg.baseline.diff_threshold = scenario.diff_threshold

    cfg.baseline.update_baseline = resolve_baseline_mode(
        cli_update_baseline=args.update_baseline,
        scenario_update_baseline=scenario.update_baseline,
        config_update_baseline=cfg.baseline.update_baseline,
    )

    # Hierarquia de resolução do Relatório Markdown (MarkText/Obsidian):
    # 1. CLI flag (--markdown / --md / --report-md vs --no-markdown / --no-md)
    # 2. Cenário YAML (campo 'markdown')
    # 3. Config global (ReportingSettings.generate_markdown)
    # 4. Fallback padrão: False
    cfg.reporting.generate_markdown = resolve_markdown_mode(
        cli_markdown=args.markdown,
        scenario_markdown=scenario.markdown,
        config_markdown=cfg.reporting.generate_markdown,
    )

    # Hierarquia de resolução do DevTools / Console do Chromium:
    # 1. CLI flag (--devtools / --console / --inspect vs --no-devtools)
    # 2. Cenário YAML (campo 'devtools')
    # 3. Config global (BrowserSettings.devtools)
    # 4. Fallback padrão: False
    cfg.browser.devtools = resolve_devtools_mode(
        cli_devtools=args.devtools,
        scenario_devtools=scenario.devtools,
        config_devtools=cfg.browser.devtools,
    )
    if cfg.browser.devtools:
        # DevTools requer modo com janela visível
        cfg.browser.headless = False

    agent = UXSentinelAgent(
        cfg,
        headless_override=args.headless,
        record_video_override=args.record_video,
        viewports_override=cli_viewport_arg,
        enable_axe_override=args.enable_axe,
        update_baseline_override=args.update_baseline,
        baseline_dir_override=args.baseline_dir,
        diff_threshold_override=args.diff_threshold,
        markdown_override=args.markdown,
        devtools_override=args.devtools,
    )
    report = await agent.run_scenario(
        scenario,
        update_baseline_override=args.update_baseline,
        baseline_dir_override=args.baseline_dir,
        diff_threshold_override=args.diff_threshold,
        markdown_override=args.markdown,
        devtools_override=args.devtools,
    )

    await asyncio.sleep(0.05)
    return 0 if report.success else 1


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            exit_code = loop.run_until_complete(async_main())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(asyncio.sleep(0.05))
            except Exception:
                pass
            loop.close()
            asyncio.set_event_loop(None)
    except KeyboardInterrupt:
        console.print("\n[yellow]Execução cancelada pelo usuário.[/yellow]")
        sys.exit(130)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

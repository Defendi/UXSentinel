import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from uxsentinel import __version__
from uxsentinel.core.config import (
    GlobalConfig,
    find_project_in_catalog,
    find_scenario_in_project,
    list_registered_projects,
    load_config,
)
from uxsentinel.scenarios.parser import load_scenario
from uxsentinel.service.execution_service import ExecutionOptions, ExecutionService

console = Console()

# Códigos de saída para esteiras de CI/CD
EXIT_SUCESSO = 0
EXIT_INCONFORMIDADES = 1
EXIT_ERRO_EXECUCAO = 2


def find_project_scenarios() -> list[Path]:
    """Descobre cenários YAML no projeto corrente (onde o comando foi invocado)."""
    cwd = Path.cwd()
    candidates: list[Path] = []

    search_dirs = [
        cwd / "scenarios",
        cwd / "scenarios" / "generated",
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


def list_registered_projects_cli(config_path: Path | None = None) -> None:
    """Exibe no terminal a tabela com os projetos cadastrados no catálogo global e seus cenários."""
    projects = list_registered_projects(config_path)

    if not projects:
        console.print(
            "[yellow]Nenhum projeto cadastrado no catálogo global (~/.config/uxsentinel/config.yaml).[/yellow]"
        )
        console.print(
            "[dim]Execute um cenário com 'uxsentinel -s <cenario.yaml>' para registrá-lo automaticamente.[/dim]"
        )
        return

    table = Table(title="Catálogo de Projetos & Cenários Registrados")
    table.add_column("ID / Slug", style="cyan bold")
    table.add_column("Nome do Projeto", style="white bold")
    table.add_column("Diretório Raiz", style="dim")
    table.add_column("Cenários", style="green")
    table.add_column("Última Execução", style="yellow")

    for p_id, p_entry in sorted(projects.items(), key=lambda item: item[1].name):
        scenarios_desc: list[str] = []
        for s_id, s_item in sorted(p_entry.scenarios.items(), key=lambda item: item[1].name):
            scenarios_desc.append(f"• [bold]{s_item.name}[/bold] ({s_id})")
        scenarios_str = "\n".join(scenarios_desc) if scenarios_desc else "[dim](nenhum)[/dim]"
        last_run_str = p_entry.last_run[:19].replace("T", " ") if p_entry.last_run else "-"
        table.add_row(p_id, p_entry.name, p_entry.root_path, scenarios_str, last_run_str)

    console.print(table)


def handle_select_project(config_path: Path | None = None) -> str | None:
    """Exibe menu interativo para o usuário selecionar um projeto do catálogo global."""
    from rich.prompt import Prompt

    catalog = list_registered_projects(config_path)
    if not catalog:
        console.print(
            "[yellow]Nenhum projeto cadastrado no catálogo global (~/.config/uxsentinel/config.yaml).[/yellow]"
        )
        return None

    items = sorted(catalog.items(), key=lambda x: x[1].name)
    table = Table(title="Projetos Registrados no UXSentinel")
    table.add_column("#", style="bold cyan", justify="right")
    table.add_column("Projeto", style="bold white")
    table.add_column("Identificador / Slug", style="dim")
    table.add_column("Cenários", style="green", justify="center")

    for idx, (p_id, p_entry) in enumerate(items, start=1):
        table.add_row(str(idx), p_entry.name, p_id, str(len(p_entry.scenarios)))

    console.print(table)
    try:
        choice = Prompt.ask(
            "[bold cyan]Selecione o número do projeto que deseja executar[/bold cyan] (ou 'q' para sair)"
        )
    except (EOFError, KeyboardInterrupt):
        return None

    choice_str = choice.strip()
    if choice_str.lower() in ("q", "sair", "exit", "cancel", "cancelar"):
        return None

    try:
        choice_idx = int(choice_str)
        if 1 <= choice_idx <= len(items):
            return items[choice_idx - 1][0]
    except ValueError:
        pass

    for p_id, p_entry in items:
        if choice_str.lower() in (p_id.lower(), p_entry.name.lower()):
            return p_id

    console.print("[red]Opção inválida selecionada.[/red]")
    return None


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


def build_arg_parser() -> argparse.ArgumentParser:
    """Constrói o parser de argumentos de linha de comando."""
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
  uxsentinel -s scenarios/teste.yaml --stream-events eventos.jsonl # Transmite eventos em tempo real em JSON Lines
  uxsentinel -s scenarios/teste.yaml --fix-prompt      # Gera prompt técnico de correção para IAs (Claude, Cursor, etc.)
  uxsentinel -s scenarios/teste.yaml --jira            # Cria issues automaticamente no Jira para inconformidades
  uxsentinel --set-jira-token                          # Configura token e URL do Jira interativamente
  uxsentinel --list-scenarios                          # Lista todos os cenários disponíveis no projeto e biblioteca
  uxsentinel --list-projects                           # Lista os projetos cadastrados no catálogo global e seus cenários
  uxsentinel -s scenarios/teste.yaml --project-name "Alpha" # Associa o cenário ao projeto especificado
  uxsentinel -P "Meu Projeto"                          # Executa todos os cenários do projeto pelo nome/slug
  uxsentinel -P "Meu Projeto" -s login                 # Executa um cenário específico dentro do projeto
  uxsentinel --scenario-path /caminho/cenario.yaml     # Executa cenário externo em caminho arbitrário
  uxsentinel --select-project                          # Menu interativo para selecionar projeto do catálogo
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
    parser.add_argument(
        "--project-name",
        type=str,
        default=None,
        help="Sobrescreve ou define o nome do projeto no catálogo para repetição de QA.",
    )
    parser.add_argument(
        "-P",
        "--project",
        type=str,
        default=None,
        metavar="PROJETO",
        help="Executa cenários do projeto especificado registrado no catálogo pelo nome ou identificador.",
    )
    parser.add_argument(
        "--scenario-path",
        "--external-scenario",
        type=str,
        default=None,
        dest="scenario_path",
        metavar="CAMINHO",
        help="Executa diretamente um arquivo YAML de cenário em caminho arbitrário fora do diretório de trabalho.",
    )
    parser.add_argument(
        "--select-project",
        action="store_true",
        help="Abre menu interativo no terminal para selecionar e executar um projeto cadastrado no catálogo.",
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
    css_group = parser.add_mutually_exclusive_group()
    css_group.add_argument(
        "--css",
        dest="enable_css",
        action="store_true",
        default=None,
        help="Ativa a auditoria e inspeção híbrida de CSS (layout, overflow, especificidade e boas práticas).",
    )
    css_group.add_argument(
        "--no-css",
        dest="enable_css",
        action="store_false",
        default=None,
        help="Desativa a auditoria de CSS.",
    )
    parser.add_argument(
        "--audit-css",
        type=str,
        default=None,
        metavar="TARGET",
        help="Executa auditoria de CSS isolada e direta (URL da web ou arquivo/diretório .css) exibindo tabela Rich no terminal.",
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
    parser.add_argument(
        "--stream-events",
        type=Path,
        default=None,
        metavar="ARQUIVO",
        help="Caminho para arquivo .jsonl onde os eventos da execução serão gravados em tempo real.",
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
    archive_group = parser.add_mutually_exclusive_group()
    archive_group.add_argument(
        "--archive",
        dest="archive",
        action="store_true",
        default=None,
        help="Compacta os relatórios e artefatos da análise anterior em arquivo ZIP antes da nova execução.",
    )
    archive_group.add_argument(
        "--no-archive",
        dest="archive",
        action="store_false",
        default=None,
        help="Desativa o arquivamento automático dos relatórios da análise anterior.",
    )
    fail_fast_group = parser.add_mutually_exclusive_group()
    fail_fast_group.add_argument(
        "--fail-fast",
        dest="fail_fast",
        action="store_true",
        default=None,
        help="Interrompe a execução imediatamente ao encontrar uma falha grave de elemento ou validação (padrão).",
    )
    fail_fast_group.add_argument(
        "--no-fail-fast",
        dest="fail_fast",
        action="store_false",
        default=None,
        help="Permite que a execução continue mesmo após falhas em passos ou asserções.",
    )
    parser.add_argument(
        "--archive-dir",
        type=str,
        default=None,
        help="Diretório onde os arquivos ZIP arquivados serão salvos (padrão: output_dir / 'archive').",
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
        "--list-projects",
        action="store_true",
        help="Lista todos os projetos cadastrados no catálogo global (~/.config/uxsentinel/config.yaml) e seus cenários associados e encerra.",
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
    crawl_group = parser.add_argument_group("Modo Exploratório Autônomo (Crawling - UXS-12)")
    crawl_group.add_argument(
        "--crawl",
        type=str,
        default=None,
        metavar="URL",
        help="Inicia o modo exploratório autônomo (crawling) a partir da URL informada.",
    )
    crawl_group.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Profundidade máxima de navegação no crawling (padrão: 3).",
    )
    crawl_group.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Número máximo de páginas a serem visitadas no crawling (padrão: 50).",
    )
    gen_group = crawl_group.add_mutually_exclusive_group()
    gen_group.add_argument(
        "--generate-scenarios",
        dest="generate_scenarios",
        action="store_true",
        default=True,
        help="Gera arquivos YAML de cenários para as jornadas navegadas (padrão: ativado).",
    )
    gen_group.add_argument(
        "--no-generate-scenarios",
        dest="generate_scenarios",
        action="store_false",
        help="Desativa a geração automática de cenários YAML.",
    )
    crawl_group.add_argument(
        "--crawl-output-dir",
        type=str,
        default="scenarios/generated",
        help="Diretório onde os cenários gerados e evidências do crawler serão salvos (padrão: 'scenarios/generated').",
    )

    return parser


def handle_init_config() -> int:
    """Manipula a flag --init-config criando o template de configuração do usuário."""
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


async def handle_set_jira_token(cfg: GlobalConfig) -> int:
    """Manipula a configuração interativa de credenciais Jira."""
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
    proj_prompt = f"Chave do Projeto [{default_proj}]: " if default_proj else "Chave do Projeto (ex: PROJ): "
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


def handle_logout_sso(cfg: GlobalConfig, provider_override: str | None) -> int:
    """Remove credenciais SSO salvas em cache."""
    from uxsentinel.core.sso import clear_cached_token

    target = provider_override or cfg.active_provider
    cleared = clear_cached_token(target)
    if cleared:
        console.print(
            f"[bold green]✓[/bold green] Credenciais SSO do provedor [bold yellow]{target}[/bold yellow] removidas com sucesso."
        )
    else:
        console.print(f"[dim]Nenhuma credencial SSO em cache encontrada para '{target}'.[/dim]")
    return 0


def handle_login_sso(cfg: GlobalConfig, provider_override: str | None) -> int:
    """Abre navegador para autenticação SSO interativa."""
    from uxsentinel.core.config import BUILTIN_PROVIDERS
    from uxsentinel.core.sso import login_via_browser

    target_provider_name = provider_override or cfg.active_provider
    provider = cfg.providers.get(target_provider_name) or BUILTIN_PROVIDERS.get(target_provider_name)
    if not provider:
        console.print(
            f"[bold red]Erro:[/bold red] Provedor '{target_provider_name}' não encontrado no arquivo de configuração."
        )
        return 1
    try:
        login_via_browser(target_provider_name, provider)
        return 0
    except Exception as exc:
        console.print(f"[bold red]❌ Falha no login SSO:[/bold red] {exc}")
        return 1


async def handle_check_ai(cfg: GlobalConfig, provider_override: str | None) -> int:
    """Testa conectividade com a API de IA configurada."""
    from uxsentinel.vision.client import UnifiedVisionClient

    client = UnifiedVisionClient(cfg)
    console.print(
        f"🔍 Testando conexão com o provedor de IA: [bold yellow]{cfg.active_provider}[/bold yellow]..."
    )
    ok, msg = await client.test_connection(check_fallback=(provider_override is None))
    if ok:
        console.print(f"[bold green]✓ Conexão bem-sucedida:[/bold green] {msg}")
        return 0
    else:
        console.print(f"[bold red]❌ Falha na conexão com a IA:[/bold red] {msg}")
        return 1


async def handle_audit_css(target: str, cfg: GlobalConfig) -> int:
    """Executa auditoria profunda de CSS em uma URL ao vivo ou arquivo/diretório estático."""
    from rich.table import Table

    from uxsentinel.css.models import CSSSeverity
    from uxsentinel.css.runner import CSSInspector

    is_url = target.startswith("http://") or target.startswith("https://")
    console.print(f"🎨 [bold cyan]Iniciando Auditoria de CSS (UXS-47):[/bold cyan] [yellow]{target}[/yellow]")

    if is_url:
        from uxsentinel.browser.context import open_browser_session

        browser_cfg = cfg.browser
        async with open_browser_session(browser_cfg) as (browser, context):
            page = await context.new_page()
            try:
                await page.goto(target, wait_until="networkidle", timeout=30000)
            except Exception as e:
                console.print(f"[bold red]❌ Falha ao navegar até a URL:[/bold red] {e}")
                return EXIT_ERRO_EXECUCAO
            report = await CSSInspector.audit_page(page)
    else:
        target_path = Path(target)
        if not target_path.exists():
            console.print(f"[bold red]❌ Alvo não encontrado:[/bold red] {target}")
            return EXIT_ERRO_EXECUCAO
        report = CSSInspector.audit_file_or_dir(target_path)

    table = Table(title=f"Resultados da Auditoria de CSS - Score: {report.score:.1f}/100")
    table.add_column("Severidade", style="bold")
    table.add_column("Regra", style="cyan")
    table.add_column("Seletor / Arquivo", style="magenta")
    table.add_column("Descrição")
    table.add_column("Sugestão", style="green")

    sev_styles = {
        CSSSeverity.BLOQUEANTE: "[bold white on red] BLOQUEANTE [/bold white on red]",
        CSSSeverity.ALTA: "[bold red]ALTA[/bold red]",
        CSSSeverity.MEDIA: "[bold yellow]MEDIA[/bold yellow]",
        CSSSeverity.BAIXA: "[bold blue]BAIXA[/bold blue]",
    }

    for v in report.violations:
        sev_label = sev_styles.get(v.severity, str(v.severity.value))
        target_col = v.selector or v.snippet or "-"
        table.add_row(sev_label, v.rule_id, target_col[:40], v.description, v.suggestion or "-")

    console.print(table)
    summary_text = ", ".join(f"{k}: {v}" for k, v in report.summary.items())
    console.print(
        f"[bold]Regras inspecionadas:[/bold] {report.total_rules_inspected} | [bold]Violações:[/bold] {len(report.violations)} ({summary_text})"
    )

    has_bloqueante = any(v.severity == CSSSeverity.BLOQUEANTE for v in report.violations)
    return EXIT_INCONFORMIDADES if has_bloqueante or report.violations else EXIT_SUCESSO


async def handle_crawl(args: argparse.Namespace, cfg: GlobalConfig) -> int:
    """Executa o modo exploratório autônomo (crawling)."""
    from uxsentinel.crawler import Crawler, CrawlOptions

    console.print(
        f"\n🕷️ [bold cyan]Iniciando Modo Exploratório Autônomo (UXS-12):[/bold cyan] [yellow]{args.crawl}[/yellow]"
    )
    console.print(
        f"[dim]Profundidade Máxima: {args.max_depth} | Limite de Páginas: {args.max_pages} | Output: {args.crawl_output_dir}[/dim]\n"
    )

    headless = args.headless if args.headless is not None else cfg.browser.headless
    options = CrawlOptions(
        start_url=args.crawl,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        generate_scenarios=args.generate_scenarios,
        output_dir=args.crawl_output_dir,
        headless=headless,
        profile=args.profile or "generic",
    )

    crawler = Crawler(options)
    result = await crawler.run()

    # Exibe resumo no terminal
    table = Table(title="Resultado da Exploração Autônoma")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="bold white")

    status_str = result.get("status", "unknown").upper()
    status_fmt = (
        f"[bold green]{status_str}[/bold green]"
        if status_str == "COMPLETED"
        else f"[bold yellow]{status_str}[/bold yellow]"
    )
    table.add_row("Status", status_fmt)
    table.add_row("Páginas Visitadas", str(result.get("visited_count", 0)))
    table.add_row("Páginas na Fila (Restantes)", str(result.get("queued_count", 0)))
    table.add_row("Erros Detectados", str(len(result.get("errors", []))))
    table.add_row("Cenários YAML Gerados", str(len(result.get("generated_scenarios", []))))

    console.print(table)

    errors = result.get("errors", [])
    if errors:
        err_table = Table(title="Inconformidades e Falhas Graves Detectadas")
        err_table.add_column("Severidade", style="bold")
        err_table.add_column("URL", style="cyan")
        err_table.add_column("Tipo", style="magenta")
        err_table.add_column("Detalhes")
        err_table.add_column("Recuo (Backtrack)", justify="center")

        for err in errors:
            sev_label = (
                "[bold white on red] BLOQUEANTE [/bold white on red]"
                if err.get("severity") == "bloqueante"
                else "[bold red]ALTA[/bold red]"
            )
            bt_label = "[green]Sucesso[/green]" if err.get("backtrack_success") else "[red]Falhou[/red]"
            err_table.add_row(
                sev_label,
                err.get("url", "-"),
                err.get("error_type", "-"),
                err.get("message", "-"),
                bt_label,
            )

        console.print(err_table)

    gen_scenarios = result.get("generated_scenarios", [])
    if gen_scenarios:
        console.print("\n[bold green]✓ Cenários gerados prontos para execução:[/bold green]")
        for sc_file in gen_scenarios:
            console.print(f"  • [cyan]{sc_file}[/cyan]")

    has_blocking = any(e.get("severity") == "bloqueante" for e in errors)
    if has_blocking:
        return EXIT_ERRO_EXECUCAO
    if errors:
        return EXIT_INCONFORMIDADES
    return EXIT_SUCESSO


async def async_main() -> int:
    """Ponto de entrada assíncrono principal da CLI do UXSentinel."""
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.init_config:
        return handle_init_config()

    if args.list_scenarios:
        list_available_scenarios()
        return EXIT_SUCESSO

    if args.list_projects:
        cfg_path = Path(args.config) if args.config else None
        list_registered_projects_cli(cfg_path)
        return EXIT_SUCESSO

    cfg = load_config(args.config)

    if args.set_jira_token:
        return await handle_set_jira_token(cfg)

    if args.provider:
        cfg.active_provider = args.provider

    if args.logout_sso:
        return handle_logout_sso(cfg, args.provider)

    if args.login_sso:
        return handle_login_sso(cfg, args.provider)

    if args.check_ai:
        return await handle_check_ai(cfg, args.provider)

    if args.audit_css:
        return await handle_audit_css(args.audit_css, cfg)

    if args.crawl:
        return await handle_crawl(args, cfg)

    cfg_path = Path(args.config) if args.config else None

    # Modo interativo de seleção de projeto
    project_target = args.project
    if args.select_project:
        selected = handle_select_project(cfg_path)
        if selected is None:
            return EXIT_SUCESSO
        project_target = selected

    scenarios_to_run: list[Path] = []
    project_display_name: str | None = None

    if project_target:
        p_match = find_project_in_catalog(project_target, cfg_path)
        if not p_match:
            console.print(
                f"[bold red]Erro:[/bold red] Projeto '{project_target}' não encontrado no catálogo global."
            )
            all_p = list_registered_projects(cfg_path)
            if all_p:
                console.print("[yellow]Projetos disponíveis no catálogo:[/yellow]")
                for pid, pent in sorted(all_p.items(), key=lambda x: x[1].name):
                    console.print(f"  • [bold]{pent.name}[/bold] (slug: [cyan]{pid}[/cyan])")
            else:
                console.print("[yellow]Nenhum projeto cadastrado no catálogo global.[/yellow]")
            return EXIT_ERRO_EXECUCAO

        _p_id, p_entry = p_match
        project_display_name = p_entry.name
        if not p_entry.scenarios:
            console.print(f"[yellow]O projeto '{p_entry.name}' não possui cenários registrados.[/yellow]")
            return EXIT_ERRO_EXECUCAO

        scenario_query = args.scenario or args.scenario_pos
        if scenario_query:
            scen_item = find_scenario_in_project(p_entry, scenario_query)
            if not scen_item:
                console.print(
                    f"[bold red]Erro:[/bold red] Cenário '{scenario_query}' não encontrado no projeto '{p_entry.name}'."
                )
                console.print("[yellow]Cenários disponíveis neste projeto:[/yellow]")
                for _sid, sitem in sorted(p_entry.scenarios.items(), key=lambda x: x[1].name):
                    console.print(f"  • [bold]{sitem.name}[/bold] (id: [cyan]{sitem.id}[/cyan])")
                return EXIT_ERRO_EXECUCAO
            scenarios_to_run = [Path(scen_item.path)]
        else:
            scenarios_to_run = [
                Path(s.path) for s in sorted(p_entry.scenarios.values(), key=lambda x: x.name)
            ]

    elif args.scenario_path:
        ext_path = Path(args.scenario_path).resolve()
        if not ext_path.is_file():
            console.print(
                f"[bold red]Erro de Cenário Externo:[/bold red] Arquivo '{args.scenario_path}' não foi encontrado."
            )
            return EXIT_ERRO_EXECUCAO
        scenarios_to_run = [ext_path]

    else:
        scenario_arg = args.scenario or args.scenario_pos
        try:
            scenario_path = resolve_scenario_path(scenario_arg)
        except (FileNotFoundError, ValueError) as err:
            console.print(f"[bold red]Erro de Cenário:[/bold red] {err}")
            console.print(
                "[yellow]Dica:[/yellow] Especifique o cenário usando [bold]-s caminho/do/cenario.yaml[/bold], selecione um projeto com [bold]-P <projeto>[/bold] ou liste com [bold]--list-scenarios[/bold]."
            )
            return EXIT_ERRO_EXECUCAO
        scenarios_to_run = [scenario_path]

    # Validação e pré-carregamento dos cenários
    for sp in scenarios_to_run:
        if not sp.is_file():
            console.print(
                f"[bold red]Erro de Cenário:[/bold red] Arquivo '{sp}' não foi encontrado no sistema de arquivos."
            )
            return EXIT_ERRO_EXECUCAO
        try:
            load_scenario(str(sp), project_name=args.project_name, auto_register=True)
        except (yaml.YAMLError, ValueError, OSError) as err:
            console.print(f"[bold red]Erro ao ler o cenário '{sp.name}':[/bold red] {err}")
            return EXIT_ERRO_EXECUCAO

    execution_service = ExecutionService(cfg)

    # Execução de cenário único
    if len(scenarios_to_run) == 1:
        scenario_path = scenarios_to_run[0]
        event_bus = None
        streamer_cm: contextlib.AbstractContextManager = contextlib.nullcontext()
        if args.stream_events:
            from uxsentinel.core.events import EventBus, JsonLinesEventStreamer

            streamer = JsonLinesEventStreamer(args.stream_events)
            streamer_cm = streamer
            event_bus = EventBus()
            event_bus.subscribe(streamer)

        with streamer_cm:
            options = ExecutionOptions(
                scenario_path=scenario_path,
                provider=args.provider,
                profile=args.profile,
                headless=args.headless,
                devtools=args.devtools,
                record_video=args.record_video,
                viewports=args.viewports or args.viewport,
                enable_axe=args.enable_axe,
                enable_css=args.enable_css,
                update_baseline=args.update_baseline,
                baseline_dir=args.baseline_dir,
                diff_threshold=args.diff_threshold,
                slowmo=args.slowmo,
                output_dir=args.output_dir,
                markdown=args.markdown,
                fail_fast=args.fail_fast,
                archive=args.archive,
                archive_dir=args.archive_dir,
                jira=args.jira,
                jira_project=args.jira_project,
                fix_prompt=args.fix_prompt,
                stream_events=args.stream_events if not event_bus else None,
                event_bus=event_bus,
            )
            report = await execution_service.run(options)
        await asyncio.sleep(0.05)
        return EXIT_SUCESSO if report.success else EXIT_INCONFORMIDADES

    # Execução sequencial de múltiplos cenários do projeto
    console.print(
        f"\n[bold green]Iniciando execução de {len(scenarios_to_run)} cenários do projeto '[white]{project_display_name}[/white]'[/bold green]\n"
    )
    multi_results = []
    all_success = True

    event_bus = None
    streamer_cm: contextlib.AbstractContextManager = contextlib.nullcontext()
    if args.stream_events:
        from uxsentinel.core.events import EventBus, JsonLinesEventStreamer

        streamer = JsonLinesEventStreamer(args.stream_events)
        streamer_cm = streamer
        event_bus = EventBus()
        event_bus.subscribe(streamer)

    with streamer_cm:
        for idx, sc_path in enumerate(scenarios_to_run, start=1):
            console.print(
                f"[bold cyan]▶ [{idx}/{len(scenarios_to_run)}] Executando Cenário: {sc_path.stem}[/bold cyan]"
            )
            options = ExecutionOptions(
                scenario_path=sc_path,
                provider=args.provider,
                profile=args.profile,
                headless=args.headless,
                devtools=args.devtools,
                record_video=args.record_video,
                viewports=args.viewports or args.viewport,
                enable_axe=args.enable_axe,
                enable_css=args.enable_css,
                update_baseline=args.update_baseline,
                baseline_dir=args.baseline_dir,
                diff_threshold=args.diff_threshold,
                slowmo=args.slowmo,
                output_dir=args.output_dir,
                markdown=args.markdown,
                fail_fast=args.fail_fast,
                archive=args.archive if idx == 1 else False,
                archive_dir=args.archive_dir,
                jira=args.jira,
                jira_project=args.jira_project,
                fix_prompt=args.fix_prompt,
                event_bus=event_bus,
            )
            rep = await execution_service.run(options)
            multi_results.append((sc_path.stem, rep))
            if not rep.success:
                all_success = False

    # Sumário consolidado
    summary_table = Table(title=f"Sumário Consolidado de Execução - {project_display_name}")
    summary_table.add_column("Cenário", style="bold cyan")
    summary_table.add_column("Resultado", justify="center")
    summary_table.add_column("Passos", justify="center")
    summary_table.add_column("Problemas", justify="center")
    summary_table.add_column("Duração", justify="right")

    for name, rep in multi_results:
        res_label = "[bold green]PASSOU[/bold green]" if rep.success else "[bold red]FALHOU[/bold red]"
        steps_count = str(len(rep.semantic_steps) or len(rep.checkpoints) or 0)
        viol_count = str(rep.total_issues)
        dur_label = f"{rep.duration_seconds:.1f}s"
        summary_table.add_row(name, res_label, steps_count, viol_count, dur_label)

    console.print("\n")
    console.print(summary_table)
    await asyncio.sleep(0.05)
    return EXIT_SUCESSO if all_success else EXIT_INCONFORMIDADES


def _graceful_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """Cancela e drena graciosamente todas as tasks pendentes (ex: Connection.run do Playwright) antes de fechar o loop."""
    try:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(asyncio.sleep(0.05))
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            loop.close()
        asyncio.set_event_loop(None)


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            exit_code = loop.run_until_complete(async_main())
        finally:
            _graceful_shutdown(loop)
    except KeyboardInterrupt:
        console.print("\n[yellow]Execução cancelada pelo usuário.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[bold red]Erro inesperado na execução:[/bold red] {exc}")
        sys.exit(EXIT_ERRO_EXECUCAO)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

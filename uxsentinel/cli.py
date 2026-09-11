import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from uxsentinel import __version__
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import load_config
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
  uxsentinel -s scenarios/teste.yaml -p gemini_sso     # Executa com Google Gemini via SSO
  uxsentinel -s scenarios/teste.yaml -p claude_sso     # Executa com Anthropic Claude via SSO
  uxsentinel -s scenarios/teste.yaml -p ollama_local  # Executa com IA 100% local (Ollama)
  uxsentinel -s scenarios/odoo_teste.yaml --profile odoo # Executa com driver especializado para Odoo OWL
  uxsentinel -s scenarios/teste.yaml --slowmo 500       # Executa com delay de 500ms entre passos
  uxsentinel -s scenarios/teste.yaml --headless        # Executa sem interface gráfica (modo CI/CD)
  uxsentinel --check-ai                                # Testa a conexão com o provedor de IA configurado
  uxsentinel --check-ai -p gemini_sso                  # Testa a conexão com o Gemini via SSO
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
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa o navegador em modo invisível (sem GUI). Padrão é visível.",
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

    if args.provider:
        cfg.active_provider = args.provider

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
    if args.headless:
        cfg.browser.headless = True
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

    agent = UXSentinelAgent(cfg)
    report = await agent.run_scenario(scenario)

    return 0 if report.success else 1


def main() -> None:
    try:
        sys.exit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Execução cancelada pelo usuário.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()

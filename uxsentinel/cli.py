import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

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


def resolve_scenario_path(scenario_arg: str | None) -> Path | None:
    cwd = Path.cwd()
    pkg_lib = Path(__file__).resolve().parent / "scenarios" / "library"

    if scenario_arg:
        candidate1 = cwd / scenario_arg
        if candidate1.is_file():
            return candidate1

        candidate2 = Path(scenario_arg)
        if candidate2.is_file():
            return candidate2

        candidate3 = cwd / "scenarios" / scenario_arg
        if candidate3.is_file():
            return candidate3

        candidate4 = pkg_lib / scenario_arg
        if candidate4.is_file():
            return candidate4

        for c in (candidate1, candidate2, candidate3, candidate4):
            with_yaml = c.with_suffix(".yaml")
            if with_yaml.is_file():
                return with_yaml

        return None

    project_scenarios = find_project_scenarios()
    if project_scenarios:
        return project_scenarios[0]

    default_pkg = pkg_lib / "exemplo_web_geral.yaml"
    if default_pkg.is_file():
        return default_pkg

    return None


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        description="UXSentinel 🛡️👁️ - Agente Universal de QA Visual, UX e Proteção de Regras de Negócio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="Sobrescreve o provedor de IA ativo (ex: anthropic_cloud, openai_cloud, gemini_cloud, ollama_local, corporate_gateway).",
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
        help="Diretório onde relatórios e screenshots serão salvos (padrão: ./report dentro do projeto analisado).",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Caminho do arquivo de configuração (padrão: busca no projeto atual ou no pacote).",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Lista os cenários do projeto atual e da biblioteca interna e encerra.",
    )

    args = parser.parse_args()

    if args.list_scenarios:
        list_available_scenarios()
        return 0

    cfg = load_config(args.config)

    if args.provider:
        cfg.active_provider = args.provider
    if args.headless:
        cfg.browser.headless = True
    if args.slowmo is not None:
        cfg.browser.slow_mo_ms = args.slowmo
    if args.output_dir:
        cfg.reporting.output_dir = args.output_dir

    scenario_path = resolve_scenario_path(args.scenario)
    if not scenario_path or not scenario_path.is_file():
        console.print(
            f"[bold red]Erro:[/bold red] Nenhum arquivo de cenário encontrado para: '{args.scenario or 'auto-discovery'}'"
        )
        console.print(
            "[yellow]Dica:[/yellow] Crie uma pasta [bold]scenarios/[/bold] com arquivos [bold].yaml[/bold] no seu projeto ou use [bold]--list-scenarios[/bold]."
        )
        return 1

    scenario = load_scenario(str(scenario_path))
    if args.profile:
        scenario.profile = args.profile

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

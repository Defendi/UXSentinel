import argparse
import contextlib
import os
import sys
import webbrowser
from pathlib import Path

import uvicorn
from rich.console import Console
from rich.panel import Panel

from uxsentinel import __version__ as core_version
from uxsentinel_studio import __version__ as studio_version
from uxsentinel_studio.server import create_app, get_session_token

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    epilog = """Exemplos práticos de uso:
  uxsentinel-studio --version
  uxsentinel-studio --help
  uxsentinel-studio --info
  uxsentinel-studio --list-providers
  uxsentinel-studio --list-projects
  uxsentinel-studio --list-scenarios
  uxsentinel-studio -p 9000
  uxsentinel-studio --no-browser
  uxsentinel-studio -d /caminho/projeto
"""
    parser = argparse.ArgumentParser(
        prog="uxsentinel-studio",
        description="UXSentinel Studio 🛡️ - Painel de Controle Visual e Web App (Live Mission Control)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        metavar="COMANDO",
        help="Subcomando opcional (version, info, status, providers, projects, scenarios)",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"uxsentinel-studio {studio_version} (uxsentinel core {core_version})",
        help="Exibe a versão do UXSentinel Studio e do Core e encerra.",
    )

    parser.add_argument(
        "--info",
        "--status",
        action="store_true",
        dest="info",
        help="Exibe painel diagnóstico com versões, configuração ativa, provedor de IA, diretório alvo e contagens, e encerra.",
    )

    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="Lista todos os provedores de LLM/IA compatíveis e o provedor ativo e encerra.",
    )

    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="Lista os projetos registrados no catálogo do UXSentinel e encerra.",
    )

    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Lista os cenários YAML disponíveis no diretório do projeto alvo e encerra.",
    )

    parser.add_argument(
        "-c", "--config", type=str, default=None, help="Caminho opcional para o arquivo config.yaml."
    )

    parser.add_argument(
        "-p", "--port", type=int, default=8765, help="Porta HTTP do servidor local (padrão: 8765)."
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Endereço de bind do servidor local (padrão: 127.0.0.1 - estritamente local).",
    )

    parser.add_argument(
        "-d",
        "--project-dir",
        type=str,
        default=None,
        help="Diretório base do projeto alvo a ser analisado (padrão: diretório atual).",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abre automaticamente a janela do navegador padrão ao iniciar.",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="warning",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Nível de log do servidor Uvicorn (padrão: warning).",
    )

    return parser.parse_args(argv)


def show_studio_info(project_dir: Path, config_path: str | None = None) -> None:
    from uxsentinel.core.config import get_user_config_path, list_registered_projects, load_config

    cfg = load_config(config_path)
    provider_name = cfg.active_provider or "Nenhum"
    provider_obj = cfg.get_active_provider()
    model_name = provider_obj.model if provider_obj else "N/A"

    scenarios_dir = project_dir / "scenarios"
    yaml_count = 0
    if scenarios_dir.is_dir():
        yaml_count = len(list(scenarios_dir.glob("*.yaml"))) + len(list(scenarios_dir.glob("*.yml")))

    cfg_path = Path(config_path) if config_path else None
    projects = list_registered_projects(cfg_path)
    projects_count = len(projects)

    panel_content = f"""[bold purple]🛡️ UXSentinel Studio - Diagnóstico[/bold purple]

[bold]Versões:[/bold]
• Studio: [cyan]{studio_version}[/cyan]
• Core: [cyan]{core_version}[/cyan]

[bold]Configuração Ativa:[/bold]
• Arquivo: [yellow]{get_user_config_path()}[/yellow]
• Provedor IA: [green]{provider_name}[/green]
• Modelo: [green]{model_name}[/green]
• Projetos Registrados: [blue]{projects_count}[/blue]

[bold]Projeto Alvo:[/bold]
• Diretório: [blue]{project_dir}[/blue]
• Cenários YAML em 'scenarios/': [blue]{yaml_count}[/blue]"""

    console.print(Panel(panel_content, border_style="purple"))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.command == "version":
        print(f"uxsentinel-studio {studio_version} (uxsentinel core {core_version})")
        sys.exit(0)

    project_dir = Path(args.project_dir).resolve() if args.project_dir else Path.cwd()

    if args.info or args.command in ("info", "status"):
        show_studio_info(project_dir, args.config)
        sys.exit(0)

    if args.list_providers or args.command in ("providers", "list-providers", "list_providers"):
        from uxsentinel.cli import list_supported_providers
        from uxsentinel.core.config import load_config

        cfg = load_config(args.config)
        list_supported_providers(cfg)
        sys.exit(0)

    if args.list_projects or args.command in ("projects", "list-projects", "list_projects"):
        from uxsentinel.cli import list_registered_projects_cli

        list_registered_projects_cli(Path(args.config) if args.config else None)
        sys.exit(0)

    if args.list_scenarios or args.command in ("scenarios", "list-scenarios", "list_scenarios"):
        import inspect

        from uxsentinel.cli import list_available_scenarios

        sig = inspect.signature(list_available_scenarios)
        if len(sig.parameters) > 0:
            list_available_scenarios(project_dir / "scenarios")
        else:
            old_cwd = Path.cwd()
            os.chdir(project_dir)
            try:
                list_available_scenarios()
            finally:
                os.chdir(old_cwd)
        sys.exit(0)

    if args.host != "127.0.0.1":
        console.print(
            "[bold red]Aviso de Segurança:[/bold red] Bind forçado para [bold]127.0.0.1[/bold] para proteger tokens e arquivos locais."
        )
        args.host = "127.0.0.1"

    app = create_app(project_dir=project_dir)
    token = get_session_token()

    studio_url = f"http://{args.host}:{args.port}/?token={token}"

    panel_content = f"""[bold purple]🛡️ UXSentinel Studio[/bold purple] [cyan]v{studio_version}[/cyan] (Core v{core_version})

🔗 [bold green]URL de Acesso:[/bold green] [underline]{studio_url}[/underline]
📁 [bold blue]Projeto Alvo:[/bold blue] {project_dir}
🔒 [bold yellow]Autenticação:[/bold yellow] Token de sessão ativo e efêmero

[dim]Pressione [bold]CTRL+C[/bold] para encerrar o servidor.[/dim]"""

    console.print(Panel(panel_content, border_style="purple"))

    if not args.no_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(studio_url)

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            access_log=False,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Servidor UXSentinel Studio encerrado com sucesso.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()

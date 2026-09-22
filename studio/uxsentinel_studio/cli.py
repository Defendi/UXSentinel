"""Entrypoint CLI para o UXSentinel Studio (UXS-48 / STU-01)."""

import argparse
import contextlib
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
    parser = argparse.ArgumentParser(
        prog="uxsentinel-studio",
        description="Painel de Controle Visual e Web App do UXSentinel (Mission Control)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Porta HTTP do servidor local (padrão: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Endereço de bind do servidor local (padrão: 127.0.0.1 - estritamente local)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abre automaticamente a janela do navegador padrão ao iniciar",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Diretório base do projeto alvo a ser analisado (padrão: diretório atual)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Força bind seguro se alguém passar 0.0.0.0 inadvertidamente
    if args.host != "127.0.0.1":
        console.print(
            "[bold red]Aviso de Segurança:[/bold red] Bind forçado para [bold]127.0.0.1[/bold] para proteger tokens e arquivos locais."
        )
        args.host = "127.0.0.1"

    project_dir = Path(args.project_dir).resolve() if args.project_dir else Path.cwd()
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
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Servidor UXSentinel Studio encerrado com sucesso.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()

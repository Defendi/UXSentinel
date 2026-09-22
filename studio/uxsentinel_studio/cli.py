"""Entrypoint CLI para o UXSentinel Studio."""

import sys

from rich.console import Console

console = Console()


def main() -> None:
    """Executa o console placeholder do Studio."""
    console.print("[bold purple]🛡️ UXSentinel Studio[/bold purple] [cyan]v1.0.0[/cyan]")
    console.print("[dim]Inicializador do servidor web e SPA. Em preparação...[/dim]")
    sys.exit(0)


if __name__ == "__main__":
    main()

"""Servidor FastAPI e segurança do UXSentinel Studio (UXS-49 / STU-02)."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from uxsentinel import __version__ as core_version
from uxsentinel_studio import __version__ as studio_version
from uxsentinel_studio.api import router as api_router
from uxsentinel_studio.security import (
    get_session_token,
    set_session_token,
    verify_studio_token,
)

__all__ = [
    "create_app",
    "get_session_token",
    "set_session_token",
    "verify_studio_token",
]


def create_app(project_dir: Path | str | None = None) -> FastAPI:
    """Fábrica de aplicação FastAPI configurada com rotas, segurança e SPA estática."""
    app = FastAPI(
        title="UXSentinel Studio API",
        version=studio_version,
        docs_url=None,  # Protege interface Swagger por padrão em ambiente local
        redoc_url=None,
    )

    proj_path = Path(project_dir).resolve() if project_dir else Path.cwd()
    app.state.project_dir = proj_path

    # CORS restrito para loopback local
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registra rotas REST da API sob o prefixo /api
    app.include_router(api_router, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index(request: Request, token: str | None = None) -> Any:
        """Serve a página principal da SPA injetando o token de sessão no sessionStorage."""
        static_dir = Path(__file__).resolve().parent / "static"
        index_file = static_dir / "index.html"

        target_token = token or request.cookies.get("studio-token", "")
        token_injection = f"""<script>
            if ('{target_token}') {{
                sessionStorage.setItem('studio_token', '{target_token}');
            }}
        </script>"""

        if index_file.is_file():
            content = index_file.read_text(encoding="utf-8")
            if "</head>" in content:
                content = content.replace("</head>", f"{token_injection}</head>")
            else:
                content = f"{token_injection}\n{content}"
            return HTMLResponse(content=content)

        # Fallback enquanto a SPA Vue 3 não estiver compilada na static/
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>UXSentinel Studio</title>
    {token_injection}
    <style>
        body {{
            background: #0f1117;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #1e2130;
            padding: 2.5rem;
            border-radius: 12px;
            border: 1px solid #2d3248;
            text-align: center;
            max-width: 500px;
        }}
        h1 {{ color: #a78bfa; margin-top: 0; }}
        code {{ background: #13151f; padding: 0.2rem 0.5rem; border-radius: 4px; color: #38bdf8; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🛡️ UXSentinel Studio</h1>
        <p>Servidor FastAPI ativo com segurança e token de sessão efêmero.</p>
        <p>Versão do Studio: <code>{studio_version}</code> | Core: <code>{core_version}</code></p>
        <p><small style="color: #94a3b8">Diretório: {app.state.project_dir}</small></p>
    </div>
</body>
</html>"""
        )

    # Monta arquivos estáticos da SPA se existirem
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount(
            "/static",
            StaticFiles(directory=str(static_dir), check_dir=False),
            name="static",
        )
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir), check_dir=False),
                name="assets",
            )

    return app

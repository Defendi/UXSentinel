"""Gerenciador de autenticação SSO (Single Sign-On) com abertura de navegador."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import http.server
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from uxsentinel.core.config import ProviderSettings

console = Console()

DEFAULT_SSO_PORT_START = 8085
DEFAULT_SSO_PORT_END = 8095

# Constantes OAuth 2.0 PKCE para Claude.ai (Contas Pro / Team)
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize"
CLAUDE_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLAUDE_OAUTH_SCOPES = "user:profile user:inference user:sessions:claude_code"


def generate_pkce_pair() -> tuple[str, str]:
    """Gera code_verifier e code_challenge (S256 base64url) conforme RFC 7636."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def get_sso_cache_dir() -> Path:
    """Retorna o diretório de cache de autenticação do usuário."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_config) if xdg_config else Path.home() / ".config"
    sso_dir = base_dir / "uxsentinel"
    sso_dir.mkdir(parents=True, exist_ok=True)
    return sso_dir


def get_sso_cache_file() -> Path:
    """Retorna o arquivo de cache de tokens SSO."""
    return get_sso_cache_dir() / "sso_cache.json"


def refresh_claude_oauth_token(refresh_token: str) -> str | None:
    """Renova o token OAuth do Claude.ai usando o refresh_token."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token.strip(),
        "client_id": CLAUDE_OAUTH_CLIENT_ID,
        "scope": CLAUDE_OAUTH_SCOPES,
    }
    try:
        req = urllib.request.Request(
            CLAUDE_OAUTH_TOKEN_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "claude-cli/2.1.267",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("accessToken") or data.get("access_token")
            expires_in = data.get("expires_in")
            if token:
                save_cached_token("claude_sso", str(token).strip(), expires_in)
                return str(token).strip()
    except Exception:
        pass
    return None


def get_cached_token(provider_name: str) -> str | None:
    """Recupera o token SSO armazenado em cache para o provedor, se válido."""
    cache_file = get_sso_cache_file()
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            item = data.get(provider_name)
            if item:
                # Verifica expiração se houver
                expires_at = item.get("expires_at")
                if not expires_at or time.time() <= float(expires_at):
                    token = item.get("token")
                    if token and str(token).strip():
                        return str(token).strip()
        except Exception:
            pass

    # Fallback inteligente para sessão do Claude Pro existente na máquina (~/.claude/.credentials.json)
    if provider_name == "claude_sso":
        claude_creds = Path.home() / ".claude" / ".credentials.json"
        if claude_creds.is_file():
            try:
                cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                oauth = cdata.get("claudeAiOauth", {})
                token = oauth.get("accessToken")
                expires_at = oauth.get("expiresAt")
                if token:
                    if expires_at:
                        # Se expiresAt estiver em ms, converte para segundos
                        exp_sec = (
                            float(expires_at) / 1000.0 if float(expires_at) > 1e11 else float(expires_at)
                        )
                        if time.time() < exp_sec:
                            return str(token).strip()
                    else:
                        return str(token).strip()

                # Se o token expirou, tenta renovar via refresh_token
                ref_tok = oauth.get("refreshToken")
                if ref_tok:
                    refreshed = refresh_claude_oauth_token(ref_tok)
                    if refreshed:
                        return refreshed
            except Exception:
                pass

    return None


def save_cached_token(
    provider_name: str,
    token: str,
    expires_in: int | None = None,
) -> None:
    """Armazena o token de autenticação SSO no cache seguro local."""
    cache_file = get_sso_cache_file()
    data: dict = {}
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    item: dict = {"token": token.strip(), "updated_at": time.time()}
    if expires_in:
        item["expires_at"] = time.time() + expires_in

    data[provider_name] = item

    # Grava no disco com permissões restritas (apenas o próprio usuário)
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with contextlib.suppress(Exception):
        cache_file.chmod(0o600)


def clear_cached_token(provider_name: str | None = None) -> bool:
    """Remove um token específico ou todo o cache SSO."""
    cache_file = get_sso_cache_file()
    if not cache_file.is_file():
        return False

    if provider_name is None:
        cache_file.unlink(missing_ok=True)
        return True

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if provider_name in data:
            del data[provider_name]
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
    except Exception:
        return False
    return False


def _find_available_port(
    start_port: int = DEFAULT_SSO_PORT_START,
    end_port: int = DEFAULT_SSO_PORT_END,
) -> int:
    """Encontra uma porta TCP local livre dentro do intervalo."""
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # Fallback para qualquer porta disponível do sistema
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


HTML_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UXSentinel - Login SSO</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: rgba(22, 30, 49, 0.85);
      --border: rgba(255, 255, 255, 0.12);
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --success: #10b981;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(circle at top, #1e1b4b 0%, var(--bg) 70%);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 40px;
      width: 100%;
      max-width: 520px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }}
    .header {{
      text-align: center;
      margin-bottom: 28px;
    }}
    .logo {{
      font-size: 32px;
      margin-bottom: 8px;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 700;
      color: #fff;
    }}
    p.subtitle {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 6px;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 12px;
      border-radius: 999px;
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #818cf8;
      font-size: 12px;
      font-weight: 600;
      margin-top: 12px;
    }}
    .instructions {{
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 16px;
      font-size: 13px;
      line-height: 1.6;
      color: #cbd5e1;
      margin-bottom: 24px;
    }}
    .instructions strong {{ color: #fff; }}
    label {{
      display: block;
      font-size: 13px;
      font-weight: 600;
      color: #e2e8f0;
      margin-bottom: 8px;
    }}
    input[type="password"], input[type="text"] {{
      width: 100%;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 10px;
      padding: 12px 16px;
      color: #fff;
      font-size: 14px;
      font-family: monospace;
      outline: none;
      transition: border-color 0.2s;
      margin-bottom: 20px;
    }}
    input[type="password"]:focus, input[type="text"]:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
    }}
    button {{
      width: 100%;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 14px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }}
    button:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 20px -5px rgba(99, 102, 241, 0.5);
    }}
    .footer {{
      text-align: center;
      margin-top: 20px;
      font-size: 12px;
      color: var(--text-muted);
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="logo">🛡️👁️</div>
      <h1>UXSentinel SSO Login</h1>
      <p class="subtitle">Autenticação com o serviço de Inteligência Artificial</p>
      <div class="badge">Provedor: {provider_name}</div>
    </div>

    <div class="instructions">
      {instructions_html}
    </div>

    {extra_action_html}

    <form method="POST" action="/callback">
      <label for="token">Token de Acesso / Bearer SSO:</label>
      <input type="password" id="token" name="token" placeholder="Cole aqui seu token de sessão SSO (Bearer ou JWT)..." required autofocus>
      <button type="submit">Autorizar e Salvar Sessão</button>
    </form>

    <div class="footer">
      Esta conexão é estritamente local (127.0.0.1). O token é armazenado com segurança em seu computador.
    </div>
  </div>
</body>
</html>
"""

HTML_SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UXSentinel - Autenticado com Sucesso!</title>
  <style>
    body {{
      background: radial-gradient(circle at top, #064e3b 0%, #0b0f19 70%);
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      background: rgba(22, 30, 49, 0.9);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 20px;
      padding: 40px;
      text-align: center;
      max-width: 480px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }}
    .icon {{ font-size: 52px; margin-bottom: 16px; }}
    <h1>{{ font-size: 24px; color: #34d399; margin-bottom: 12px; }}
    p {{ color: #cbd5e1; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }}
    .badge {{
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #6ee7b7;
      padding: 6px 16px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Autenticado com Sucesso!</h1>
    <p>O token do provedor <strong>{provider_name}</strong> foi validado e salvo com segurança.<br>Você já pode fechar esta janela e voltar para o terminal.</p>
    <div class="badge">Sessão Ativa no UXSentinel</div>
  </div>
</body>
</html>
"""


class LoopbackAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handler HTTP para servir a tela de autenticação e receber o callback."""

    def log_message(self, format: str, *args: object) -> None:
        """Silencia logs HTTP padrão do servidor para não poluir o terminal."""
        return

    @property
    def server_instance(self) -> LoopbackAuthServer:
        return self.server  # type: ignore

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        # Rota para iniciar fluxo OAuth PKCE oficial com Claude.ai
        if parsed.path == "/oauth/claude/login":
            verifier, challenge = generate_pkce_pair()
            state = secrets.token_urlsafe(16)
            self.server_instance.code_verifier = verifier
            self.server_instance.oauth_state = state

            port = self.server_instance.server_address[1]
            oauth_params = {
                "code": "true",
                "client_id": CLAUDE_OAUTH_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": f"http://localhost:{port}/callback",
                "scope": CLAUDE_OAUTH_SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
            auth_url = f"{CLAUDE_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(oauth_params)}"

            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return

        # Se o token vier via query param (/callback?token=... ou /callback?code=...)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            token = params.get("token", [None])[0]

            # Se recebemos um authorization_code do Claude.ai e temos o code_verifier
            if code and self.server_instance.code_verifier:
                port = self.server_instance.server_address[1]
                token_payload = {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"http://localhost:{port}/callback",
                    "client_id": CLAUDE_OAUTH_CLIENT_ID,
                    "code_verifier": self.server_instance.code_verifier,
                    "state": self.server_instance.oauth_state or "",
                }
                try:
                    req = urllib.request.Request(
                        CLAUDE_OAUTH_TOKEN_URL,
                        data=json.dumps(token_payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "claude-cli/2.1.267",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        token = resp_data.get("accessToken") or resp_data.get("access_token")
                        expires_in = resp_data.get("expires_in")
                        if token:
                            save_cached_token(self.server_instance.provider_name, token, expires_in)
                except Exception:
                    token = code
            elif code and not token:
                token = code

            if token:
                self.server_instance.captured_token = token.strip()
                self._send_success_response()
                return

        # Página padrão de login
        self._send_login_page()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            token: str | None = None
            content_type = self.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    payload = json.loads(post_data.decode("utf-8"))
                    token = payload.get("token") or payload.get("code")
                except Exception:
                    pass
            else:
                form_fields = urllib.parse.parse_qs(post_data.decode("utf-8"))
                token = form_fields.get("token", [None])[0]

            if token:
                self.server_instance.captured_token = token.strip()
                self._send_success_response()
                return

        self.send_error(400, "Dados de autenticação inválidos.")

    def _send_login_page(self) -> None:
        provider_name = self.server_instance.provider_name
        instructions = self.server_instance.instructions_html

        extra_action_html = ""
        if "claude" in provider_name.lower():
            extra_action_html = """
            <div style="margin-bottom: 24px; text-align: center;">
              <a href="/oauth/claude/login" style="display: block; width: 100%; text-decoration: none; background: linear-gradient(135deg, #d97706 0%, #b45309 100%); color: #fff; border-radius: 10px; padding: 14px; font-weight: 700; font-size: 15px; box-shadow: 0 4px 14px rgba(217, 119, 6, 0.4);">
                ✨ Conectar com Conta Claude Pro / Team no Navegador
              </a>
              <p style="color: #94a3b8; font-size: 12px; margin-top: 8px;">Ou informe o token manualmente abaixo caso já possua:</p>
            </div>
            """

        content = HTML_LOGIN_PAGE.format(
            provider_name=html.escape(provider_name),
            instructions_html=instructions,
            extra_action_html=extra_action_html,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_success_response(self) -> None:
        provider_name = self.server_instance.provider_name
        content = HTML_SUCCESS_PAGE.format(provider_name=html.escape(provider_name)).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class LoopbackAuthServer(http.server.HTTPServer):
    """Servidor HTTP temporário para loopback de autenticação SSO."""

    def __init__(
        self,
        server_address: tuple[str, int],
        provider_name: str,
        instructions_html: str = "",
    ):
        super().__init__(server_address, LoopbackAuthHandler)
        self.provider_name = provider_name
        self.instructions_html = instructions_html
        self.captured_token: str | None = None
        self.code_verifier: str | None = None
        self.oauth_state: str | None = None


def login_via_browser(
    provider_name: str,
    provider: ProviderSettings,
    timeout_seconds: int = 120,
) -> str:
    """Inicia o servidor de callback local, abre o navegador padrão para login SSO

    e aguarda a captura do token.
    """
    port = _find_available_port()
    loopback_url = f"http://127.0.0.1:{port}"

    # Prepara instruções amigáveis dependendo do serviço
    service = provider.service
    if service == "gemini":
        instructions = (
            "Para autenticar no <strong>Google Gemini SSO</strong>, você pode utilizar o token "
            "gerado pelo seu Google Cloud SDK corporativo:<br>"
            "<code style='color:#818cf8;background:rgba(0,0,0,0.4);padding:4px 8px;border-radius:6px;display:inline-block;margin:6px 0;'>"
            "gcloud auth print-access-token</code><br>"
            "Copie a saída e cole no campo abaixo."
        )
    elif service == "anthropic":
        instructions = (
            "Para autenticar no <strong>Claude (Anthropic)</strong> com sua <strong>Conta Pro / Team</strong>, "
            "clique no botão laranja abaixo para autorizar no navegador via fluxo OAuth oficial.<br>"
            "Caso prefira utilizar credenciais manuais de um gateway corporativo, cole o token no campo abaixo."
        )
    else:
        instructions = f"Informe o token corporativo de sessão para o provedor <strong>{html.escape(provider_name)}</strong>."

    # Se houver auth_url customizada no config, podemos redirecionar ou incluir o link
    auth_url_custom = getattr(provider, "auth_url", None)
    if auth_url_custom:
        instructions += (
            f"<br><br><a href='{auth_url_custom}' target='_blank' style='color:#60a5fa;font-weight:600;text-decoration:underline;'>"
            "Clique aqui para abrir a página de login SSO do seu provedor</a>."
        )

    server = LoopbackAuthServer(
        ("127.0.0.1", port),
        provider_name=provider_name,
        instructions_html=instructions,
    )

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    target_url = auth_url_custom if (auth_url_custom and "callback" in auth_url_custom) else loopback_url

    console.print(
        f"\n[bold cyan]🌐 Abrindo o navegador para login SSO com:[/bold cyan] [bold yellow]{provider_name}[/bold yellow]"
    )
    console.print(f"[dim]URL de autenticação local: {loopback_url}[/dim]")
    console.print(f"[dim]Aguardando resposta do navegador (timeout: {timeout_seconds}s)...[/dim]")

    # Tenta abrir o navegador padrão
    opened = False
    try:
        opened = webbrowser.open(target_url, new=2)
    except Exception:
        opened = False

    if not opened:
        console.print(
            "[yellow]⚠️ Não foi possível abrir o navegador automaticamente (ambiente sem interface gráfica ou bloqueado).[/yellow]"
        )
        console.print(f"[bold]Acesse o link no seu navegador:[/bold] [underline]{loopback_url}[/underline]\n")

    # Loop de espera pelo callback
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if server.captured_token:
            break
        time.sleep(0.5)

    captured = server.captured_token
    server.shutdown()
    server.server_close()

    if not captured:
        # Fallback interativo no terminal caso o usuário não tenha concluído no browser
        console.print(
            "[yellow]Tempo limite do navegador esgotado ou nenhum token recebido pelo callback.[/yellow]"
        )
        if sys.stdin.isatty():
            token_input = console.input(
                f"[bold green]Cole o token de SSO para '{provider_name}' manualmente (ou pressione Enter para cancelar): [/bold green]"
            )
            captured = token_input.strip() if token_input else None

    if not captured:
        raise TimeoutError(
            f"Autenticação SSO cancelada ou tempo limite esgotado para o provedor '{provider_name}'."
        )

    # Salva no cache local seguro
    save_cached_token(provider_name, captured)
    console.print(
        f"[bold green]✓ Autenticação SSO concluída![/bold green] Token armazenado com segurança em: [dim]{get_sso_cache_file()}[/dim]\n"
    )
    return captured

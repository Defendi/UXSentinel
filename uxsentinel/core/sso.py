"""Gerenciador de autenticação SSO (Single Sign-On) com abertura de navegador."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import http.server
import json
import logging
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
logger = logging.getLogger("uxsentinel.sso")

DEFAULT_SSO_PORT_START = 8085
DEFAULT_SSO_PORT_END = 8095

# Constantes OAuth 2.0 PKCE para Claude.ai / Anthropic Platform (Contas Pro / Team)
TOKEN_EXPIRY_BUFFER_SECONDS = 300
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_AUTHORIZE_URL = "https://platform.claude.com/oauth/authorize"
CLAUDE_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLAUDE_OAUTH_MANUAL_REDIRECT_URL = "https://platform.claude.com/oauth/code/callback"
CLAUDE_OAUTH_SCOPES = "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"


def generate_pkce_pair() -> tuple[str, str]:
    """Gera code_verifier e code_challenge (S256 base64url) conforme RFC 7636 e padrão Claude Code."""
    verifier = secrets.token_urlsafe(32)
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


def exchange_claude_oauth_code(
    code_or_raw: str,
    code_verifier: str,
    redirect_uri: str,
    state: str | None = None,
) -> tuple[str | None, int | None, str | None]:
    """Troca authorization_code pelo access_token e refresh_token junto à Anthropic."""
    code = code_or_raw.strip()
    if "#" in code:
        parts = code.split("#", 1)
        code = parts[0].strip()
        if not state and len(parts) > 1:
            state = parts[1].strip()

    payload: dict = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": CLAUDE_OAUTH_CLIENT_ID,
        "code_verifier": code_verifier,
    }
    if state:
        payload["state"] = state

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
            access_token = data.get("access_token") or data.get("accessToken")
            refresh_token = data.get("refresh_token") or data.get("refreshToken")
            expires_in = data.get("expires_in")

            # Tenta gerar uma chave de API nativa via endpoint oficial de CLI se disponível
            if access_token:
                try:
                    key_req = urllib.request.Request(
                        "https://api.anthropic.com/api/oauth/claude_cli/create_api_key",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "User-Agent": "claude-cli/2.1.267",
                        },
                        data=b"",
                        method="POST",
                    )
                    with urllib.request.urlopen(key_req, timeout=15) as key_resp:
                        key_data = json.loads(key_resp.read().decode("utf-8"))
                        raw_key = key_data.get("raw_key")
                        if raw_key and str(raw_key).startswith("sk-ant-"):
                            return str(raw_key).strip(), expires_in, refresh_token
                except Exception:
                    pass

                return str(access_token).strip(), expires_in, refresh_token
    except Exception as exc:
        logger.warning("Falha na troca de código OAuth Anthropic: %s", exc)
        return None, None, None
    return None, None, None


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
            new_refresh = data.get("refreshToken") or data.get("refresh_token") or refresh_token
            expires_in = data.get("expires_in")
            if token:
                save_cached_token(
                    "claude_sso",
                    str(token).strip(),
                    expires_in=expires_in,
                    refresh_token=new_refresh,
                )
                return str(token).strip()
    except Exception:
        pass
    return None


def get_cached_token(provider_name: str) -> str | None:
    """Recupera o token SSO armazenado em cache para o provedor, se válido."""
    cache_file = get_sso_cache_file()
    item: dict | None = None
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            item = data.get(provider_name)
        except Exception:
            item = None

    if item:
        token = item.get("token")
        tok_str = str(token).strip() if token else ""
        expires_at = item.get("expires_at")
        ref_tok = item.get("refresh_token")

        now = time.time()
        is_claude_provider = "claude" in provider_name.lower() or tok_str.startswith("sk-ant-oat")

        if expires_at is not None:
            exp_time = float(expires_at)
            # Verifica se faltam menos de TOKEN_EXPIRY_BUFFER_SECONDS para expirar
            if now + TOKEN_EXPIRY_BUFFER_SECONDS >= exp_time:
                # Tenta obter refresh token local ou do Claude CLI
                cli_refresh: str | None = None
                if not ref_tok and is_claude_provider:
                    claude_creds = Path.home() / ".claude" / ".credentials.json"
                    if claude_creds.is_file():
                        try:
                            cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                            cli_refresh = cdata.get("claudeAiOauth", {}).get("refreshToken")
                        except Exception:
                            cli_refresh = None

                active_ref = ref_tok or cli_refresh
                if active_ref and is_claude_provider:
                    refreshed = refresh_claude_oauth_token(active_ref)
                    if refreshed:
                        return refreshed

                # Se ainda não expirou totalmente, usa o token atual como fallback de melhor esforço
                if now < exp_time and tok_str:
                    return tok_str
            else:
                # Ainda não atingiu a margem de expiração
                if tok_str:
                    return tok_str
        else:
            # Sem expires_at registrado
            if tok_str.startswith("sk-ant-oat"):
                updated_at = float(item.get("updated_at", 0))
                # Se tiver mais de 1h desde updated_at, tratar como expirado
                if now - updated_at > 3600.0:
                    if ref_tok and is_claude_provider:
                        refreshed = refresh_claude_oauth_token(ref_tok)
                        if refreshed:
                            return refreshed
                else:
                    if tok_str:
                        return tok_str
            elif tok_str:
                return tok_str

    # Sincronização inteligente com ~/.claude/.credentials.json se claude_sso
    if provider_name == "claude_sso":
        claude_creds = Path.home() / ".claude" / ".credentials.json"
        if claude_creds.is_file():
            try:
                cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                oauth = cdata.get("claudeAiOauth", {})
                cli_token = oauth.get("accessToken")
                cli_expires_at = oauth.get("expiresAt")
                cli_refresh = oauth.get("refreshToken")

                if cli_token:
                    cli_token_str = str(cli_token).strip()
                    if cli_expires_at:
                        val = float(cli_expires_at)
                        # Timestamps Unix em ms têm magnitude >= 1e11 (ex: ano 2026 é ~1.7e12), ou > 1e10
                        # Se for fornecido em ms ou valor muito maior que time.time(), converte para segundos
                        exp_sec = val / 1000.0 if val > 1e10 or val > time.time() * 10.0 else val
                        # Se ainda for válido (respeitando o buffer), sincroniza e retorna
                        if time.time() + TOKEN_EXPIRY_BUFFER_SECONDS < exp_sec:
                            rem_sec = max(0, int(exp_sec - time.time()))
                            save_cached_token(
                                "claude_sso",
                                cli_token_str,
                                expires_in=rem_sec,
                                refresh_token=cli_refresh,
                            )
                            return cli_token_str
                    elif not cli_refresh:
                        save_cached_token(
                            "claude_sso",
                            cli_token_str,
                            refresh_token=cli_refresh,
                        )
                        return cli_token_str

                # Se o token estiver vencido (ou sem token), mas houver refreshToken:
                if cli_refresh:
                    refreshed = refresh_claude_oauth_token(cli_refresh)
                    if refreshed:
                        return refreshed
            except Exception:
                pass

    return None


def save_cached_token(
    provider_name: str,
    token: str,
    expires_in: int | float | None = None,
    refresh_token: str | None = None,
) -> None:
    """Armazena o token de autenticação SSO no cache seguro local."""
    cache_file = get_sso_cache_file()
    data: dict = {}
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    prev_item = data.get(provider_name, {}) if isinstance(data, dict) else {}
    cleaned_token = token.strip()

    item: dict = {"token": cleaned_token, "updated_at": time.time()}

    if expires_in is not None:
        item["expires_at"] = time.time() + float(expires_in)
    elif cleaned_token.startswith("sk-ant-oat"):
        item["expires_at"] = time.time() + 3500.0

    if refresh_token:
        item["refresh_token"] = refresh_token.strip()
    elif prev_item.get("refresh_token"):
        item["refresh_token"] = prev_item["refresh_token"]

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

        # Rota para iniciar fluxo OAuth PKCE automático via localhost
        if parsed.path == "/oauth/claude/login":
            port = self.server_instance.server_address[1]
            auth_url = self.server_instance.auto_auth_url or (
                f"{CLAUDE_OAUTH_AUTHORIZE_URL}?"
                + urllib.parse.urlencode(
                    {
                        "code": "true",
                        "client_id": CLAUDE_OAUTH_CLIENT_ID,
                        "response_type": "code",
                        "redirect_uri": f"http://localhost:{port}/callback",
                        "scope": CLAUDE_OAUTH_SCOPES,
                        "code_challenge": self.server_instance.code_challenge or "",
                        "code_challenge_method": "S256",
                        "state": self.server_instance.oauth_state or "",
                    }
                )
            )
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return

        # Rota para iniciar fluxo OAuth PKCE manual via tela de cópia oficial da Anthropic
        if parsed.path == "/oauth/claude/manual":
            auth_url = self.server_instance.manual_auth_url or (
                f"{CLAUDE_OAUTH_AUTHORIZE_URL}?"
                + urllib.parse.urlencode(
                    {
                        "code": "true",
                        "client_id": CLAUDE_OAUTH_CLIENT_ID,
                        "response_type": "code",
                        "redirect_uri": CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
                        "scope": CLAUDE_OAUTH_SCOPES,
                        "code_challenge": self.server_instance.code_challenge or "",
                        "code_challenge_method": "S256",
                        "state": self.server_instance.oauth_state or "",
                    }
                )
            )
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return

        # Se o token vier via query param (/callback?token=... ou /callback?code=...)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            token = params.get("token", [None])[0]
            cb_state = params.get("state", [None])[0] or self.server_instance.oauth_state

            # Se recebemos um authorization_code do Claude.ai e temos o code_verifier
            if code and self.server_instance.code_verifier:
                port = self.server_instance.server_address[1]
                tok, exp, ref = exchange_claude_oauth_code(
                    code,
                    self.server_instance.code_verifier,
                    redirect_uri=f"http://localhost:{port}/callback",
                    state=cb_state,
                )
                if tok:
                    save_cached_token(
                        self.server_instance.provider_name,
                        tok,
                        expires_in=exp,
                        refresh_token=ref,
                    )
                    self.server_instance.captured_token = tok
                    self._send_success_response()
                    return
                # Se a troca falhou pelo endpoint mas temos o code, armazena code
                token = code
            elif code and not token:
                token = code

            if token:
                entered_tok = token.strip()
                self.server_instance.captured_token = entered_tok
                if entered_tok.startswith("sk-ant-oat"):
                    ref_from_cli: str | None = None
                    claude_creds = Path.home() / ".claude" / ".credentials.json"
                    if claude_creds.is_file():
                        try:
                            cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                            ref_from_cli = cdata.get("claudeAiOauth", {}).get("refreshToken")
                        except Exception:
                            ref_from_cli = None
                    save_cached_token(
                        self.server_instance.provider_name,
                        entered_tok,
                        expires_in=3500,
                        refresh_token=ref_from_cli,
                    )
                else:
                    save_cached_token(self.server_instance.provider_name, entered_tok)
                self._send_success_response()
                return

        # Página padrão de login
        self._send_login_page()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            raw_input: str | None = None
            content_type = self.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    payload = json.loads(post_data.decode("utf-8"))
                    raw_input = payload.get("token") or payload.get("code")
                except Exception:
                    pass
            else:
                form_fields = urllib.parse.parse_qs(post_data.decode("utf-8"))
                raw_input = form_fields.get("token", [None])[0]

            if raw_input:
                entered = raw_input.strip()
                # Se for código de autorização manual (# ou prefixo cai_)
                if ("#" in entered or entered.startswith("cai_")) and self.server_instance.code_verifier:
                    tok, exp, ref = exchange_claude_oauth_code(
                        entered,
                        self.server_instance.code_verifier,
                        redirect_uri=CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
                        state=self.server_instance.oauth_state,
                    )
                    if tok:
                        self.server_instance.captured_token = tok
                        save_cached_token(
                            self.server_instance.provider_name,
                            tok,
                            expires_in=exp,
                            refresh_token=ref,
                        )
                        self._send_success_response()
                        return

                if entered.startswith("sk-ant-oat"):
                    ref_from_cli: str | None = None
                    claude_creds = Path.home() / ".claude" / ".credentials.json"
                    if claude_creds.is_file():
                        try:
                            cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                            ref_from_cli = cdata.get("claudeAiOauth", {}).get("refreshToken")
                        except Exception:
                            ref_from_cli = None
                    self.server_instance.captured_token = entered
                    save_cached_token(
                        self.server_instance.provider_name,
                        entered,
                        expires_in=3500,
                        refresh_token=ref_from_cli,
                    )
                    self._send_success_response()
                    return

                self.server_instance.captured_token = entered
                save_cached_token(self.server_instance.provider_name, entered)
                self._send_success_response()
                return

        self.send_error(400, "Dados de autenticação inválidos.")

    def _send_login_page(self) -> None:
        provider_name = self.server_instance.provider_name
        instructions = self.server_instance.instructions_html

        extra_action_html = ""
        if "claude" in provider_name.lower():
            extra_action_html = """
            <div style="margin-bottom: 24px; text-align: center; display: flex; flex-direction: column; gap: 10px;">
              <a href="/oauth/claude/login" style="display: block; width: 100%; text-decoration: none; background: linear-gradient(135deg, #d97706 0%, #b45309 100%); color: #fff; border-radius: 10px; padding: 14px; font-weight: 700; font-size: 15px; box-shadow: 0 4px 14px rgba(217, 119, 6, 0.4);">
                ✨ Conectar com Conta Claude Pro / Team (Automático)
              </a>
              <a href="/oauth/claude/manual" target="_blank" style="display: block; width: 100%; text-decoration: none; background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.2); color: #cbd5e1; border-radius: 10px; padding: 10px; font-weight: 600; font-size: 13px;">
                📋 Abrir Autorização Manual (com Código de Cópia)
              </a>
              <p style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Após autorizar, você também pode colar o código ou token abaixo:</p>
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
        self.code_challenge: str | None = None
        self.oauth_state: str | None = None
        self.auto_auth_url: str = ""
        self.manual_auth_url: str = ""


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
            "autorize o acesso na plataforma oficial. Você pode utilizar o fluxo automático com redirecionamento "
            "local ou o fluxo com cópia manual do código.<br>"
            "Caso possua uma chave de API Anthropic (sk-ant-api...) ou token de gateway corporativo, "
            "basta colar no formulário abaixo."
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

    verifier, challenge = generate_pkce_pair()
    oauth_state = secrets.token_urlsafe(32)
    server.code_verifier = verifier
    server.code_challenge = challenge
    server.oauth_state = oauth_state

    is_claude = "claude" in provider_name.lower() or provider.service == "anthropic"
    if is_claude:
        auto_params = {
            "code": "true",
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": f"http://localhost:{port}/callback",
            "scope": CLAUDE_OAUTH_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": oauth_state,
        }
        server.auto_auth_url = f"{CLAUDE_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(auto_params)}"

        manual_params = {
            "code": "true",
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
            "scope": CLAUDE_OAUTH_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": oauth_state,
        }
        server.manual_auth_url = f"{CLAUDE_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(manual_params)}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    target_url = (
        server.auto_auth_url
        if is_claude
        else (auth_url_custom if (auth_url_custom and "callback" in auth_url_custom) else loopback_url)
    )

    console.print(
        f"\n[bold cyan]🌐 Abrindo o navegador para login SSO com:[/bold cyan] [bold yellow]{provider_name}[/bold yellow]"
    )
    if is_claude:
        console.print(
            f"[bold green]🔗 URL oficial Claude OAuth:[/bold green] [underline]{server.auto_auth_url}[/underline]"
        )
        console.print(f"[dim]Alternativa manual (cópia de código): {server.manual_auth_url}[/dim]")
    else:
        console.print(f"[dim]URL de autenticação local: {loopback_url}[/dim]")
    console.print(
        f"[dim]Aguardando autorização no navegador ou entrada manual no terminal (timeout: {timeout_seconds}s)...[/dim]"
    )

    # Thread em segundo plano para ler código ou token digitado no terminal sem travar
    def _listen_terminal_input() -> None:
        try:
            if sys.stdin.isatty():
                line = sys.stdin.readline()
                if line and line.strip():
                    entered = line.strip()
                    if ("#" in entered or entered.startswith("cai_")) and server.code_verifier:
                        tok, exp, ref = exchange_claude_oauth_code(
                            entered,
                            server.code_verifier,
                            redirect_uri=CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
                            state=server.oauth_state,
                        )
                        if tok:
                            server.captured_token = tok
                            save_cached_token(provider_name, tok, expires_in=exp, refresh_token=ref)
                            return
                    if entered.startswith("sk-ant-oat"):
                        ref_from_cli: str | None = None
                        claude_creds = Path.home() / ".claude" / ".credentials.json"
                        if claude_creds.is_file():
                            try:
                                cdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                                ref_from_cli = cdata.get("claudeAiOauth", {}).get("refreshToken")
                            except Exception:
                                ref_from_cli = None
                        server.captured_token = entered
                        save_cached_token(
                            provider_name,
                            entered,
                            expires_in=3500,
                            refresh_token=ref_from_cli,
                        )
                        return
                    server.captured_token = entered
                    save_cached_token(provider_name, entered)
        except Exception:
            pass

    terminal_thread = threading.Thread(target=_listen_terminal_input, daemon=True)
    terminal_thread.start()

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
        console.print(f"[bold]Acesse o link no seu navegador:[/bold] [underline]{target_url}[/underline]\n")

    # Loop de espera pelo callback ou entrada manual
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if server.captured_token:
            break
        time.sleep(0.5)

    captured = server.captured_token
    server.shutdown()
    server.server_close()

    if not captured:
        # Fallback interativo caso o usuário ainda queira informar
        console.print("[yellow]Tempo limite esgotado ou nenhum token recebido pelo callback.[/yellow]")
        if sys.stdin.isatty():
            token_input = console.input(
                f"[bold green]Cole o token ou código de SSO para '{provider_name}' manualmente (ou pressione Enter para cancelar): [/bold green]"
            )
            if token_input and token_input.strip():
                entered = token_input.strip()
                if ("#" in entered or entered.startswith("cai_")) and server.code_verifier:
                    tok, exp, ref = exchange_claude_oauth_code(
                        entered,
                        server.code_verifier,
                        redirect_uri=CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
                        state=server.oauth_state,
                    )
                    if tok:
                        captured = tok
                        save_cached_token(provider_name, tok, expires_in=exp, refresh_token=ref)
                    else:
                        captured = entered
                else:
                    captured = entered

    if not captured:
        raise TimeoutError(
            f"Autenticação SSO cancelada ou tempo limite esgotado para o provedor '{provider_name}'."
        )

    # Salva no cache local seguro
    save_cached_token(provider_name, captured)
    console.print(
        f"[bold green]✓ Autenticação SSO concluída![/bold green] Sessão armazenada com segurança em: [dim]{get_sso_cache_file()}[/dim]\n"
    )
    return captured

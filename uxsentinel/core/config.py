import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Carrega primeiro o .env do diretório atual (projeto alvo) e depois o global
load_dotenv(dotenv_path=Path.cwd() / ".env")
load_dotenv()

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def _interpolate_env_vars(raw_text: str) -> str:
    """Substitui variáveis de ambiente no padrão ${VAR} ou ${VAR:-default}."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return ENV_VAR_PATTERN.sub(_replacer, raw_text)


class BrowserSettings(BaseModel):
    headless: bool = False
    slow_mo_ms: int = 350
    viewport_width: int = 1440
    viewport_height: int = 900
    highlight_clicks: bool = True
    timeout_ms: int = 15000


class ReportingSettings(BaseModel):
    output_dir: str = "scenarios/report"
    generate_html: bool = True
    generate_json: bool = True
    save_screenshots: bool = True


class ProviderSettings(BaseModel):
    type: str  # 'api', 'local', 'sso'
    service: str  # 'anthropic', 'openai', 'gemini', 'ollama', 'openai_compatible'
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.1
    timeout: int = 45
    headers: dict[str, str] = Field(default_factory=dict)
    verify_ssl: bool = True
    auth_url: str | None = None
    token_url: str | None = None


class GlobalConfig(BaseModel):
    active_provider: str = "anthropic_cloud"
    fallback_provider: str | None = "ollama_local"
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)

    def get_active_provider(self) -> ProviderSettings:
        if self.active_provider not in self.providers:
            if self.providers:
                return next(iter(self.providers.values()))
            raise ValueError(f"Provedor ativo '{self.active_provider}' não encontrado na configuração.")
        return self.providers[self.active_provider]

    def get_fallback_provider(self) -> ProviderSettings | None:
        if self.fallback_provider and self.fallback_provider in self.providers:
            return self.providers[self.fallback_provider]
        return None


DEFAULT_CONFIG_TEMPLATE = """# ==============================================================================
# UXSentinel - Configuração do Usuário
# Localização: ~/.config/uxsentinel/config.yaml
# Não requer permissões de administrador (sudo)
# ==============================================================================

active_provider: "anthropic_cloud"
fallback_provider: "ollama_local"

browser:
  headless: false              # 'false' para acompanhar o navegador abrindo na tela
  slow_mo_ms: 350              # Delay em milissegundos entre passos (ritmo humano)
  viewport:
    width: 1440
    height: 900
  highlight_clicks: true       # Halo visual no elemento clicado ou focado
  timeout_ms: 15000

reporting:
  output_dir: "scenarios/report"
  generate_html: true
  generate_json: true
  save_screenshots: true

providers:
  anthropic_cloud:
    type: "api"
    service: "anthropic"
    model: "claude-3-5-sonnet-latest"
    api_key: "${ANTHROPIC_API_KEY}"
    max_tokens: 2000
    temperature: 0.1

  openai_cloud:
    type: "api"
    service: "openai"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
    max_tokens: 2000
    temperature: 0.1

  gemini_cloud:
    type: "api"
    service: "gemini"
    model: "gemini-1.5-pro"
    api_key: "${GEMINI_API_KEY}"
    max_tokens: 2000
    temperature: 0.1

  ollama_local:
    type: "local"
    service: "ollama"
    base_url: "http://localhost:11434"
    model: "qwen2-vl:7b"
    temperature: 0.1
    timeout: 60

  corporate_gateway:
    type: "sso"
    service: "openai_compatible"
    base_url: "https://ai-gateway.suaempresa.com.br/v1"
    model: "corporate-vision-model"
    api_key: "${SSO_CORPORATE_TOKEN}"
    headers:
      X-Enterprise-Client-Id: "${ENTERPRISE_CLIENT_ID:-uxsentinel-qa}"
    timeout: 45
    verify_ssl: true
"""


def get_user_config_dir() -> Path:
    """Retorna o diretório de configuração do usuário no padrão XDG (~/.config/uxsentinel).

    Totalmente acessível e editável pelo usuário sem necessidade de permissões de sudo.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base_dir / "uxsentinel"


def ensure_user_config() -> Path:
    """Garante a existência do arquivo de configuração do usuário (~/.config/uxsentinel/config.yaml).

    Se não existir, cria o diretório e o arquivo automaticamente a partir do template padrão
    ou do config.example.yaml incluído no pacote.
    """
    config_dir = get_user_config_dir()
    config_file = config_dir / "config.yaml"

    if not config_file.is_file():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            # Tenta copiar o modelo empacotado se disponível
            pkg_config = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
            if pkg_config.is_file():
                config_file.write_text(pkg_config.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                config_file.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        except OSError:
            # Caso não seja possível gravar (ex: ambiente efêmero ou somente-leitura)
            pass

    return config_file


def load_config(config_path: str | None = None) -> GlobalConfig:
    """Carrega o arquivo de configuração YAML com prioridade para:
    1. Parâmetro explícito passado (--config)
    2. Variável de ambiente UXSENTINEL_CONFIG_PATH
    3. Projeto cliente corrente (onde o comando foi invocado): uxsentinel.yaml, .uxsentinel.yaml, config/config.yaml
    4. Diretório de configuração do usuário sem sudo: ~/.config/uxsentinel/config.yaml
    5. Fallback padrão seguro em memória
    """
    cwd = Path.cwd()
    user_cfg_file = ensure_user_config()
    pkg_dir = Path(__file__).resolve().parent.parent.parent

    candidate_paths = [
        config_path,
        os.environ.get("UXSENTINEL_CONFIG_PATH"),
        cwd / "uxsentinel.yaml",
        cwd / ".uxsentinel.yaml",
        cwd / "config" / "config.yaml",
        cwd / "config" / "config.example.yaml",
        user_cfg_file,
        pkg_dir / "config" / "config.yaml",
        pkg_dir / "config" / "config.example.yaml",
    ]

    selected_file: Path | None = None
    for cp in candidate_paths:
        if cp:
            p = Path(cp)
            if p.is_file():
                selected_file = p
                break

    if not selected_file:
        return GlobalConfig()

    content = selected_file.read_text(encoding="utf-8")
    interpolated_content = _interpolate_env_vars(content)
    raw_dict = yaml.safe_load(interpolated_content) or {}

    browser_dict = raw_dict.get("browser", {})
    viewport = browser_dict.get("viewport", {})
    browser_settings = BrowserSettings(
        headless=browser_dict.get("headless", False),
        slow_mo_ms=browser_dict.get("slow_mo_ms", 350),
        viewport_width=viewport.get("width", 1440),
        viewport_height=viewport.get("height", 900),
        highlight_clicks=browser_dict.get("highlight_clicks", True),
        timeout_ms=browser_dict.get("timeout_ms", 15000),
    )

    reporting_dict = raw_dict.get("reporting", {})
    reporting_settings = ReportingSettings(
        output_dir=reporting_dict.get("output_dir", "scenarios/report"),
        generate_html=reporting_dict.get("generate_html", True),
        generate_json=reporting_dict.get("generate_json", True),
        save_screenshots=reporting_dict.get("save_screenshots", True),
    )

    providers_dict: dict[str, ProviderSettings] = {}
    for p_name, p_data in raw_dict.get("providers", {}).items():
        providers_dict[p_name] = ProviderSettings(
            type=p_data.get("type", "api"),
            service=p_data.get("service", "anthropic"),
            model=p_data.get("model", ""),
            api_key=p_data.get("api_key"),
            base_url=p_data.get("base_url"),
            max_tokens=p_data.get("max_tokens", 2000),
            temperature=p_data.get("temperature", 0.1),
            timeout=p_data.get("timeout", 45),
            headers=p_data.get("headers") or {},
            verify_ssl=p_data.get("verify_ssl", True),
            auth_url=p_data.get("auth_url"),
            token_url=p_data.get("token_url"),
        )

    active_p = os.environ.get(
        "UXSENTINEL_ACTIVE_PROVIDER", raw_dict.get("active_provider", "anthropic_cloud")
    )

    return GlobalConfig(
        active_provider=active_p,
        fallback_provider=raw_dict.get("fallback_provider", "ollama_local"),
        browser=browser_settings,
        reporting=reporting_settings,
        providers=providers_dict,
    )

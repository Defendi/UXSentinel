import contextlib
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from uxsentinel.core.models import (
    CANONICAL_VIEWPORTS,
    DEFAULT_FALLBACK_VIEWPORT,
    ViewportConfig,
    parse_viewport_spec,
    parse_viewports,
    resolve_viewports,
)

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
    devtools: bool = False
    capture_console: bool = True
    slow_mo_ms: int = 350
    viewport_width: int = 1440
    viewport_height: int = 900
    viewports: list[ViewportConfig] | list[str] | None = None
    highlight_clicks: bool = True
    timeout_ms: int = 15000
    self_healing: bool = True
    record_video: bool = False
    record_video_dir: str | None = None
    record_video_size: dict[str, int] | None = None
    enable_axe: bool = True
    axe_tags: list[str] = Field(
        default_factory=lambda: [
            "wcag2a",
            "wcag2aa",
            "wcag21a",
            "wcag21aa",
            "wcag22aa",
        ]
    )


def resolve_devtools_mode(
    cli_devtools: bool | None = None,
    scenario_devtools: bool | None = None,
    config_devtools: bool | None = None,
) -> bool:
    """Resolve se a aba DevTools/Console do Chromium deve ser aberta:
    1. CLI flag (--devtools / --console / --inspect vs --no-devtools)
    2. Cenário YAML (campo 'devtools')
    3. Config global (BrowserSettings.devtools)
    4. Fallback padrão: False
    """
    if cli_devtools is not None:
        return cli_devtools
    if scenario_devtools is not None:
        return scenario_devtools
    if config_devtools is not None:
        return config_devtools
    return False


def resolve_video_mode(
    cli_video: bool | None = None,
    scenario_video: bool | None = None,
    config_video: bool | None = None,
) -> bool:
    """Resolve se a gravação de vídeo deve ser ativada seguindo a hierarquia estrita:
    1. CLI flag (--record-video / --video vs --no-video)
    2. Cenário YAML (campo 'video' definido no cenário)
    3. Config global (BrowserSettings.record_video)
    4. Fallback padrão: False
    """
    if cli_video is not None:
        return cli_video
    if scenario_video is not None:
        return scenario_video
    if config_video is not None:
        return config_video
    return False


def resolve_display_mode(
    cli_headless: bool | None = None,
    scenario_headless: bool | None = None,
    config_headless: bool | None = None,
) -> bool:
    """Resolve o modo de execução do navegador (headless vs headed) seguindo a hierarquia estrita:
    1. CLI flag (--headless/--no-gui/--silent vs --headed/--gui/--visible)
    2. Cenário YAML (campo 'headless' definido no cenário)
    3. Config global (BrowserSettings.headless)
    4. Fallback padrão: False (visível com ritmo humano)
    """
    if cli_headless is not None:
        return cli_headless
    if scenario_headless is not None:
        return scenario_headless
    if config_headless is not None:
        return config_headless
    return False


def resolve_axe_mode(
    cli_axe: bool | None = None,
    scenario_axe: bool | None = None,
    config_axe: bool | None = None,
) -> bool:
    """Resolve se a auditoria de acessibilidade Axe-Core deve ser executada:
    1. CLI flag (--axe vs --no-axe)
    2. Cenário YAML (campo 'axe')
    3. Config global (BrowserSettings.enable_axe)
    4. Fallback padrão: True
    """
    if cli_axe is not None:
        return cli_axe
    if scenario_axe is not None:
        return scenario_axe
    if config_axe is not None:
        return config_axe
    return True


def resolve_markdown_mode(
    cli_markdown: bool | None = None,
    scenario_markdown: bool | None = None,
    config_markdown: bool | None = None,
) -> bool:
    """Resolve se o relatório Markdown formatado para MarkText deve ser gerado:
    1. CLI flag (--markdown / --md vs --no-markdown)
    2. Cenário YAML (campo 'markdown')
    3. Config global (ReportingSettings.generate_markdown)
    4. Fallback padrão: False
    """
    if cli_markdown is not None:
        return cli_markdown
    if scenario_markdown is not None:
        return scenario_markdown
    if config_markdown is not None:
        return config_markdown
    return False


class ReportingSettings(BaseModel):
    output_dir: str = "scenarios/report"
    generate_html: bool = True
    generate_json: bool = True
    generate_markdown: bool = False
    save_screenshots: bool = True
    generate_fix_prompt: bool = False


DEFAULT_I18N_ALLOWLIST: list[str] = [
    "Status",
    "Dashboard",
    "Lead",
    "Login",
    "Logout",
    "Feedback",
    "Insight",
    "Online",
    "ID",
    "App",
    "Upload",
    "Download",
    "E-mail",
    "Email",
    "API",
    "Software",
    "Link",
    "Setup",
    "Bug",
    "Layout",
    "Design",
    "Banner",
    "Checkout",
    "Pipeline",
    "Card",
    "Tag",
    "Score",
    "Sprint",
    "Kanban",
    "Briefing",
    "Deploy",
    "Release",
    "Case",
]


class BaselineSettings(BaseModel):
    baseline_dir: str = "scenarios/baselines"
    diff_threshold: float = 0.1
    update_baseline: bool = False


def resolve_baseline_mode(
    cli_update_baseline: bool | None = None,
    scenario_update_baseline: bool | None = None,
    config_update_baseline: bool | None = None,
) -> bool:
    """Resolve se a atualização de baseline deve ser executada:
    1. CLI flag (--update-baseline)
    2. Cenário YAML (campo 'update_baseline')
    3. Config global (BaselineSettings.update_baseline)
    4. Fallback padrão: False
    """
    if cli_update_baseline is not None:
        return cli_update_baseline
    if scenario_update_baseline is not None:
        return scenario_update_baseline
    if config_update_baseline is not None:
        return config_update_baseline
    return False


class VisionSettings(BaseModel):
    use_mixture_of_evaluators: bool = True
    enable_devils_advocate: bool = True
    enable_dom_validation: bool = True
    enable_som: bool = False
    i18n_allowlist: list[str] = Field(default_factory=lambda: list(DEFAULT_I18N_ALLOWLIST))


class JiraSettings(BaseModel):
    enabled: bool = False
    url: str = Field(default="", description="URL base do Jira (ex: https://empresa.atlassian.net)")
    email: str | None = Field(default="", description="Email do usuário Atlassian")
    api_token: str | None = Field(default="", description="Token de API do Jira")
    project_key: str | None = Field(default="", description="Chave do projeto (ex: UX, QA)")
    issue_type: str = Field(default="Bug", description="Tipo da issue")
    labels: list[str] = Field(default_factory=lambda: ["uxsentinel", "qa-audit"])


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


BUILTIN_PROVIDERS: dict[str, ProviderSettings] = {
    "gemini_sso": ProviderSettings(
        type="sso",
        service="gemini",
        model="gemini-1.5-pro",
        api_key="${GEMINI_SSO_TOKEN}",
        headers={"Authorization": "Bearer ${GEMINI_SSO_TOKEN}"},
        max_tokens=2000,
        temperature=0.1,
    ),
    "claude_sso": ProviderSettings(
        type="sso",
        service="anthropic",
        model="claude-haiku-4-5",
        api_key="${CLAUDE_SSO_TOKEN}",
        headers={
            "Authorization": "Bearer ${CLAUDE_SSO_TOKEN}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-cli/2.1.267",
        },
        max_tokens=2000,
        temperature=0.1,
    ),
    "gemini_cloud": ProviderSettings(
        type="api",
        service="gemini",
        model="gemini-1.5-pro",
        api_key="${GEMINI_API_KEY}",
        max_tokens=2000,
        temperature=0.1,
    ),
    "anthropic_cloud": ProviderSettings(
        type="api",
        service="anthropic",
        model="claude-3-5-sonnet-latest",
        api_key="${ANTHROPIC_API_KEY}",
        max_tokens=2000,
        temperature=0.1,
    ),
    "openai_cloud": ProviderSettings(
        type="api",
        service="openai",
        model="gpt-4o",
        api_key="${OPENAI_API_KEY}",
        max_tokens=2000,
        temperature=0.1,
    ),
    "ollama_local": ProviderSettings(
        type="local",
        service="ollama",
        base_url="http://localhost:11434",
        model="qwen2-vl:7b",
        temperature=0.1,
        timeout=60,
    ),
}


class GlobalConfig(BaseModel):
    active_provider: str = "anthropic_cloud"
    fallback_provider: str | None = "ollama_local"
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    baseline: BaselineSettings = Field(default_factory=BaselineSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)

    def get_active_provider(self) -> ProviderSettings:
        if self.active_provider in self.providers:
            return self.providers[self.active_provider]
        if self.active_provider in BUILTIN_PROVIDERS:
            return BUILTIN_PROVIDERS[self.active_provider]

        avail = ", ".join(sorted(set(self.providers.keys()).union(BUILTIN_PROVIDERS.keys())))
        raise ValueError(
            f"Provedor ativo '{self.active_provider}' não encontrado na configuração. "
            f"Opções disponíveis: {avail}"
        )

    def get_fallback_provider(self) -> ProviderSettings | None:
        if not self.fallback_provider:
            return None
        if self.fallback_provider in self.providers:
            return self.providers[self.fallback_provider]
        if self.fallback_provider in BUILTIN_PROVIDERS:
            return BUILTIN_PROVIDERS[self.fallback_provider]
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
  # viewports:                 # Lista de viewports padrão para auditoria responsiva
  #   - desktop                # 1440x900
  #   - tablet                 # 768x1024
  #   - mobile                 # 375x812
  highlight_clicks: true       # Halo visual no elemento clicado ou focado
  timeout_ms: 15000
  record_video: false          # Gravação nativa em vídeo da sessão de teste

reporting:
  output_dir: "scenarios/report"
  generate_html: true
  generate_json: true
  save_screenshots: true
  generate_fix_prompt: false

# ==============================================================================
# Integração Atlassian Jira (Abertura Automática de Cards)
# ==============================================================================
jira:
  enabled: false
  url: "https://sua-empresa.atlassian.net"
  email: "${JIRA_EMAIL}"
  api_token: "${JIRA_API_TOKEN}"
  project_key: "${JIRA_PROJECT_KEY}"
  issue_type: "Bug"
  labels:
    - "uxsentinel"
    - "qa-audit"


providers:
  gemini_sso:
    type: "sso"
    service: "gemini"
    model: "gemini-1.5-pro"
    api_key: "${GEMINI_SSO_TOKEN}"
    headers:
      Authorization: "Bearer ${GEMINI_SSO_TOKEN}"
    max_tokens: 2000
    temperature: 0.1

  claude_sso:
    type: "sso"
    service: "anthropic"
    model: "claude-haiku-4-5"
    api_key: "${CLAUDE_SSO_TOKEN}"
    headers:
      Authorization: "Bearer ${CLAUDE_SSO_TOKEN}"
      anthropic-beta: "oauth-2025-04-20"
      User-Agent: "claude-cli/2.1.267"
    max_tokens: 2000
    temperature: 0.1

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


def get_user_config_path() -> Path:
    """Retorna o caminho do arquivo de configuração do usuário (~/.config/uxsentinel/config.yaml)."""
    return get_user_config_dir() / "config.yaml"


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
    raw_viewports = browser_dict.get("viewports")
    parsed_viewports = parse_viewports(raw_viewports) if raw_viewports else None
    video_size_dict = browser_dict.get("record_video_size") or browser_dict.get("video_size")
    browser_settings = BrowserSettings(
        headless=browser_dict.get("headless", False),
        slow_mo_ms=browser_dict.get("slow_mo_ms", 350),
        viewport_width=viewport.get("width", 1440),
        viewport_height=viewport.get("height", 900),
        viewports=parsed_viewports,
        highlight_clicks=browser_dict.get("highlight_clicks", True),
        timeout_ms=browser_dict.get("timeout_ms", 15000),
        record_video=browser_dict.get("record_video", False),
        record_video_dir=browser_dict.get("record_video_dir"),
        record_video_size=video_size_dict,
        enable_axe=browser_dict.get("enable_axe", True),
        axe_tags=browser_dict.get("axe_tags")
        or [
            "wcag2a",
            "wcag2aa",
            "wcag21a",
            "wcag21aa",
            "wcag22aa",
        ],
    )

    reporting_dict = raw_dict.get("reporting", {})
    reporting_settings = ReportingSettings(
        output_dir=reporting_dict.get("output_dir", "scenarios/report"),
        generate_html=reporting_dict.get("generate_html", True),
        generate_json=reporting_dict.get("generate_json", True),
        save_screenshots=reporting_dict.get("save_screenshots", True),
        generate_fix_prompt=reporting_dict.get("generate_fix_prompt", False),
    )

    jira_dict = raw_dict.get("jira") or {}
    jira_settings = JiraSettings(
        enabled=bool(jira_dict.get("enabled", False)),
        url=jira_dict.get("url") or "",
        email=jira_dict.get("email") or "",
        api_token=jira_dict.get("api_token") or "",
        project_key=jira_dict.get("project_key") or "",
        issue_type=jira_dict.get("issue_type") or "Bug",
        labels=jira_dict.get("labels") or ["uxsentinel", "qa-audit"],
    )

    vision_dict = raw_dict.get("vision", {})
    raw_allowlist = vision_dict.get("i18n_allowlist")
    i18n_allowlist = raw_allowlist if raw_allowlist is not None else list(DEFAULT_I18N_ALLOWLIST)
    vision_settings = VisionSettings(
        use_mixture_of_evaluators=vision_dict.get("use_mixture_of_evaluators", True),
        enable_devils_advocate=vision_dict.get("enable_devils_advocate", True),
        enable_dom_validation=vision_dict.get("enable_dom_validation", True),
        enable_som=vision_dict.get("enable_som", False),
        i18n_allowlist=i18n_allowlist,
    )

    # Inicializa com provedores padrão embutidos e mescla com os definidos pelo usuário
    providers_dict: dict[str, ProviderSettings] = {k: v.model_copy() for k, v in BUILTIN_PROVIDERS.items()}
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
        vision=vision_settings,
        jira=jira_settings,
        providers=providers_dict,
    )


def save_jira_config(
    url: str | None = None,
    email: str | None = None,
    api_token: str | None = None,
    project_key: str | None = None,
    enabled: bool | None = None,
) -> Path:
    """Salva ou atualiza a seção 'jira' no arquivo de configuração do usuário (~/.config/uxsentinel/config.yaml)."""
    cfg_file = ensure_user_config()
    content = cfg_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}

    if "jira" not in data or not isinstance(data["jira"], dict):
        data["jira"] = {}

    if url is not None:
        data["jira"]["url"] = url.strip()
    if email is not None:
        data["jira"]["email"] = email.strip()
    if api_token is not None:
        data["jira"]["api_token"] = api_token.strip()
    if project_key is not None:
        data["jira"]["project_key"] = project_key.strip().upper()
    if enabled is not None:
        data["jira"]["enabled"] = enabled

    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)
    return cfg_file


__all__ = [
    "BUILTIN_PROVIDERS",
    "CANONICAL_VIEWPORTS",
    "DEFAULT_CONFIG_TEMPLATE",
    "DEFAULT_FALLBACK_VIEWPORT",
    "DEFAULT_I18N_ALLOWLIST",
    "BrowserSettings",
    "GlobalConfig",
    "JiraSettings",
    "ProviderSettings",
    "ReportingSettings",
    "ViewportConfig",
    "VisionSettings",
    "ensure_user_config",
    "get_user_config_dir",
    "get_user_config_path",
    "load_config",
    "parse_viewport_spec",
    "parse_viewports",
    "resolve_axe_mode",
    "resolve_devtools_mode",
    "resolve_display_mode",
    "resolve_markdown_mode",
    "resolve_video_mode",
    "resolve_viewports",
    "save_jira_config",
]

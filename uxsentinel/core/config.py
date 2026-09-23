import contextlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    inspect: bool = False
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
    enable_css_audit: bool = True
    fail_fast: bool = True
    axe_tags: list[str] = Field(
        default_factory=lambda: [
            "wcag2a",
            "wcag2aa",
            "wcag21a",
            "wcag21aa",
            "wcag22aa",
        ]
    )


def resolve_fail_fast_mode(
    cli_fail_fast: bool | None = None,
    scenario_fail_fast: bool | None = None,
    config_fail_fast: bool | None = None,
) -> bool:
    """Resolve se a execução deve ser abortada imediatamente na primeira falha grave:
    1. CLI flag (--fail-fast vs --no-fail-fast)
    2. Cenário YAML (campo 'fail_fast' ou 'abort_on_error')
    3. Config global (BrowserSettings.fail_fast)
    4. Fallback padrão: True
    """
    if cli_fail_fast is not None:
        return cli_fail_fast
    if scenario_fail_fast is not None:
        return scenario_fail_fast
    if config_fail_fast is not None:
        return config_fail_fast
    return True


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


def resolve_css_mode(
    cli_css: bool | None = None,
    scenario_css: bool | None = None,
    config_css: bool | None = None,
) -> bool:
    """Resolve se a auditoria híbrida de CSS deve ser executada:
    1. CLI flag (--css vs --no-css)
    2. Cenário YAML (campo 'css')
    3. Config global (BrowserSettings.enable_css_audit)
    4. Fallback padrão: True
    """
    if cli_css is not None:
        return cli_css
    if scenario_css is not None:
        return scenario_css
    if config_css is not None:
        return config_css
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


def resolve_archive_mode(
    cli_archive: bool | None = None,
    scenario_archive: bool | None = None,
    config_archive: bool | None = None,
) -> bool:
    """Resolve se os relatórios da análise anterior devem ser compactados em ZIP:
    1. CLI flag (--archive vs --no-archive)
    2. Cenário YAML (campo 'archive')
    3. Config global (ReportingSettings.archive_previous_reports)
    4. Fallback padrão: True
    """
    if cli_archive is not None:
        return cli_archive
    if scenario_archive is not None:
        return scenario_archive
    if config_archive is not None:
        return config_archive
    return True


def resolve_archive_dir(
    cli_archive_dir: str | None = None,
    scenario_archive_dir: str | None = None,
    config_archive_dir: str | None = None,
) -> str | None:
    """Resolve o diretório onde os arquivos ZIP arquivados serão salvos:
    1. CLI flag (--archive-dir)
    2. Cenário YAML (campo 'archive_dir')
    3. Config global (ReportingSettings.archive_dir)
    4. Fallback padrão: None (usa output_dir / 'archive')
    """
    if cli_archive_dir is not None:
        return cli_archive_dir
    if scenario_archive_dir is not None:
        return scenario_archive_dir
    if config_archive_dir is not None:
        return config_archive_dir
    return None


class ReportingSettings(BaseModel):
    output_dir: str = "scenarios/report"
    generate_html: bool = True
    generate_json: bool = True
    generate_markdown: bool = False
    save_screenshots: bool = True
    generate_fix_prompt: bool = False
    archive_previous_reports: bool = True
    archive_dir: str | None = None


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


class ProjectScenarioItem(BaseModel):
    """Representa um cenário de teste associado a um projeto registrado no catálogo."""

    id: str
    path: str
    name: str
    last_run: str | None = None


class ProjectCatalogEntry(BaseModel):
    """Representa um projeto e seu inventário acumulado de cenários de teste."""

    name: str
    root_path: str
    scenarios: dict[str, ProjectScenarioItem] = Field(default_factory=dict)
    last_run: str | None = None


class GlobalConfig(BaseModel):
    active_provider: str = "anthropic_cloud"
    fallback_provider: str | None = "ollama_local"
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    baseline: BaselineSettings = Field(default_factory=BaselineSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    projects: dict[str, ProjectCatalogEntry] = Field(default_factory=dict)
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
            # O arquivo pode receber tokens do Jira e chaves de API em texto plano
            with contextlib.suppress(Exception):
                config_file.chmod(0o600)
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
        enable_css_audit=browser_dict.get("enable_css_audit", browser_dict.get("enable_css", True)),
        fail_fast=browser_dict.get("fail_fast", True),
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

    projects_dict: dict[str, ProjectCatalogEntry] = {}
    for p_id, p_data in raw_dict.get("projects", {}).items():
        if isinstance(p_data, dict):
            scenarios_dict: dict[str, ProjectScenarioItem] = {}
            for s_id, s_data in p_data.get("scenarios", {}).items():
                if isinstance(s_data, dict):
                    scenarios_dict[s_id] = ProjectScenarioItem(
                        id=str(s_data.get("id", s_id)),
                        path=str(s_data.get("path", "")),
                        name=str(s_data.get("name", s_id)),
                        last_run=s_data.get("last_run"),
                    )
            projects_dict[p_id] = ProjectCatalogEntry(
                name=str(p_data.get("name", p_id)),
                root_path=str(p_data.get("root_path", "")),
                scenarios=scenarios_dict,
                last_run=p_data.get("last_run"),
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
        projects=projects_dict,
        providers=providers_dict,
    )


def save_jira_config(
    url: str | None = None,
    email: str | None = None,
    api_token: str | None = None,
    project_key: str | None = None,
    enabled: bool | None = None,
    config_path: Path | None = None,
) -> Path:
    """Salva ou atualiza a seção 'jira' no arquivo de configuração do usuário (~/.config/uxsentinel/config.yaml)."""
    cfg_file = Path(config_path) if config_path is not None else ensure_user_config()
    content = cfg_file.read_text(encoding="utf-8") if cfg_file.is_file() else ""
    data = yaml.safe_load(content) or {} if content else {}

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

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)
    return cfg_file


def save_active_provider(
    provider_name: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """Salva ou atualiza o provedor de IA ativo e suas credenciais/endereço em ~/.config/uxsentinel/config.yaml."""
    cfg_file = Path(config_path) if config_path is not None else ensure_user_config()
    content = cfg_file.read_text(encoding="utf-8") if cfg_file.is_file() else ""
    data = yaml.safe_load(content) or {} if content else {}

    p_clean = provider_name.strip()
    data["active_provider"] = p_clean

    if "providers" not in data or not isinstance(data["providers"], dict):
        data["providers"] = {}

    if p_clean not in data["providers"] or not isinstance(data["providers"][p_clean], dict):
        if p_clean in BUILTIN_PROVIDERS:
            b_prov = BUILTIN_PROVIDERS[p_clean]
            data["providers"][p_clean] = {
                "type": b_prov.type,
                "service": b_prov.service,
                "model": b_prov.model,
                "temperature": b_prov.temperature,
                "max_tokens": b_prov.max_tokens,
            }
            if b_prov.base_url:
                data["providers"][p_clean]["base_url"] = b_prov.base_url
            if b_prov.headers:
                data["providers"][p_clean]["headers"] = dict(b_prov.headers)
        else:
            data["providers"][p_clean] = {
                "type": "api",
                "service": "anthropic",
                "model": "",
            }

    prov_dict = data["providers"][p_clean]
    if api_key is not None and api_key.strip():
        prov_dict["api_key"] = api_key.strip()
    if base_url is not None and base_url.strip():
        prov_dict["base_url"] = base_url.strip()
    if model is not None and model.strip():
        prov_dict["model"] = model.strip()

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)
    return cfg_file


def save_default_viewports(
    viewports: list[str] | list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    clear_viewports: bool = False,
    config_path: Path | None = None,
) -> Path:
    """Salva a resolução padrão de viewport e/ou lista de viewports em ~/.config/uxsentinel/config.yaml."""
    cfg_file = Path(config_path) if config_path is not None else ensure_user_config()
    content = cfg_file.read_text(encoding="utf-8") if cfg_file.is_file() else ""
    data = yaml.safe_load(content) or {} if content else {}

    if "browser" not in data or not isinstance(data["browser"], dict):
        data["browser"] = {}

    if width is not None or height is not None:
        if "viewport" not in data["browser"] or not isinstance(data["browser"]["viewport"], dict):
            data["browser"]["viewport"] = {}
        if width is not None:
            data["browser"]["viewport"]["width"] = int(width)
        if height is not None:
            data["browser"]["viewport"]["height"] = int(height)

    if clear_viewports:
        data["browser"].pop("viewports", None)
    elif viewports is not None:
        data["browser"]["viewports"] = [
            v.model_dump(exclude_none=True)
            if hasattr(v, "model_dump")
            else (v.__dict__ if hasattr(v, "__dict__") and not isinstance(v, (str, int, float, bool)) else v)
            for v in viewports
        ]

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)
    return cfg_file


def infer_project_metadata(
    scenario_path: str | Path,
    scenario_data: dict[str, Any] | None = None,
) -> tuple[str, str, Path]:
    """Infere metadados do projeto a partir do caminho do cenário e dados do YAML.

    Retorna: (project_id, project_name, project_root_path)
    """
    resolved_path = Path(scenario_path).resolve()
    current = resolved_path.parent
    root: Path | None = None

    # 1. Procura por marcadores de raiz de projeto subindo a hierarquia
    for parent in [current, *current.parents]:
        if (
            (parent / ".git").exists()
            or (parent / "pyproject.toml").exists()
            or (parent / "package.json").exists()
            or (parent / "cargo.toml").exists()
            or (parent / "Cargo.toml").exists()
            or (parent / "go.mod").exists()
        ):
            root = parent
            break

    # 2. Se estiver dentro de uma pasta chamada 'scenarios' ou 'cenarios', assume a pasta pai
    if root is None:
        for parent in [current, *current.parents]:
            if parent.name.lower() in ("scenarios", "cenarios") and parent.parent != parent:
                root = parent.parent
                break

    # 3. Fallback: o diretório do próprio cenário
    if root is None:
        root = current

    # Inferência do nome do projeto
    project_name: str | None = None
    if scenario_data:
        p_name = scenario_data.get("project") or scenario_data.get("projeto")
        if isinstance(p_name, str) and p_name.strip():
            project_name = p_name.strip()

    if not project_name:
        pkg_json = root / "package.json"
        if pkg_json.is_file():
            try:
                import json

                pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
                if isinstance(pkg_data, dict) and pkg_data.get("name"):
                    project_name = str(pkg_data["name"]).strip()
            except Exception:
                pass

        if not project_name:
            pyproj = root / "pyproject.toml"
            if pyproj.is_file():
                try:
                    text = pyproj.read_text(encoding="utf-8")
                    m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
                    if m:
                        project_name = m.group(1).strip()
                except Exception:
                    pass

    if not project_name:
        project_name = root.name if root.name else "default"

    project_id = re.sub(r"[^a-zA-Z0-9]+", "-", project_name.lower().strip()).strip("-")
    if not project_id:
        project_id = "default"

    return project_id, project_name, root


def register_project_scenario(
    scenario_path: str | Path,
    scenario_data: dict[str, Any] | None = None,
    project_name: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """Registra ou atualiza um cenário no catálogo de projetos em ~/.config/uxsentinel/config.yaml.

    Preserva e acumula múltiplos cenários sob a chave do projeto sem sobrescrever os existentes.
    """
    resolved_path = Path(scenario_path).resolve()
    inferred_id, inferred_name, inferred_root = infer_project_metadata(resolved_path, scenario_data)

    final_name = project_name.strip() if project_name and project_name.strip() else inferred_name
    final_id = (
        re.sub(r"[^a-zA-Z0-9]+", "-", final_name.lower().strip()).strip("-")
        if project_name and project_name.strip()
        else inferred_id
    )
    if not final_id:
        final_id = "default"

    cfg_file = config_path if config_path is not None else ensure_user_config()

    data: dict[str, Any] = {}
    if cfg_file.is_file():
        try:
            content = cfg_file.read_text(encoding="utf-8")
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    if "projects" not in data or not isinstance(data["projects"], dict):
        data["projects"] = {}

    projects_map = data["projects"]
    if final_id not in projects_map or not isinstance(projects_map[final_id], dict):
        projects_map[final_id] = {
            "name": final_name,
            "root_path": str(inferred_root),
            "scenarios": {},
            "last_run": None,
        }

    proj_entry = projects_map[final_id]
    proj_entry["name"] = final_name
    if not proj_entry.get("root_path"):
        proj_entry["root_path"] = str(inferred_root)
    if "scenarios" not in proj_entry or not isinstance(proj_entry["scenarios"], dict):
        proj_entry["scenarios"] = {}

    s_data = scenario_data or {}
    scenario_id = str(s_data.get("id") or resolved_path.stem)
    scenario_title = str(s_data.get("name") or s_data.get("nome") or s_data.get("title") or scenario_id)

    now_iso = datetime.now(UTC).isoformat()
    proj_entry["scenarios"][scenario_id] = {
        "id": scenario_id,
        "path": str(resolved_path),
        "name": scenario_title,
        "last_run": now_iso,
    }
    proj_entry["last_run"] = now_iso

    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        with contextlib.suppress(Exception):
            cfg_file.chmod(0o600)
    except Exception:
        pass

    return cfg_file


def list_registered_projects(config_path: Path | None = None) -> dict[str, ProjectCatalogEntry]:
    """Retorna o catálogo de projetos registrados no config.yaml."""
    cfg_file = config_path if config_path is not None else get_user_config_path()
    if not cfg_file.is_file():
        return {}

    try:
        content = cfg_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or "projects" not in data or not isinstance(data["projects"], dict):
            return {}

        result: dict[str, ProjectCatalogEntry] = {}
        for p_id, p_val in data["projects"].items():
            if isinstance(p_val, dict):
                scenarios_dict: dict[str, ProjectScenarioItem] = {}
                for s_id, s_val in p_val.get("scenarios", {}).items():
                    if isinstance(s_val, dict):
                        scenarios_dict[s_id] = ProjectScenarioItem(
                            id=str(s_val.get("id", s_id)),
                            path=str(s_val.get("path", "")),
                            name=str(s_val.get("name", s_id)),
                            last_run=s_val.get("last_run"),
                        )
                result[p_id] = ProjectCatalogEntry(
                    name=str(p_val.get("name", p_id)),
                    root_path=str(p_val.get("root_path", "")),
                    scenarios=scenarios_dict,
                    last_run=p_val.get("last_run"),
                )
        return result
    except Exception:
        return {}


def find_project_in_catalog(
    query: str,
    config_path: Path | str | None = None,
) -> tuple[str, ProjectCatalogEntry] | None:
    """Localiza um projeto no catálogo por slug exato, nome (case-insensitive) ou correspondência unívoca."""
    clean_q = query.strip()
    if not clean_q:
        return None

    cfg_path = Path(config_path) if config_path else None
    catalog = list_registered_projects(cfg_path)
    if not catalog:
        return None

    q_lower = clean_q.lower()

    # 1. Correspondência exata por ID / Slug
    if q_lower in catalog:
        return q_lower, catalog[q_lower]

    # 2. Correspondência exata por Nome
    for p_id, entry in catalog.items():
        if entry.name.strip().lower() == q_lower:
            return p_id, entry

    # 3. Slug normalizado a partir da query
    slug_q = re.sub(r"[^a-zA-Z0-9]+", "-", q_lower).strip("-")
    if slug_q and slug_q in catalog:
        return slug_q, catalog[slug_q]

    # 4. Correspondência unívoca por prefixo ou substring
    matches: list[tuple[str, ProjectCatalogEntry]] = []
    for p_id, entry in catalog.items():
        if q_lower in p_id.lower() or q_lower in entry.name.lower():
            matches.append((p_id, entry))

    if len(matches) == 1:
        return matches[0]

    return None


def find_scenario_in_project(
    project_entry: ProjectCatalogEntry,
    scenario_query: str,
) -> ProjectScenarioItem | None:
    """Localiza um cenário dentro de um projeto por ID, nome ou nome do arquivo."""
    clean_sq = scenario_query.strip()
    if not clean_sq:
        return None

    sq_lower = clean_sq.lower()

    # 1. Correspondência exata por ID da chave
    if sq_lower in project_entry.scenarios:
        return project_entry.scenarios[sq_lower]

    for _s_id, s_item in project_entry.scenarios.items():
        if s_item.id.lower() == sq_lower:
            return s_item

    # 2. Correspondência exata por Nome / Título do cenário
    for _s_id, s_item in project_entry.scenarios.items():
        if s_item.name.strip().lower() == sq_lower:
            return s_item

    # 3. Correspondência por nome do arquivo (ex: login.yaml ou login)
    for _s_id, s_item in project_entry.scenarios.items():
        path_obj = Path(s_item.path)
        if path_obj.name.lower() == sq_lower or path_obj.stem.lower() == sq_lower:
            return s_item

    # 4. Correspondência unívoca parcial
    matches: list[ProjectScenarioItem] = []
    for s_id, s_item in project_entry.scenarios.items():
        path_obj = Path(s_item.path)
        if sq_lower in s_id.lower() or sq_lower in s_item.name.lower() or sq_lower in path_obj.stem.lower():
            matches.append(s_item)

    if len(matches) == 1:
        return matches[0]

    return None


def remove_project_from_catalog(
    project_id: str,
    config_path: Path | None = None,
) -> bool:
    """Remove um projeto do catálogo de projetos no config.yaml."""
    clean_id = project_id.strip()
    if not clean_id:
        return False

    cfg_file = config_path if config_path is not None else get_user_config_path()
    if not cfg_file.is_file():
        return False

    try:
        content = cfg_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception:
        return False

    if not isinstance(data, dict) or "projects" not in data or not isinstance(data["projects"], dict):
        return False

    target_key: str | None = None
    if clean_id in data["projects"]:
        target_key = clean_id
    else:
        match = find_project_in_catalog(clean_id, cfg_file)
        if match and match[0] in data["projects"]:
            target_key = match[0]

    if target_key is None:
        return False

    del data["projects"][target_key]

    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        with contextlib.suppress(Exception):
            cfg_file.chmod(0o600)
        return True
    except Exception:
        return False


def remove_scenario_from_catalog(
    scenario_id: str,
    project_id: str | None = None,
    config_path: Path | None = None,
) -> bool:
    """Remove o registro de um cenário de um ou todos os projetos no config.yaml."""
    clean_sid = scenario_id.strip()
    if not clean_sid:
        return False

    cfg_file = config_path if config_path is not None else get_user_config_path()
    if not cfg_file.is_file():
        return False

    try:
        content = cfg_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception:
        return False

    if not isinstance(data, dict) or "projects" not in data or not isinstance(data["projects"], dict):
        return False

    removed = False

    def _purge_scenario_from_project(proj_dict: dict[str, Any]) -> bool:
        scenarios_map = proj_dict.get("scenarios")
        if not isinstance(scenarios_map, dict):
            return False
        keys_to_del = []
        for k, s_val in scenarios_map.items():
            if k == clean_sid:
                keys_to_del.append(k)
            elif isinstance(s_val, dict):
                s_id = str(s_val.get("id", ""))
                s_path = str(s_val.get("path", ""))
                if s_id == clean_sid or Path(s_path).name == clean_sid or Path(s_path).stem == clean_sid:
                    keys_to_del.append(k)
        for k in keys_to_del:
            del scenarios_map[k]
        return len(keys_to_del) > 0

    if project_id:
        clean_pid = project_id.strip()
        target_proj_key: str | None = None
        if clean_pid in data["projects"]:
            target_proj_key = clean_pid
        else:
            match = find_project_in_catalog(clean_pid, cfg_file)
            if match and match[0] in data["projects"]:
                target_proj_key = match[0]

        if (
            target_proj_key
            and isinstance(data["projects"][target_proj_key], dict)
            and _purge_scenario_from_project(data["projects"][target_proj_key])
        ):
            removed = True
    else:
        for _p_key, proj_data in data["projects"].items():
            if isinstance(proj_data, dict) and _purge_scenario_from_project(proj_data):
                removed = True

    if not removed:
        return False

    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        with contextlib.suppress(Exception):
            cfg_file.chmod(0o600)
        return True
    except Exception:
        return False


__all__ = [
    "BUILTIN_PROVIDERS",
    "CANONICAL_VIEWPORTS",
    "DEFAULT_CONFIG_TEMPLATE",
    "DEFAULT_FALLBACK_VIEWPORT",
    "DEFAULT_I18N_ALLOWLIST",
    "BrowserSettings",
    "GlobalConfig",
    "JiraSettings",
    "ProjectCatalogEntry",
    "ProjectScenarioItem",
    "ProviderSettings",
    "ReportingSettings",
    "ViewportConfig",
    "VisionSettings",
    "ensure_user_config",
    "find_project_in_catalog",
    "find_scenario_in_project",
    "get_user_config_dir",
    "get_user_config_path",
    "infer_project_metadata",
    "list_registered_projects",
    "load_config",
    "parse_viewport_spec",
    "parse_viewports",
    "register_project_scenario",
    "remove_project_from_catalog",
    "remove_scenario_from_catalog",
    "resolve_axe_mode",
    "resolve_devtools_mode",
    "resolve_display_mode",
    "resolve_fail_fast_mode",
    "resolve_markdown_mode",
    "resolve_video_mode",
    "resolve_viewports",
    "save_active_provider",
    "save_default_viewports",
    "save_jira_config",
]

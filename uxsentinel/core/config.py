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
    output_dir: str = "report"
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


def load_config(config_path: str | None = None) -> GlobalConfig:
    """Carrega o arquivo de configuração YAML com prioridade para o projeto cliente corrente."""
    cwd = Path.cwd()
    pkg_dir = Path(__file__).resolve().parent.parent.parent

    candidate_paths = [
        config_path,
        os.environ.get("UXSENTINEL_CONFIG_PATH"),
        cwd / "uxsentinel.yaml",
        cwd / ".uxsentinel.yaml",
        cwd / "config" / "config.yaml",
        cwd / "config" / "config.example.yaml",
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
        output_dir=reporting_dict.get("output_dir", "report"),
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

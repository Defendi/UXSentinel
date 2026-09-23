"""Serviço de gerenciamento seguro de configuração e testes de conectividade (UXS-33)."""

import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator

from uxsentinel.core.config import (
    GlobalConfig,
    ensure_user_config,
    get_user_config_path,
    load_config,
)
from uxsentinel.vision.client import UnifiedVisionClient


class BrowserConfigDTO(BaseModel):
    headless: bool = False
    slow_mo_ms: int = 350
    devtools: bool = False
    viewport_width: int = 1440
    viewport_height: int = 900
    enable_axe: bool = True
    fail_fast: bool = True


class SecretFieldStatus(BaseModel):
    configured: bool


class JiraSafeDTO(BaseModel):
    enabled: bool = False
    url: str = ""
    email: str = ""
    project_key: str = ""
    issue_type: str = "Bug"
    api_token: SecretFieldStatus


class ProviderSafeDTO(BaseModel):
    type: str
    service: str
    model: str
    base_url: str | None = None
    has_api_key: bool


class ConfigFilesDTO(BaseModel):
    """Localização e status dos arquivos de configuração e ambiente."""

    active_config_path: str
    user_config_path: str
    project_config_path: str | None = None
    env_path: str | None = None
    project_dir: str
    user_config_exists: bool
    project_config_exists: bool
    env_exists: bool


class SafeConfigDTO(BaseModel):
    """Representação segura da configuração global com mascaramento total de segredos."""

    active_provider: str
    fallback_provider: str | None = None
    browser: BrowserConfigDTO
    jira: JiraSafeDTO
    providers: dict[str, ProviderSafeDTO] = Field(default_factory=dict)
    config_files: ConfigFilesDTO | None = None


class ConfigUpdateDTO(BaseModel):
    """Camada de alteração de configurações globais sem persistência direta de tokens."""

    active_provider: str | None = None
    fallback_provider: str | None = None
    browser_headless: bool | None = None
    browser_slow_mo_ms: int | None = None
    browser_devtools: bool | None = None
    jira_enabled: bool | None = None
    jira_url: str | None = None
    jira_email: str | None = None
    jira_project_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _unpack_nested(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "browser" in data and isinstance(data["browser"], dict):
                b = data["browser"]
                if "headless" in b and data.get("browser_headless") is None:
                    data["browser_headless"] = b["headless"]
                if "slow_mo_ms" in b and data.get("browser_slow_mo_ms") is None:
                    data["browser_slow_mo_ms"] = b["slow_mo_ms"]
                if "devtools" in b and data.get("browser_devtools") is None:
                    data["browser_devtools"] = b["devtools"]
            if "jira" in data and isinstance(data["jira"], dict):
                j = data["jira"]
                if "enabled" in j and data.get("jira_enabled") is None:
                    data["jira_enabled"] = j["enabled"]
                if "url" in j and data.get("jira_url") is None:
                    data["jira_url"] = j["url"]
                if "email" in j and data.get("jira_email") is None:
                    data["jira_email"] = j["email"]
                if "project_key" in j and data.get("jira_project_key") is None:
                    data["jira_project_key"] = j["project_key"]
        return data


class ConnectionResult(BaseModel):
    """Resultado estruturado de testes de conectividade (Jira ou IA)."""

    valid: bool
    message: str
    latency_ms: int | None = None


class ConfigService:
    """Serviço de configuração segura do UXSentinel."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._custom_config = config_path is not None
        self.config_path = Path(config_path) if config_path else get_user_config_path()

    def _load_raw_config(self, target_config_path: Path | None = None) -> GlobalConfig:
        target = target_config_path or self.config_path
        return load_config(str(target) if target and target.is_file() else None)

    def get_safe_config(self, project_dir: Path | str | None = None) -> SafeConfigDTO:
        """Gera SafeConfigDTO mascarando todos os segredos e informando os arquivos de config."""
        proj_dir = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()

        user_cfg = get_user_config_path().resolve()
        user_config_path = str(user_cfg)
        user_config_exists = user_cfg.is_file()

        # Resolução de configuração do projeto
        candidate_project_files = [
            proj_dir / "uxsentinel.yaml",
            proj_dir / ".uxsentinel.yaml",
            proj_dir / "config" / "config.yaml",
            proj_dir / "config" / "config.example.yaml",
        ]
        detected_project_cfg: Path | None = None
        for cp in candidate_project_files:
            if cp.is_file():
                detected_project_cfg = cp.resolve()
                break

        if detected_project_cfg:
            project_config_path = str(detected_project_cfg)
            project_config_exists = True
        else:
            default_proj_cfg = proj_dir / "config" / "config.yaml"
            project_config_path = str(default_proj_cfg.resolve())
            project_config_exists = False

        env_file = (proj_dir / ".env").resolve()
        env_path = str(env_file)
        env_exists = env_file.is_file()

        # Resolução do arquivo ativo efetivo respeitando hierarquia
        active_target_path: Path | None = None
        if self._custom_config and self.config_path and self.config_path.is_file():
            active_target_path = self.config_path.resolve()
        elif project_config_exists and detected_project_cfg:
            active_target_path = detected_project_cfg
        elif user_config_exists:
            active_target_path = user_cfg
        else:
            active_target_path = user_cfg

        active_config_path = str(active_target_path)

        cfg = self._load_raw_config(active_target_path)

        # Verifica se o token do Jira está configurado
        jira_token_val = cfg.jira.api_token or ""
        jira_token_configured = bool(jira_token_val.strip()) and not jira_token_val.startswith("${")

        safe_jira = JiraSafeDTO(
            enabled=cfg.jira.enabled,
            url=cfg.jira.url,
            email=cfg.jira.email,
            project_key=cfg.jira.project_key,
            issue_type=cfg.jira.issue_type,
            api_token=SecretFieldStatus(configured=jira_token_configured),
        )

        safe_browser = BrowserConfigDTO(
            headless=cfg.browser.headless,
            slow_mo_ms=cfg.browser.slow_mo_ms,
            devtools=cfg.browser.devtools,
            viewport_width=cfg.browser.viewport_width,
            viewport_height=cfg.browser.viewport_height,
            enable_axe=cfg.browser.enable_axe,
            fail_fast=cfg.browser.fail_fast,
        )

        safe_providers: dict[str, ProviderSafeDTO] = {}
        for pname, psettings in cfg.providers.items():
            key_val = psettings.api_key or ""
            has_key = bool(key_val.strip()) and not key_val.startswith("${")
            safe_providers[pname] = ProviderSafeDTO(
                type=psettings.type,
                service=psettings.service,
                model=psettings.model,
                base_url=psettings.base_url,
                has_api_key=has_key,
            )

        config_files_dto = ConfigFilesDTO(
            active_config_path=active_config_path,
            user_config_path=user_config_path,
            project_config_path=project_config_path,
            env_path=env_path,
            project_dir=str(proj_dir),
            user_config_exists=user_config_exists,
            project_config_exists=project_config_exists,
            env_exists=env_exists,
        )

        return SafeConfigDTO(
            active_provider=cfg.active_provider,
            fallback_provider=cfg.fallback_provider,
            browser=safe_browser,
            jira=safe_jira,
            providers=safe_providers,
            config_files=config_files_dto,
        )

    def update_config(self, data: ConfigUpdateDTO) -> None:
        """Atualiza campos seguros e grava com permissão 0600."""
        target_file = ensure_user_config() if not self.config_path.is_file() else self.config_path
        cfg = self._load_raw_config()

        if data.active_provider is not None:
            cfg.active_provider = data.active_provider
        if data.fallback_provider is not None:
            cfg.fallback_provider = data.fallback_provider
        if data.browser_headless is not None:
            cfg.browser.headless = data.browser_headless
        if data.browser_slow_mo_ms is not None:
            cfg.browser.slow_mo_ms = data.browser_slow_mo_ms
        if data.browser_devtools is not None:
            cfg.browser.devtools = data.browser_devtools
        if data.jira_enabled is not None:
            cfg.jira.enabled = data.jira_enabled
        if data.jira_url is not None:
            cfg.jira.url = data.jira_url
        if data.jira_email is not None:
            cfg.jira.email = data.jira_email
        if data.jira_project_key is not None:
            cfg.jira.project_key = data.jira_project_key

        import yaml

        dumped = yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True)
        target_file.write_text(dumped, encoding="utf-8")
        target_file.chmod(0o600)

    def set_jira_token(self, token: str) -> None:
        """Grava token do Jira com permissão restrita 0600."""
        target_file = ensure_user_config() if not self.config_path.is_file() else self.config_path
        cfg = self._load_raw_config()
        cfg.jira.api_token = token

        import yaml

        dumped = yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True)
        target_file.write_text(dumped, encoding="utf-8")
        target_file.chmod(0o600)

    def set_ai_token(self, provider: str, token: str) -> None:
        """Grava token do provedor de IA com permissão restrita 0600."""
        target_file = ensure_user_config() if not self.config_path.is_file() else self.config_path
        cfg = self._load_raw_config()
        if provider in cfg.providers:
            cfg.providers[provider].api_key = token
        import yaml

        dumped = yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True)
        target_file.write_text(dumped, encoding="utf-8")
        target_file.chmod(0o600)

    async def test_jira_connection(self, url: str, email: str, token: str) -> ConnectionResult:
        """Testa conexão com o Jira Cloud sem persistir credenciais."""
        if not url or not email or not token:
            return ConnectionResult(valid=False, message="URL, e-mail e token do Jira são obrigatórios.")

        api_url = f"{url.rstrip('/')}/rest/api/3/myself"
        start_time = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    api_url,
                    auth=(email, token),
                    headers={"Accept": "application/json"},
                )
                latency = int((time.monotonic() - start_time) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("displayName", email)
                    return ConnectionResult(
                        valid=True,
                        message=f"Conectado com sucesso como {name}!",
                        latency_ms=latency,
                    )
                if resp.status_code in (401, 403):
                    return ConnectionResult(
                        valid=False,
                        message="Credenciais inválidas ou acesso não autorizado (401/403).",
                        latency_ms=latency,
                    )
                return ConnectionResult(
                    valid=False,
                    message=f"Falha na conexão com Jira (HTTP {resp.status_code}).",
                    latency_ms=latency,
                )
        except Exception as ex:
            return ConnectionResult(valid=False, message=f"Erro de rede ou timeout: {ex}")

    async def test_ai_connection(self, provider: str) -> ConnectionResult:
        """Testa conexão com o provedor de IA via chamada de teste nativa."""
        cfg = self._load_raw_config()
        cfg.active_provider = provider

        start_time = time.monotonic()
        try:
            client = UnifiedVisionClient(cfg)
            ok, msg = await client.test_connection(check_fallback=False)
            latency = int((time.monotonic() - start_time) * 1000)
            return ConnectionResult(
                valid=ok,
                message=msg if ok else f"Falha na conexão com '{provider}': {msg}",
                latency_ms=latency,
            )
        except Exception as ex:
            latency = int((time.monotonic() - start_time) * 1000)
            return ConnectionResult(
                valid=False,
                message=f"Erro ao conectar com provedor '{provider}': {ex}",
                latency_ms=latency,
            )

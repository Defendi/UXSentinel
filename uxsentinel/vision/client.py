import logging

import httpx

from uxsentinel.core.config import GlobalConfig, ProviderSettings
from uxsentinel.vision.prompts import QA_SYSTEM_PROMPT

logger = logging.getLogger("uxsentinel.vision")


def _prepare_anthropic_auth(
    provider_name: str,
    model: str,
    api_key: str,
    headers: dict[str, str],
) -> tuple[dict[str, str], str]:
    """Prepara cabeçalhos e modelo compatível para Anthropic, suportando OAuth da conta Pro."""
    hdrs = dict(headers)
    auth_header = hdrs.get("Authorization", "").strip()

    token = (
        auth_header.replace("Bearer ", "").strip() if auth_header else api_key.replace("Bearer ", "").strip()
    )

    is_api_key = token.startswith("sk-ant-api") or api_key.startswith("sk-ant-api")

    if not is_api_key and (
        "sk-ant-oat" in auth_header
        or api_key.startswith("sk-ant-oat")
        or "claude_sso" in provider_name
        or hdrs.get("anthropic-beta") == "oauth-2025-04-20"
    ):
        hdrs["Authorization"] = f"Bearer {token}"
        hdrs.pop("x-api-key", None)
        hdrs.setdefault("anthropic-beta", "oauth-2025-04-20")
        hdrs.setdefault("User-Agent", "claude-cli/2.1.267")
        # Se for modelo da API comercial tradicional que não existe no catálogo OAuth Pro,
        # mapeia para modelos compatíveis da conta Pro
        if model in ("claude-3-5-sonnet-latest", "claude-3-5-sonnet-20241022", "claude-3-7-sonnet-latest"):
            model = "claude-haiku-4-5"
    else:
        if is_api_key:
            hdrs["x-api-key"] = token
            hdrs.pop("Authorization", None)
        elif auth_header:
            hdrs["Authorization"] = auth_header
        elif api_key.startswith("Bearer "):
            hdrs["Authorization"] = api_key
        elif api_key and not api_key.startswith("sk-ant-"):
            hdrs["Authorization"] = f"Bearer {api_key}"
            hdrs["x-api-key"] = api_key
        elif api_key:
            hdrs["x-api-key"] = api_key
        else:
            hdrs.pop("Authorization", None)

    return hdrs, model


class UnifiedVisionClient:
    """Cliente unificado para chamadas a modelos de visão (Cloud API, Ollama Local e SSO Gateway)."""

    def __init__(self, config: GlobalConfig):
        self.config = config

    def _find_provider_name(self, provider: ProviderSettings) -> str:
        """Localiza a chave do provedor no catálogo de configurações."""
        for name, p in self.config.providers.items():
            if p == provider or (
                p.model == provider.model and p.service == provider.service and p.type == provider.type
            ):
                return name
        return self.config.active_provider

    def _ensure_provider_auth(
        self,
        provider: ProviderSettings,
        interactive: bool = True,
        force_refresh: bool = False,
    ) -> str | None:
        """Garante que provedores do tipo SSO possuam token Bearer válido, abrindo o navegador se necessário."""
        p_name = self._find_provider_name(provider)
        is_sso = provider.type == "sso" or "_sso" in p_name

        if not is_sso:
            return provider.api_key

        from uxsentinel.core.sso import (
            get_cached_token,
            get_sso_cache_file,
            login_via_browser,
            refresh_claude_oauth_token,
        )

        auth_header = provider.headers.get("Authorization", "").strip()
        if auth_header in ("Bearer", "Bearer "):
            auth_header = ""

        token = ""
        if not force_refresh:
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif auth_header:
                token = auth_header
            elif provider.api_key and provider.api_key.startswith("Bearer "):
                token = provider.api_key[7:].strip()
            elif provider.api_key and not provider.api_key.startswith("${"):
                token = provider.api_key.strip()

        # Quando force_refresh=True for solicitado, não reutilizar o token em cache atual se houver refresh_token
        if force_refresh:
            ref_tok: str | None = None
            cache_file = get_sso_cache_file()
            if cache_file.is_file():
                try:
                    import json

                    cdata = json.loads(cache_file.read_text(encoding="utf-8"))
                    ref_tok = cdata.get(p_name, {}).get("refresh_token")
                except Exception:
                    ref_tok = None

            if not ref_tok:
                from pathlib import Path

                claude_creds = Path.home() / ".claude" / ".credentials.json"
                if claude_creds.is_file():
                    try:
                        import json

                        ccdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                        ref_tok = ccdata.get("claudeAiOauth", {}).get("refreshToken")
                    except Exception:
                        ref_tok = None

            if ref_tok:
                new_tok = refresh_claude_oauth_token(ref_tok)
                if new_tok:
                    token = new_tok

        # Se não houver token no config ou variável de ambiente, busca no cache local seguro
        if not token:
            cached = get_cached_token(p_name)
            if cached:
                token = cached
            elif interactive:
                # Dispara abertura do navegador para login SSO interativo
                try:
                    token = login_via_browser(p_name, provider)
                except Exception as exc:
                    logger.warning("Falha ao autenticar via SSO no navegador: %s", exc)
                    return None

        if token:
            provider.headers["Authorization"] = f"Bearer {token}"
            provider.api_key = token
            return token

        return None

    async def test_connection(self, check_fallback: bool = True) -> tuple[bool, str]:
        """Testa se a IA está acessível e pronta para auditar telas antes de iniciar os testes."""
        active = self.config.get_active_provider()
        ok, msg = await self._probe_provider(active)
        if ok:
            return True, f"Provedor ativo '{self.config.active_provider}' ({active.model}) operacional."

        if check_fallback:
            fallback_name = self.config.fallback_provider
            if fallback_name and fallback_name != self.config.active_provider:
                fallback = self.config.get_fallback_provider()
                if fallback:
                    fb_ok, fb_msg = await self._probe_provider(fallback)
                    if fb_ok:
                        return True, (
                            f"Provedor principal '{self.config.active_provider}' indisponível ({msg}), "
                            f"mas contingência '{fallback_name}' ({fallback.model}) está operacional."
                        )
        return False, f"Provedor '{self.config.active_provider}' indisponível: {msg}"

    async def _probe_provider(self, provider: ProviderSettings, interactive: bool = True) -> tuple[bool, str]:
        p_name = self._find_provider_name(provider)
        service = provider.service.lower().strip()
        timeout = min(provider.timeout, 8.0)

        # Se o provedor for SSO, resolve credencial ou abre o navegador
        if provider.type == "sso" or "_sso" in p_name:
            token = self._ensure_provider_auth(provider, interactive=interactive)
            if not token:
                return False, (
                    f"Autenticação SSO não realizada para o provedor '{p_name}'. "
                    "Execute 'uxsentinel --login-sso' ou realize o login via navegador."
                )

        api_key = (provider.api_key or "").strip()

        try:
            if service == "ollama":
                url = (provider.base_url or "http://localhost:11434").rstrip("/") + "/api/tags"
                async with httpx.AsyncClient(timeout=timeout, verify=provider.verify_ssl) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    installed = [m.get("name") for m in data.get("models", [])] + [
                        m.get("model") for m in data.get("models", [])
                    ]
                    target = provider.model
                    match = any(
                        target == name or target.split(":")[0] == (name or "").split(":")[0]
                        for name in installed
                        if name
                    )
                    if not match:
                        return False, (
                            f"Ollama ativo, mas o modelo '{target}' não está instalado. "
                            f"Execute 'ollama pull {target}' ou ajuste o modelo no config.yaml."
                        )
                    return True, f"Ollama local operacional com o modelo '{target}'."

            elif service == "anthropic":
                auth_header = provider.headers.get("Authorization", "").strip()
                if auth_header in ("Bearer", "Bearer "):
                    auth_header = ""

                if not api_key and not auth_header:
                    return False, (
                        f"Chave de API ou token SSO ausente para a Anthropic ({provider.model}). "
                        "Defina a variável ANTHROPIC_API_KEY ou CLAUDE_SSO_TOKEN no ambiente."
                    )
                raw_base = provider.base_url or ""
                if not raw_base or "suaempresa.com.br" in raw_base:
                    raw_base = "https://api.anthropic.com/v1"
                url = raw_base.rstrip("/") + "/messages"
                headers, target_model = _prepare_anthropic_auth(
                    p_name,
                    provider.model,
                    api_key,
                    {
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                        **provider.headers,
                    },
                )

                payload = {
                    "model": target_model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                }
                async with httpx.AsyncClient(timeout=timeout, verify=provider.verify_ssl) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return True, f"API Anthropic respondeu com sucesso (modelo: {target_model})."

            elif service in ("openai", "openai_compatible"):
                if service == "openai" and not api_key:
                    return False, (
                        f"Chave de API ausente para o modelo '{provider.model}'. "
                        "Configure OPENAI_API_KEY no ambiente ou no config.yaml."
                    )
                url = (provider.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    **provider.headers,
                }
                payload = {
                    "model": provider.model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                }
                async with httpx.AsyncClient(timeout=timeout, verify=provider.verify_ssl) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return True, "API OpenAI compatível respondeu com sucesso."

            elif service == "gemini":
                auth_header = provider.headers.get("Authorization", "").strip()
                if auth_header in ("Bearer", "Bearer "):
                    auth_header = ""

                if not api_key and not auth_header:
                    return False, (
                        f"Chave de API ou token SSO ausente para o Google Gemini ({provider.model}). "
                        "Defina a variável GEMINI_API_KEY ou GEMINI_SSO_TOKEN no ambiente."
                    )
                base = (provider.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
                headers = {"Content-Type": "application/json", **provider.headers}

                if auth_header:
                    headers["Authorization"] = auth_header
                    url = f"{base}/models/{provider.model}:generateContent"
                elif api_key.startswith("ya29."):
                    headers["Authorization"] = f"Bearer {api_key}"
                    url = f"{base}/models/{provider.model}:generateContent"
                elif api_key:
                    headers["x-goog-api-key"] = api_key
                    url = f"{base}/models/{provider.model}:generateContent"
                else:
                    headers.pop("Authorization", None)
                    url = f"{base}/models/{provider.model}:generateContent"

                payload = {
                    "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 5},
                }
                async with httpx.AsyncClient(timeout=timeout, verify=provider.verify_ssl) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return True, "API Google Gemini respondeu com sucesso."

            else:
                return False, f"Tipo de serviço de IA desconhecido: '{provider.service}'."

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                if provider.type == "sso" or "_sso" in p_name:
                    from uxsentinel.core.sso import clear_cached_token

                    clear_cached_token(p_name)
                return False, (
                    f"Autenticação recusada (HTTP {code}). Verifique sua chave de API ou token SSO "
                    f"para o modelo '{provider.model}' (ou execute 'uxsentinel --login-sso -p {p_name}')."
                )
            elif code == 404:
                return False, (
                    f"Endpoint ou modelo não encontrado (HTTP 404). Verifique se o modelo '{provider.model}' "
                    f"está correto no serviço '{provider.service}'."
                )
            elif code == 429:
                return False, (
                    f"Limite de requisições ou quota excedida (HTTP 429) no provedor '{provider.service}'."
                )
            else:
                detail = exc.response.text[:200].strip()
                return False, f"Erro HTTP {code} retornado pelo provedor: {detail}"
        except httpx.ConnectError:
            target = provider.base_url or provider.service
            return (
                False,
                f"Falha de conexão com o servidor de IA ({target}). Verifique sua conexão ou se o serviço local está ativo.",
            )
        except httpx.TimeoutException:
            return (
                False,
                f"Tempo limite de conexão esgotado ({timeout}s) ao consultar o provedor de IA '{provider.service}'.",
            )
        except Exception as exc:
            return False, f"Falha de comunicação: {exc}"

    async def analyze(
        self,
        image_base64: str,
        user_prompt: str,
        media_type: str = "image/png",
        system_prompt: str | None = None,
    ) -> str:
        """Executa a chamada ao provedor de visão ativo com fallback automático."""
        active_provider = self.config.get_active_provider()
        try:
            return await self._dispatch_provider(
                active_provider, image_base64, user_prompt, media_type, system_prompt=system_prompt
            )
        except Exception as exc:
            logger.warning("Falha ao chamar provedor '%s': %s", active_provider.model, exc)
            fallback = self.config.get_fallback_provider()
            if fallback and fallback != active_provider:
                logger.info("Acionando provedor de fallback: '%s'", fallback.model)
                return await self._dispatch_provider(
                    fallback, image_base64, user_prompt, media_type, system_prompt=system_prompt
                )
            raise exc

    async def _dispatch_provider(
        self,
        provider: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
        system_prompt: str | None = None,
    ) -> str:
        self._ensure_provider_auth(provider, interactive=True)
        service = provider.service.lower().strip()

        if service == "anthropic":
            return await self._call_anthropic(
                provider, image_base64, user_prompt, media_type, system_prompt=system_prompt
            )
        elif service == "openai" or service == "openai_compatible":
            return await self._call_openai_compatible(
                provider, image_base64, user_prompt, media_type, system_prompt=system_prompt
            )
        elif service == "gemini":
            return await self._call_gemini(
                provider, image_base64, user_prompt, media_type, system_prompt=system_prompt
            )
        elif service == "ollama":
            return await self._call_ollama(provider, image_base64, user_prompt, system_prompt=system_prompt)
        else:
            raise ValueError(f"Serviço de IA não suportado: {provider.service}")

    async def _call_anthropic(
        self,
        p: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
        system_prompt: str | None = None,
    ) -> str:
        raw_base = p.base_url or ""
        if not raw_base or "suaempresa.com.br" in raw_base:
            raw_base = "https://api.anthropic.com/v1"
        url = raw_base.rstrip("/") + "/messages"
        p_name = self._find_provider_name(p)
        headers, target_model = _prepare_anthropic_auth(
            p_name,
            p.model,
            p.api_key or "",
            {
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                **p.headers,
            },
        )
        sys_prompt = system_prompt or QA_SYSTEM_PROMPT
        payload = {
            "model": target_model,
            "max_tokens": p.max_tokens,
            "temperature": p.temperature,
            "system": sys_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": user_prompt,
                        },
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=p.timeout, verify=p.verify_ssl) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                is_sso = (
                    p.type == "sso"
                    or "claude_sso" in p_name
                    or str(p.api_key or "").startswith("sk-ant-oat")
                    or "sk-ant-oat" in str(headers.get("Authorization", ""))
                )
                if exc.response.status_code == 401 and is_sso:
                    # Tenta renovar o token e retentar a requisição uma vez de forma transparente
                    from pathlib import Path

                    from uxsentinel.core.sso import get_sso_cache_file, refresh_claude_oauth_token

                    ref_tok: str | None = None
                    cache_file = get_sso_cache_file()
                    if cache_file.is_file():
                        try:
                            import json

                            cdata = json.loads(cache_file.read_text(encoding="utf-8"))
                            ref_tok = cdata.get(p_name, {}).get("refresh_token")
                        except Exception:
                            ref_tok = None

                    if not ref_tok:
                        claude_creds = Path.home() / ".claude" / ".credentials.json"
                        if claude_creds.is_file():
                            try:
                                import json

                                ccdata = json.loads(claude_creds.read_text(encoding="utf-8"))
                                ref_tok = ccdata.get("claudeAiOauth", {}).get("refreshToken")
                            except Exception:
                                ref_tok = None

                    if ref_tok:
                        new_tok = refresh_claude_oauth_token(ref_tok)
                        if new_tok:
                            p.api_key = new_tok
                            p.headers["Authorization"] = f"Bearer {new_tok}"
                            headers["Authorization"] = f"Bearer {new_tok}"
                            if "x-api-key" in headers:
                                headers["x-api-key"] = new_tok
                            # Retenta a chamada HTTP de forma transparente
                            response = await client.post(url, json=payload, headers=headers)
                            response.raise_for_status()
                        else:
                            raise exc
                    else:
                        raise exc
                else:
                    raise exc

            data = response.json()
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", "")
            return ""

    async def _call_openai_compatible(
        self,
        p: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
        system_prompt: str | None = None,
    ) -> str:
        url = (p.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {p.api_key or ''}",
            "Content-Type": "application/json",
            **p.headers,
        }
        image_data_uri = f"data:{media_type};base64,{image_base64}"
        sys_prompt = system_prompt or QA_SYSTEM_PROMPT

        payload = {
            "model": p.model,
            "max_tokens": p.max_tokens,
            "temperature": p.temperature,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "image_url": {"url": image_data_uri, "detail": "high"},
                            "type": "image_url",
                        },
                    ],
                },
            ],
        }

        async with httpx.AsyncClient(timeout=p.timeout, verify=p.verify_ssl) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    async def _call_gemini(
        self,
        p: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
        system_prompt: str | None = None,
    ) -> str:
        base = (p.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        headers = {"Content-Type": "application/json", **p.headers}
        api_key = p.api_key or ""
        sys_prompt = system_prompt or QA_SYSTEM_PROMPT

        # Suporte a SSO (OAuth2 Bearer Token / GCP / Vertex AI / Gateway Corporativo)
        if api_key.startswith("ya29.") or "Authorization" in headers:
            if "Authorization" not in headers and api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            url = f"{base}/models/{p.model}:generateContent"
        elif api_key:
            # API Key direta (Google AI Studio) - suporta header x-goog-api-key e query param
            headers["x-goog-api-key"] = api_key
            url = f"{base}/models/{p.model}:generateContent"
        else:
            url = f"{base}/models/{p.model}:generateContent"

        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_prompt},
                        {
                            "inline_data": {
                                "mime_type": media_type,
                                "data": image_base64,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": p.temperature,
                "maxOutputTokens": p.max_tokens,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=p.timeout, verify=p.verify_ssl) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""

    async def _call_ollama(
        self,
        p: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        url = (p.base_url or "http://localhost:11434").rstrip("/") + "/api/generate"
        headers = {"Content-Type": "application/json", **p.headers}
        sys_prompt = system_prompt or QA_SYSTEM_PROMPT

        prompt_combined = f"{sys_prompt}\n\n{user_prompt}"
        payload = {
            "model": p.model,
            "prompt": prompt_combined,
            "images": [image_base64],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": p.temperature,
            },
        }

        async with httpx.AsyncClient(timeout=p.timeout, verify=p.verify_ssl) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

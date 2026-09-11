import logging

import httpx

from uxsentinel.core.config import GlobalConfig, ProviderSettings
from uxsentinel.vision.prompts import QA_SYSTEM_PROMPT

logger = logging.getLogger("uxsentinel.vision")


class UnifiedVisionClient:
    """Cliente unificado para chamadas a modelos de visão (Cloud API, Ollama Local e SSO Gateway)."""

    def __init__(self, config: GlobalConfig):
        self.config = config

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

    async def _probe_provider(self, provider: ProviderSettings) -> tuple[bool, str]:
        service = provider.service.lower().strip()
        timeout = min(provider.timeout, 8.0)
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
                url = (provider.base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
                headers = {
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    **provider.headers,
                }
                if auth_header:
                    headers["Authorization"] = auth_header
                elif api_key.startswith("Bearer "):
                    headers["Authorization"] = api_key
                elif api_key and not api_key.startswith("sk-ant-"):
                    headers["Authorization"] = f"Bearer {api_key}"
                    headers["x-api-key"] = api_key
                elif api_key:
                    headers["x-api-key"] = api_key
                else:
                    headers.pop("Authorization", None)

                payload = {
                    "model": provider.model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                }
                async with httpx.AsyncClient(timeout=timeout, verify=provider.verify_ssl) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return True, "API Anthropic respondeu com sucesso."

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
                return False, (
                    f"Autenticação recusada (HTTP {code}). Verifique sua chave de API ou token SSO "
                    f"para o modelo '{provider.model}'."
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
    ) -> str:
        """Executa a chamada ao provedor de visão ativo com fallback automático."""
        active_provider = self.config.get_active_provider()
        try:
            return await self._dispatch_provider(active_provider, image_base64, user_prompt, media_type)
        except Exception as exc:
            logger.warning("Falha ao chamar provedor '%s': %s", active_provider.model, exc)
            fallback = self.config.get_fallback_provider()
            if fallback and fallback != active_provider:
                logger.info("Acionando provedor de fallback: '%s'", fallback.model)
                return await self._dispatch_provider(fallback, image_base64, user_prompt, media_type)
            raise exc

    async def _dispatch_provider(
        self,
        provider: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
    ) -> str:
        service = provider.service.lower().strip()

        if service == "anthropic":
            return await self._call_anthropic(provider, image_base64, user_prompt, media_type)
        elif service == "openai" or service == "openai_compatible":
            return await self._call_openai_compatible(provider, image_base64, user_prompt, media_type)
        elif service == "gemini":
            return await self._call_gemini(provider, image_base64, user_prompt, media_type)
        elif service == "ollama":
            return await self._call_ollama(provider, image_base64, user_prompt)
        else:
            raise ValueError(f"Serviço de IA não suportado: {provider.service}")

    async def _call_anthropic(
        self,
        p: ProviderSettings,
        image_base64: str,
        user_prompt: str,
        media_type: str,
    ) -> str:
        url = (p.base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **p.headers,
        }
        api_key = p.api_key or ""

        # Suporte a SSO (OAuth2 / JWT Bearer Token / Gateway Corporativo)
        if "Authorization" in headers:
            pass
        elif api_key.startswith("Bearer "):
            headers["Authorization"] = api_key
        elif api_key and not api_key.startswith("sk-ant-"):
            # Token corporativo SSO / Gateway
            headers["Authorization"] = f"Bearer {api_key}"
            headers["x-api-key"] = api_key
        elif api_key:
            headers["x-api-key"] = api_key
        payload = {
            "model": p.model,
            "max_tokens": p.max_tokens,
            "temperature": p.temperature,
            "system": QA_SYSTEM_PROMPT,
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
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
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
    ) -> str:
        url = (p.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {p.api_key or ''}",
            "Content-Type": "application/json",
            **p.headers,
        }
        image_data_uri = f"data:{media_type};base64,{image_base64}"

        payload = {
            "model": p.model,
            "max_tokens": p.max_tokens,
            "temperature": p.temperature,
            "messages": [
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_uri, "detail": "high"},
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
    ) -> str:
        base = (p.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        headers = {"Content-Type": "application/json", **p.headers}
        api_key = p.api_key or ""

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
            "system_instruction": {"parts": [{"text": QA_SYSTEM_PROMPT}]},
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
    ) -> str:
        url = (p.base_url or "http://localhost:11434").rstrip("/") + "/api/generate"
        headers = {"Content-Type": "application/json", **p.headers}

        prompt_combined = f"{QA_SYSTEM_PROMPT}\n\n{user_prompt}"
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

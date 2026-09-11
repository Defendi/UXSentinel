import logging

import httpx

from uxsentinel.core.config import GlobalConfig, ProviderSettings
from uxsentinel.vision.prompts import QA_SYSTEM_PROMPT

logger = logging.getLogger("uxsentinel.vision")


class UnifiedVisionClient:
    """Cliente unificado para chamadas a modelos de visão (Cloud API, Ollama Local e SSO Gateway)."""

    def __init__(self, config: GlobalConfig):
        self.config = config

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
            "x-api-key": p.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **p.headers,
        }
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

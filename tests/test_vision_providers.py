from unittest.mock import MagicMock, patch

import pytest

from uxsentinel.cli import list_supported_providers
from uxsentinel.core.config import GlobalConfig, ProviderSettings
from uxsentinel.vision.client import UnifiedVisionClient


@pytest.fixture
def vision_client():
    config = GlobalConfig()
    return UnifiedVisionClient(config)


@pytest.mark.asyncio
async def test_probe_provider_missing_keys(vision_client):
    """Testa se _probe_provider retorna False e mensagem de erro correta quando chaves estão ausentes."""

    # Groq Cloud
    groq_provider = ProviderSettings(
        type="api",
        service="groq",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.2-11b-vision-preview",
        api_key="",
    )
    ok, msg = await vision_client._probe_provider(groq_provider)
    assert not ok
    assert "GROQ_API_KEY" in msg

    # OpenRouter
    or_provider = ProviderSettings(
        type="api",
        service="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.2-11b-vision-instruct",
        api_key="",
    )
    ok, msg = await vision_client._probe_provider(or_provider)
    assert not ok
    assert "OPENROUTER_API_KEY" in msg

    # Mistral AI
    mistral_provider = ProviderSettings(
        type="api",
        service="mistral",
        base_url="https://api.mistral.ai/v1",
        model="pixtral-12b-2409",
        api_key="",
    )
    ok, msg = await vision_client._probe_provider(mistral_provider)
    assert not ok
    assert "MISTRAL_API_KEY" in msg

    # Azure OpenAI
    azure_provider = ProviderSettings(type="api", service="azure", base_url="", model="gpt-4o", api_key="")
    ok, msg = await vision_client._probe_provider(azure_provider)
    assert not ok
    assert "AZURE_OPENAI_API_KEY" in msg


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_probe_provider_success(mock_post, vision_client):
    """Testa se _probe_provider realiza o ping corretamente (mockado) e constrói headers certos."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    # Azure OpenAI
    azure_provider = ProviderSettings(
        type="api",
        service="azure",
        base_url="https://test.openai.azure.com",
        model="gpt-4o",
        api_key="test-key",
    )
    ok, msg = await vision_client._probe_provider(azure_provider)
    assert ok
    assert "API azure compatível respondeu com sucesso" in msg

    # Check headers
    args, kwargs = mock_post.call_args
    assert "api-key" in kwargs["headers"]
    assert kwargs["headers"]["api-key"] == "test-key"

    # LM Studio
    lm_provider = ProviderSettings(
        type="local",
        service="lmstudio",
        base_url="http://localhost:1234/v1",
        model="qwen2-vl-7b-instruct",
        api_key="none",
    )
    ok, msg = await vision_client._probe_provider(lm_provider)
    assert ok
    assert "API lmstudio compatível respondeu com sucesso" in msg


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_dispatch_provider_openai_compatible(mock_post, vision_client):
    """Testa se o despacho multimodal funciona para os novos provedores usando o formato compatível."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"choices": [{"message": {"content": "Análise mockada do provedor"}}]}
    mock_post.return_value = mock_response

    groq_provider = ProviderSettings(
        type="api",
        service="groq",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.2-11b-vision-preview",
        api_key="test-key",
    )

    res = await vision_client._dispatch_provider(groq_provider, "base64data", "O que tem aqui?", "image/png")
    assert res == "Análise mockada do provedor"

    args, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert payload["model"] == "llama-3.2-11b-vision-preview"
    assert "image_url" in payload["messages"][1]["content"][1]


def test_list_providers_cli(capsys):
    """Testa se todos os novos provedores são listados no CLI."""
    cfg = GlobalConfig()
    list_supported_providers(cfg)

    captured = capsys.readouterr()
    output = captured.out

    assert "groq" in output
    assert "openrouter" in output
    assert "mistral" in output
    assert "azure" in output
    assert "lmstudio" in output

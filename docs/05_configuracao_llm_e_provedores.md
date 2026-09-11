# Configuração Unificada de Modelos de Linguagem e Visão (LLMs)

O **UXSentinel** possui uma camada de abstração de inteligência artificial agnóstica. Todas as preferências de modelos de visão, chaves de acesso e conexões são orquestradas a partir de um único arquivo de configuração: `config/config.yaml`.

---

## 1. Categorias de Provedores Suportadas

Para atender desde o desenvolvedor individual até ambientes corporativos rigorosos com segurança de dados, o UXSentinel suporta três tipos fundamentais de provedores:

1. **`api` (Provedores Cloud Públicos)**:
   - **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus.
   - **OpenAI**: GPT-4o, GPT-4o-mini.
   - **Google Gemini**: Gemini 1.5 Pro, Gemini 1.5 Flash.
2. **`local` (Inferência Local / On-Premise)**:
   - **Ollama**: Modelos multimodais locais como `qwen2-vl`, `llava`, `minicpm-v` rodando em GPU/CPU própria sem enviar nenhum dado para a nuvem.
   - **vLLM / LocalAI**: Endpoints locais de alta performance compatíveis com a API do OpenAI.
3. **`sso` / `gateway` (Gateways Corporativos e Nuvem Privada)**:
   - Servidores intermediários corporativos (ex: LiteLLM, Azure OpenAI Gateway, AWS Bedrock via proxy interno).
   - Autenticação com Bearer Token de SSO, certificados mTLS ou headers corporativos customizados (ex: `X-Corporate-ID`, `Authorization: Bearer <SSO_TOKEN>`).

---

## 2. Estrutura Canônica do `config/config.yaml`

```yaml
# ==============================================================================
# UXSentinel - Configuração Global de Inteligência Artificial e Visão
# ==============================================================================

# Define qual provedor está ativo no momento
active_provider: "anthropic_cloud"   # Opções: anthropic_cloud, openai_cloud, gemini_cloud, ollama_local, corporate_gateway

# Configuração de fallback caso o provedor principal atinja rate limit ou caia
fallback_provider: "ollama_local"

# Catálogo de Provedores Configurados
providers:
  # ----------------------------------------------------------------------------
  # Categoria 1: Provedores Cloud (API Pública)
  # ----------------------------------------------------------------------------
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

  # ----------------------------------------------------------------------------
  # Categoria 2: Modelos Locais (Air-Gapped / Privacidade Total)
  # ----------------------------------------------------------------------------
  ollama_local:
    type: "local"
    service: "ollama"
    base_url: "http://localhost:11434"
    model: "qwen2-vl:7b"               # Modelo multimodal com suporte a imagem
    temperature: 0.1
    timeout: 60

  vllm_local:
    type: "local"
    service: "openai_compatible"
    base_url: "http://localhost:8000/v1"
    model: "Qwen/Qwen2-VL-7B-Instruct"
    api_key: "none"
    timeout: 60

  # ----------------------------------------------------------------------------
  # Categoria 3: Gateway Corporativo / SSO / Enterprise Proxy
  # ----------------------------------------------------------------------------
  corporate_gateway:
    type: "sso"
    service: "openai_compatible"
    base_url: "https://ai-gateway.suaempresa.com.br/v1"
    model: "corporate-gpt4o-vision"
    api_key: "${SSO_CORPORATE_TOKEN}"
    headers:
      X-Enterprise-Client-Id: "${ENTERPRISE_CLIENT_ID:-uxsentinel-qa}"
      X-Corporate-Department: "QualityAssurance"
    timeout: 45
    verify_ssl: true
```

---

## 3. Alternância Rápida entre Provedores

Você pode alternar o provedor ativo de três maneiras:

1. **Pelo arquivo `config.yaml`**: Alterando o campo `active_provider`.
2. **Via Variável de Ambiente**:
   ```bash
   export UXSENTINEL_ACTIVE_PROVIDER=ollama_local
   ```
3. **Via Linha de Comando (CLI)**:
   ```bash
   python main.py --provider gemini_cloud --scenario scenarios/login.yaml
   ```

---

## 4. Segurança e Segredos

- Nenhuma chave de API ou token de SSO deve ser gravado diretamente em texto plano no arquivo de configuração caso o projeto seja versionado em Git.
- O parser do UXSentinel suporta a interpolação automática de variáveis de ambiente no padrão `${NOME_DA_VARIAVEL}` e com valores padrão `${VARIAVEL:-padrao}`.

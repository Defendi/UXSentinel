# Configuração Unificada de Modelos de Linguagem e Visão (LLMs)

O **UXSentinel** possui uma camada de abstração de inteligência artificial agnóstica. Todas as preferências de modelos de visão, chaves de acesso e conexões são orquestradas a partir de um único arquivo de configuração: `config/config.yaml` (ou `~/.config/uxsentinel/config.yaml`).

---

## 1. Categorias de Provedores Suportadas

Para atender desde o desenvolvedor individual até ambientes corporativos rigorosos com governança de dados e identidade centralizada, o UXSentinel suporta três tipos fundamentais de provedores:

1. **`api` (Provedores Cloud Públicos)**:
   - **Google Gemini**: Gemini 1.5 Pro, Gemini 1.5 Flash (via chave de API pública).
   - **Anthropic Claude**: Claude 3.5 Sonnet, Claude 3 Opus (via `x-api-key`).
   - **OpenAI**: GPT-4o, GPT-4o-mini (via `api_key`).
2. **`sso` / `gateway` (Gateways Corporativos e Nuvem Privada com Autenticação SSO)**:
   - **`gemini_sso`**: Google Gemini consumido através de Single Sign-On corporativo (Google Cloud Vertex / Workspace SSO), autenticado via token JWT/OAuth2 no header `Authorization: Bearer <token>`.
   - **`claude_sso`**: Anthropic Claude consumido através de autenticação corporativa centralizada (SSO corporativo / Proxy Bedrock / IAM OIDC), autenticado via Bearer token no cabeçalho HTTP.
   - **`corporate_gateway`**: Gateways internos genéricos (ex: LiteLLM, Azure OpenAI Gateway, proxy corporativo com headers `X-Corporate-ID`, mTLS ou certificados internos).
3. **`local` (Inferência Local / On-Premise)**:
   - **Ollama**: Modelos multimodais locais como `qwen2-vl:7b`, `llava`, `minicpm-v` rodando em GPU/CPU própria sem enviar nenhum dado para a nuvem.
   - **vLLM / LocalAI**: Endpoints locais de alta performance compatíveis com a API do OpenAI.

---

## 2. Estrutura Canônica do `config/config.yaml`

```yaml
# ==============================================================================
# UXSentinel - Configuração Global de Inteligência Artificial e Visão
# ==============================================================================

# Define qual provedor está ativo no momento
active_provider: "gemini_sso"   # Opções: gemini_sso, claude_sso, gemini_cloud, anthropic_cloud, openai_cloud, ollama_local, corporate_gateway

# Configuração de fallback caso o provedor principal atinja rate limit ou caia
fallback_provider: "ollama_local"

# Catálogo de Provedores Configurados
providers:
  # ----------------------------------------------------------------------------
  # Categoria 1: Provedores com SSO Corporativo (Bearer Token / OAuth2)
  # ----------------------------------------------------------------------------
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
    model: "claude-3-5-sonnet-latest"
    api_key: "${CLAUDE_SSO_TOKEN}"
    headers:
      Authorization: "Bearer ${CLAUDE_SSO_TOKEN}"
    max_tokens: 2000
    temperature: 0.1

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

  # ----------------------------------------------------------------------------
  # Categoria 2: Provedores Cloud (API Pública com Chaves Nativas)
  # ----------------------------------------------------------------------------
  gemini_cloud:
    type: "api"
    service: "gemini"
    model: "gemini-1.5-pro"
    api_key: "${GEMINI_API_KEY}"
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

  # ----------------------------------------------------------------------------
  # Categoria 3: Modelos Locais (Air-Gapped / Privacidade Total)
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
```

---

## 3. Como Utilizar Provedores via SSO Corporativo

Muitas empresas bloqueiam o uso de chaves de API estáticas e exigem que todo o tráfego de IA seja auditado e autenticado através de um provedor de identidade corporativo (Google Cloud Identity, Okta, Microsoft Entra ID / Azure AD, Ping Identity).

### 3.1 Google Gemini via SSO (`gemini_sso`)
1. Gere o token de acesso da sua conta corporativa via Google Cloud CLI:
   ```bash
   export GEMINI_SSO_TOKEN=$(gcloud auth print-access-token)
   ```
2. Dispare a auditoria visual com o UXSentinel:
   ```bash
   uxsentinel -s scenarios/meu_teste.yaml -p gemini_sso
   ```
O cliente HTTP do UXSentinel enviará o cabeçalho `Authorization: Bearer <seu_token>` diretamente para o endpoint oficial do Google Gemini, sem requerer chave de API estática no código ou na URL.

### 3.2 Anthropic Claude via SSO (`claude_sso`)
1. Obtenha o token temporário de sessão gerado pelo portal de SSO ou IAM da sua empresa:
   ```bash
   export CLAUDE_SSO_TOKEN="ey..."
   ```
2. Execute o UXSentinel informando o provedor:
   ```bash
   uxsentinel -s scenarios/meu_teste.yaml -p claude_sso
   ```
O cliente do UXSentinel configurará automaticamente o cabeçalho `Authorization: Bearer <token>` e respeitará as políticas de inspeção da organização.

---

## 4. Alternância Rápida entre Provedores

Você pode alternar o provedor ativo de três maneiras, em ordem de precedência:

1. **Via Linha de Comando (CLI)** (Maior precedência):
   ```bash
   uxsentinel -s scenarios/login.yaml -p gemini_sso
   uxsentinel -s scenarios/login.yaml -p claude_sso
   uxsentinel -s scenarios/login.yaml -p ollama_local
   ```
2. **Definido Diretamente no Arquivo de Cenário (`.yaml`)**:
   ```yaml
   provider: "gemini_sso"
   ```
3. **Pelo arquivo `config.yaml`**:
   Alterando o valor da chave `active_provider`.

---

## 5. Segurança e Segredos

- **Nunca comite chaves ou tokens no Git**: O UXSentinel ignora arquivos de segredos locais via `.gitignore`.
- **Interpolação de Variáveis**: O parser do UXSentinel suporta a interpolação automática de variáveis de ambiente no formato `${NOME_DA_VARIAVEL}` e valores padrão com `${VARIAVEL:-padrao}`.
- **Validação de Fallback**: Caso o token de SSO expire durante a execução de uma suíte extensa de testes, o UXSentinel aciona graciosamente o `fallback_provider` (ex: `ollama_local`) sem interromper a execução do fluxo.

---

## 6. Verificação Prévia de Conectividade com a IA (Pre-flight Check)

Para evitar consumo desnecessário de recursos do sistema e aberturas de janelas de navegador Playwright que falhariam no meio do fluxo, o UXSentinel conta com um mecanismo automático de **Pre-flight Check**.

### 6.1 Pré-validação Automática ao Iniciar Cenários
Antes de abrir o navegador e executar qualquer passo, o agente realiza um probe ultraleve (timeout de 8s) com o provedor de IA configurado:
- Se a IA estiver acessível, o cenário inicia normalmente.
- Se a chave estiver ausente, expirada ou o serviço offline (e não houver fallback válido), a execução é **imediatamente abortada**, emitindo uma mensagem de erro detalhada em português com orientações de correção.

### 6.2 Teste Direto de Conexão via CLI (`--check-ai`)
Você pode testar a conectividade de qualquer provedor configurado diretamente pelo terminal, sem rodar nenhum teste de UI:

```bash
# Testa o provedor padrão ativo (active_provider)
uxsentinel --check-ai

# Testa um provedor específico (ex: Gemini via SSO)
uxsentinel --check-ai -p gemini_sso

# Testa Claude via SSO
uxsentinel --check-ai -p claude_sso

# Testa servidor Ollama local
uxsentinel --check-ai -p ollama_local
```

Se tudo estiver correto, o UXSentinel exibe uma mensagem de sucesso confirmando a prontidão do modelo. Caso ocorra erro, são informadas as instruções exatas para regularização (ex: exportar variável de ambiente, verificar token SSO ou baixar o modelo no Ollama).


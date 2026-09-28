# 🔌 Guia de Uso: Servidor MCP Nativo do UXSentinel (Model Context Protocol)

Este documento é o guia oficial de integração e operação do **Servidor MCP nativo do UXSentinel**. Ele ensina como conectar o motor autônomo de Visual QA, Acessibilidade e Auditoria Web do UXSentinel diretamente aos seus assistentes e IDEs com IA (como **Claude Desktop**, **Cursor**, **Antigravity**, **VS Code Copilot**, **Windsurf**, entre outros).

---

## 📑 Índice

1. [O que é o UXSentinel MCP?](#1-o-que-é-o-uxsentinel-mcp)
2. [Como Iniciar o Servidor](#2-como-iniciar-o-servidor)
3. [Configuração nos Principais Clientes e IDEs](#3-configuração-nos-principais-clientes-e-ides)
   - [Claude Desktop](#31-claude-desktop)
   - [Cursor](#32-cursor)
   - [Antigravity / Gemini CLI](#33-antigravity--gemini-cli)
   - [VS Code (Cline / Roo Code / Copilot)](#34-vs-code-cline--roo-code)
   - [Windsurf](#35-windsurf)
4. [Ferramentas Disponíveis (Tools)](#4-ferramentas-disponíveis-tools)
   - [`list_scenarios`](#41-list_scenarios)
   - [`validate_scenario`](#42-validate_scenario)
   - [`run_scenario`](#43-run_scenario)
   - [`inspect_url`](#44-inspect_url)
   - [`get_last_report`](#45-get_last_report)
5. [Recursos Compartilhados (Resources)](#5-recursos-compartilhados-resources)
6. [Exemplos Práticos de Interação com a IA](#6-exemplos-práticos-de-interação-com-a-ia)
7. [Arquitetura e Boas Práticas (Isolamento de Stdio)](#7-arquitetura-e-boas-práticas-isolamento-de-stdio)
8. [Troubleshooting e Diagnóstico](#8-troubleshooting-e-diagnóstico)

---

## 1. O que é o UXSentinel MCP?

O **UXSentinel MCP** implementa a especificação oficial do [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) da Anthropic, operando sobre transporte **JSON-RPC 2.0 via `stdio`**.

Ao ativar o servidor MCP, qualquer agente de IA conectado ganha superpoderes para:
- 🔍 **Inspecionar e auditar páginas web** em tempo real (`inspect_url`);
- 🧪 **Disparar cenários automatizados** de teste e regressão visual com Playwright (`run_scenario`);
- 📐 **Validar sintaxe e semântica de cenários YAML** sem precisar abrir janelas gráficas (`validate_scenario`);
- 📂 **Explorar catálogos locais e bibliotecas** de testes (`list_scenarios`);
- 📊 **Consultar relatórios e métricas de acessibilidade (WCAG 2.2 AA)** e usabilidade (`get_last_report`).

---

## 2. Como Iniciar o Servidor

Você pode iniciar o servidor MCP nativo diretamente pela linha de comando:

### Opção 1: Via binário CLI do ambiente local
```bash
uxsentinel mcp
# ou
uxsentinel --mcp
```

### Opção 2: Via gerenciador `uv`
```bash
uv run uxsentinel mcp
```

### Opção 3: Via interpretador Python com ambiente virtual
```bash
/caminho/para/UXSentinel/ambiente/bin/uxsentinel mcp
```

> [!NOTE]
> O servidor MCP escuta comandos através da entrada padrão (`stdin`) e responde via saída padrão (`stdout`). Qualquer log de depuração, telemetria ou print interno é redirecionado automaticamente para `stderr`, preservando a integridade das mensagens JSON-RPC.

---

## 3. Configuração nos Principais Clientes e IDEs

### 3.1. Claude Desktop

Adicione a configuração no arquivo `claude_desktop_config.json`:
- **Linux:** `~/.config/Claude/claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "/caminho/para/UXSentinel/ambiente/bin/uxsentinel",
      "args": ["mcp"],
      "cwd": "/caminho/para/seu-projeto"
    }
  }
}
```

*Se estiver usando o `uv`:*
```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "uv",
      "args": [
        "--directory",
        "/caminho/para/UXSentinel",
        "run",
        "uxsentinel",
        "mcp"
      ]
    }
  }
}
```

---

### 3.2. Cursor

No Cursor, você pode configurar o servidor em **Cursor Settings > Features > MCP**, ou criar um arquivo `.cursor/mcp.json` na raiz do seu projeto:

```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "/caminho/para/UXSentinel/ambiente/bin/uxsentinel",
      "args": ["mcp"]
    }
  }
}
```

---

### 3.3. Antigravity / Gemini CLI

Em ambientes do **Google Antigravity** ou assistentes baseados em Gemini com suporte a MCP, configure no `mcp_config.json`:

```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "uv",
      "args": [
        "--directory",
        "/caminho/para/UXSentinel",
        "run",
        "uxsentinel",
        "mcp"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

### 3.4. VS Code (Cline / Roo Code)

No painel de configurações do **Cline** ou **Roo Code** (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "/caminho/para/UXSentinel/ambiente/bin/python",
      "args": ["-m", "uxsentinel.cli", "mcp"],
      "disabled": false,
      "autoApprove": [
        "list_scenarios",
        "validate_scenario",
        "get_last_report"
      ]
    }
  }
}
```

---

### 3.5. Windsurf

No arquivo de configuração `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "uxsentinel": {
      "command": "/caminho/para/UXSentinel/ambiente/bin/uxsentinel",
      "args": ["mcp"]
    }
  }
}
```

---

## 4. Ferramentas Disponíveis (Tools)

O servidor MCP expõe **5 ferramentas robustas** projetadas para interação autônoma com LLMs.

### 4.1. `list_scenarios`
Varre e lista todos os cenários YAML disponíveis (locais em `./scenarios` e na biblioteca embutida do UXSentinel).

* **Parâmetros:**
  - `tag` *(string, opcional)*: Filtra por tag específica (ex.: `"smoke"`, `"login"`, `"a11y"`).
  - `profile` *(string, opcional)*: Filtra pelo perfil da aplicação (`"generic"` ou `"odoo"`).

* **Exemplo de Retorno:**
```json
[
  {
    "id": "fluxo_login",
    "title": "Validação de Login e Sessão",
    "profile": "generic",
    "path": "scenarios/login.yaml",
    "tags": ["smoke", "auth"],
    "steps_count": 5,
    "description": "Autentica usuário e valida dashboard inicial"
  }
]
```

---

### 4.2. `validate_scenario`
Realiza análise estática e sintática profunda de um arquivo YAML de cenário sem inicializar navegadores ou gastar recursos computacionais.

* **Parâmetros:**
  - `scenario_path` *(string, obrigatório)*: Caminho para o arquivo `.yaml`.

* **Exemplo de Retorno:**
```json
{
  "valid": true,
  "scenario_path": "scenarios/login.yaml",
  "id": "fluxo_login",
  "title": "Validação de Login e Sessão",
  "steps_count": 5,
  "tags": ["smoke"],
  "errors": []
}
```

---

### 4.3. `run_scenario`
Executa o fluxo completo do cenário com Playwright, capturando checkpoints visuais, auditoria de acessibilidade Axe-Core e inspeção por IA multimodal.

* **Parâmetros:**
  - `scenario_path` *(string, obrigatório)*: Caminho relativo ou absoluto do cenário YAML.
  - `profile` *(string, opcional)*: Perfil de execução (`"generic"` ou `"odoo"`).
  - `headless` *(boolean, opcional, padrão `true`)*: Se `false`, exibe a janela do navegador em tempo real.
  - `slowmo` *(integer, opcional, padrão `0`)*: Delay em milissegundos entre as ações.
  - `devtools` *(boolean, opcional, padrão `false`)*: Abre o Chromium DevTools anexado.
  - `viewport` *(string, opcional)*: Preset (`"desktop"`, `"tablet"`, `"mobile"`) ou dimensão customizada (`"1920x1080"`).
  - `ai_provider` *(string, opcional)*: Provedor de IA ativo (`"gemini_sso"`, `"claude_sso"`, `"ollama_local"`, etc.).

* **Exemplo de Retorno:**
```json
{
  "scenario_id": "fluxo_login",
  "success": true,
  "status": "passed",
  "duration_seconds": 4.12,
  "checkpoints_count": 2,
  "total_issues": 0,
  "a11y_score": 98.5,
  "reports": {
    "html": "reports/fluxo_login_report.html",
    "json": "reports/fluxo_login_report.json",
    "markdown": "reports/fluxo_login_report.md"
  },
  "issues": []
}
```

---

### 4.4. `inspect_url`
Auditoria ad-hoc rápida em qualquer URL ativa (local ou remota), executando validação WCAG 2.2 AA (Axe-Core) e heurísticas estruturais de UX sem exigir arquivos YAML prévios.

* **Parâmetros:**
  - `url` *(string, obrigatório)*: URL da aplicação (deve iniciar com `http://` ou `https://`).
  - `viewport` *(string, opcional, padrão `"desktop"`)*: Resolução para teste (`"desktop"`, `"mobile"`, etc.).
  - `check_a11y` *(boolean, opcional, padrão `true`)*: Ativa verificação completa com Axe-Core.
  - `check_visual` *(boolean, opcional, padrão `true`)*: Executa heurísticas de integridade visual no DOM.

* **Exemplo de Retorno:**
```json
{
  "url": "http://localhost:3000",
  "viewport": "desktop (1280x800)",
  "a11y_score": 92.0,
  "a11y_violations_count": 1,
  "a11y_violations": [
    {
      "id": "color-contrast",
      "impact": "serious",
      "description": "Elements must have sufficient color contrast",
      "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast"
    }
  ],
  "visual_issues_count": 0,
  "status": "issues_found"
}
```

---

### 4.5. `get_last_report`
Recupera o resultado mais recente gerado pelo motor do UXSentinel no workspace.

* **Parâmetros:**
  - `format` *(string, opcional)*: Formato de saída:
    - `"summary"` *(padrão)*: Resumo executivo textual com métricas, status e contadores de severidade.
    - `"markdown"`: Relatório formatado com tabelas em Markdown.
    - `"json"`: Objeto JSON integral com todos os dados da execução.

---

## 5. Recursos Compartilhados (Resources)

Além de invocar ferramentas ativas, agentes compatíveis com MCP podem ler dados de contexto diretamente via recursos padronizados:

| URI do Recurso | Tipo MIME | Descrição |
| :--- | :--- | :--- |
| `uxsentinel://scenarios` | `application/json` | Catálogo completo com todos os cenários YAML registrados no projeto. |
| `uxsentinel://reports/latest` | `application/json` | Dados brutos do último relatório de teste gerado pelo sistema. |

---

## 6. Exemplos Práticos de Interação com a IA

Depois de conectar o UXSentinel MCP na sua IDE ou chat, você pode interagir em linguagem natural:

### 💬 Exemplo 1: Descobrir e Validar Cenários
> **Você:** *"Quais cenários de teste temos para a área de autenticação?"*  
> **IA (chamando `list_scenarios`):** Localiza e apresenta `scenarios/login.yaml` e suas tags.

### 💬 Exemplo 2: Auditoria Rápida de URL
> **Você:** *"Faça uma inspeção rápida na minha página local http://localhost:8080 simulando um celular e veja se há problemas de acessibilidade."*  
> **IA (chamando `inspect_url` com `viewport: "mobile"`):** Retorna o score de acessibilidade, problemas de contraste e botões sem label.

### 💬 Exemplo 3: Executar Teste e Resumir
> **Você:** *"Rode o cenário de checkout e me mostre se houve alguma quebra visual."*  
> **IA (chamando `run_scenario`):** Executa o cenário com Playwright, analisa checkpoints e reporta as discrepâncias visuais encontradas.

---

## 7. Arquitetura e Boas Práticas (Isolamento de Stdio)

```
┌────────────────────────┐                  ┌────────────────────────┐
│     Cliente MCP        │   JSON-RPC 2.0   │   Servidor UXSentinel  │
│ (Cursor, Claude, etc.) │ ───────────────> │       (server.py)      │
│                        │      stdin       │                        │
│                        │ <─────────────── │                        │
│                        │      stdout      │                        │
└────────────────────────┘                  └────────────────────────┘
                                                         │
                                               Logs/Prints espúrios
                                                         ▼
                                                    sys.stderr
```

- **Pureza do Canal `stdout`:** Conforme as especificações de protocolo do MCP, qualquer dado que não seja uma mensagem JSON-RPC válida corrompe a comunicação. O UXSentinel redireciona automaticamente o `sys.stdout` para `sys.stderr` durante todo o ciclo de vida do servidor, garantindo 100% de estabilidade e tolerância a falhas.
- **Tratamento Hermético:** As ferramentas MCP funcionam de forma isolada, capturando exceções internas e retornando respostas com `isError=True` estruturadas em vez de quebrar o processo do servidor.

---

## 8. Troubleshooting e Diagnóstico

### 1. O cliente MCP acusa "Connection closed" ou "Invalid JSON"
- Verifique se você está executando comandos que imprimem saídas no console antes de iniciar o loop JSON-RPC.
- Certifique-se de que o interpretador Python apontado na configuração possui todas as dependências instaladas (`playwright`, `pydantic`, `pyyaml`).

### 2. Navegador não abre durante `run_scenario`
- O padrão da ferramenta via MCP é `headless=true` para não interferir na área de trabalho do usuário. Se desejar ver o navegador, instrua o agente: *"Execute com headless false"*.

### 3. Testando o servidor manualmente no terminal
Você pode verificar a saúde do servidor enviando uma mensagem de inicialização JSON-RPC:

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "manual-test", "version": "1.0"}}}' | uxsentinel mcp
```

A resposta esperada no terminal deve ser:
```json
{"id":1,"jsonrpc":"2.0","result":{"capabilities":{"resources":{},"tools":{}},"protocolVersion":"2024-11-05","serverInfo":{"name":"uxsentinel","version":"1.1.10"}}}
```

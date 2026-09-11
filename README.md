# UXSentinel 🛡️👁️
### Agente Universal de QA Visual, Auditoria de UX e Proteção de Regras de Negócio

O **UXSentinel** é um agente autônomo e inteligente projetado para auditar **qualquer aplicação web** (Odoo, React, Vue, Angular, Django, SaaS e portais corporativos). Ele opera abrindo o navegador em **modo visível na sua tela**, navegando como um usuário humano rigoroso com velocidade cadenciada e inspecionando visualmente cada tela com **Modelos Multimodais de IA (Visão Computacional)**.

---

## 🌟 Principais Recursos

- **Acompanhamento Visual ao Vivo (Human-in-the-Loop)**: O navegador abre na sua tela (`headless: false`) com ritmo humano (`slow_mo`) e efeitos visuais animados (cursor virtual e halo luminoso no elemento clicado ou focado).
- **Universalidade Real com Perfis de Framework**:
  - Perfil **`generic`**: Opera sobre qualquer aplicação web baseada em HTML5 padrão.
  - Perfil **`odoo`**: Especializado em ecossistemas Odoo (versões 16 a 19 e OWL Framework), com sincronização inteligente com o loader `.o_loading`, detecção de modais `.o_dialog` e captura de erros silenciosos.
- **Navegação Declarativa em YAML**: Escreva cenários de teste e proteja regras de negócio críticas sem precisar programar em código Playwright complexo.
- **Auditoria Rigorosa por IA (Validação Reversa e Ceticismo Metódico)**:
  - 🌐 **Internacionalização (i18n)**: Detecta botões, mensagens, abas e labels em inglês em telas brasileiras.
  - 🚫 **Vazamento Técnico**: Identifica identificadores de banco em `snake_case` (ex: `user_id`, `created_at`), IDs crus, prefixos de framework (`x_studio_`) e stacktraces.
  - 📐 **Geometria de Modais**: Avalia centralização, botões de ação cortados no rodapé e quebras de viewport.
  - 📋 **Regras de Negócio**: Compara o comportamento esperado descrito no teste com o que está sendo exibido na tela.
  - ♿ **Ergonomia e Anti-Patterns**: Alerta sobre contrastes deficientes (WCAG 4.5:1), sobreposições e botões sem rótulos.
- **Inteligência Artificial Flexível**: Alternância transparente via `config/config.yaml` entre:
  - **APIs Cloud**: Anthropic Claude, OpenAI GPT-4o, Google Gemini.
  - **Modelos Locais (On-Premise)**: Ollama com Qwen2-VL ou LLaVA (privacidade total sem envio para nuvens externas).
  - **Gateways Corporativos com SSO**: Proxies com tokens corporativos e headers customizados.
- **Relatórios Visuais Ricos**: Gera um dashboard HTML moderno e responsivo com screenshots em alta resolução, badges de severidade e sugestões acionáveis de correção.
- **Padrão PyPI & PEPs**: Estruturado conforme PEP 517/518/621 no `pyproject.toml`, utilizando Python 3.12 nativo e formatado via Ruff.

---

## 📋 Requisitos do Sistema

- **Sistema Operacional**: Linux, macOS ou Windows.
- **Python**: Versão **3.12 ou superior** (com ambiente virtual dedicado).
- **Navegadores**: Chromium (gerenciado automaticamente pelo Playwright).

---

## 🚀 Instalação Passo a Passo

O projeto utiliza o ambiente virtual configurado na pasta **`ambiente/`**:

### 1. Clonar e Acessar o Repositório
```bash
git clone <url-do-repositorio> UXSentinel
cd UXSentinel
```

### 2. Criar e Ativar o Ambiente Virtual (Python 3.12)
Caso a pasta `ambiente/` ainda não exista:
```bash
python3.12 -m venv ambiente
```

Ative o ambiente (ou execute os binários diretamente via `ambiente/bin/python3`):
```bash
source ambiente/bin/activate
# No Windows: ambiente\Scripts\activate
```

### 3. Instalar as Dependências do Projeto
```bash
ambiente/bin/pip install -r requirements.txt
ambiente/bin/pip install -e .
```

### 4. Instalar o Navegador Chromium do Playwright
```bash
ambiente/bin/playwright install chromium
```

---

## ⚙️ Configuração

### 1. Arquivo Global de Configuração (`config/config.yaml`)
Copie o modelo de exemplo para criar a sua configuração local:
```bash
cp config/config.example.yaml config/config.yaml
```

No `config/config.yaml`, você pode definir o provedor de IA ativo, opções de viewport e delay visual:
```yaml
# Provedor ativo: anthropic_cloud, openai_cloud, gemini_cloud, ollama_local ou corporate_gateway
active_provider: "anthropic_cloud"
fallback_provider: "ollama_local"

browser:
  headless: false              # 'false' para acompanhar o browser abrindo na tela
  slow_mo_ms: 350              # Delay em milissegundos entre passos (ritmo humano)
  viewport:
    width: 1440
    height: 900
  highlight_clicks: true       # Efeito visual no ponto do clique

reporting:
  output_dir: "report"
  generate_html: true
  generate_json: true
```

### 2. Variáveis de Ambiente (`.env`)
Crie um arquivo `.env` na raiz do projeto com as chaves do provedor que desejar utilizar:
```env
# Provedores Cloud (opcional, dependendo de qual você ativar)
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...

# Aplicação Alvo de Teste (opcional)
APP_BASE_URL=https://meu-ambiente-de-teste.com
QA_BASE_URL=http://localhost:8069
QA_USER=admin
QA_PASSWORD=senha_segura
```

> [!TIP]
> **Privacidade Total com Ollama**: Se você configurar `active_provider: "ollama_local"`, nenhuma chave de API externa é necessária! O agente fará a inferência visual 100% no seu hardware local usando modelos como `qwen2-vl:7b`.

---

## 🕹️ Como Usar

Você pode executar o agente via `ambiente/bin/python3 main.py` ou diretamente através do comando de pacote `ambiente/bin/uxsentinel`.

### 🏢 Executando o UXSentinel a Partir de Qualquer Projeto Cliente
O UXSentinel foi projetado para **analisar aplicações a partir da própria pasta do projeto alvo** (por exemplo, na pasta de módulos do Odoo da Gotryx, ou no repositório de um portal React/Django):

1. **Disponibilização do comando global (`uxsentinel`)**:
   Ao instalar o pacote no sistema ou ambiente com `pip install -e .`, o comando binário `uxsentinel` é criado. Com `~/.local/bin` no seu `$PATH`, você pode chamá-lo globalmente de qualquer diretório:
   ```bash
   # Link simbólico para uso global rápido:
   ln -sf /mnt/home/alexandre/Projetos/UXSentinel/ambiente/bin/uxsentinel ~/.local/bin/uxsentinel
   ```

2. **Coloque os cenários dentro do projeto cliente**:
   Crie uma pasta `scenarios/` na raiz do projeto alvo (ex: `/caminho/meu-projeto/scenarios/fluxo_vendas.yaml`).

3. **Execute o comando diretamente de dentro da pasta do projeto alvo**:
   ```bash
   cd /caminho/do/meu-projeto

   # Auto-detecta os cenários da pasta scenarios/ local:
   uxsentinel

   # Ou especifique um cenário específico daquele projeto:
   uxsentinel --scenario scenarios/fluxo_vendas.yaml --slowmo 400
   ```

4. **Isolamento de Credenciais e Relatórios**:
   - O UXSentinel lê o `.env` local presente na pasta do projeto cliente (carregando URLs, logins e tokens daquele projeto).
   - O dashboard visual e as capturas são salvos automaticamente dentro da pasta `report/` do próprio projeto cliente!

---

### 1. Listar os Cenários Disponíveis
Exibe os cenários do projeto local onde você está e os cenários da biblioteca interna:
```bash
ambiente/bin/uxsentinel --list-scenarios
```

### 2. Executar um Cenário no Navegador Visível (Padrão)
A janela do Chromium se abrirá na tela e você acompanhará cada ação:
```bash
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml
```

### 3. Executar Cenário Especializado para Odoo
Aguardando estabilização do loader `.o_loading` e modais OWL:
```bash
ambiente/bin/uxsentinel --scenario scenarios/cenario_odoo.yaml --profile odoo
```

### 4. Ajustar a Velocidade do Acompanhamento Visual (`--slowmo`)
Para apresentações ou auditorias minuciosas, aumente o delay (ex: 500ms):
```bash
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml --slowmo 500
```

### 5. Alternar o Provedor de IA via Linha de Comando
Substitua o provedor na hora da execução sem mexer no arquivo de configuração:
```bash
# Usar OpenAI GPT-4o
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml --provider openai_cloud

# Usar Google Gemini 1.5
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml --provider gemini_cloud

# Usar inferência local com Ollama (100% privado)
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml --provider ollama_local
```

### 6. Executar em Background / Modo Headless (Esteiras CI/CD)
```bash
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml --headless
```

---

## 📝 Como Criar um Novo Cenário de Teste (YAML)

Crie um arquivo `.yaml` dentro de `uxsentinel/scenarios/library/meu_fluxo.yaml`:

```yaml
version: "1.0"
id: "emissao_fatura_cliente"
title: "Fluxo de Emissão de Fatura e Verificação de Modal"
profile: "generic"    # 'generic' ou 'odoo'
tags: ["financeiro", "faturamento"]

env:
  base_url: "${APP_BASE_URL:-http://localhost:8000}"

steps:
  - action: "goto"
    url: "${base_url}/invoices/new"
    description: "Navega para a tela de nova fatura"

  - action: "fill"
    selector: "input#cliente_nome"
    value: "Empresa de Demonstração Ltda"
    description: "Informa o cliente"

  - action: "click"
    selector: "button#btn-emitir"
    description: "Clica para emitir"

  - action: "wait_modal"
    timeout: 8000
    description: "Aguarda abertura do modal de confirmação"

  # Checkpoint onde o agente para, fotografa e audita com IA
  - action: "checkpoint"
    name: "modal_confirmacao_emissao"
    description: "Auditoria do modal de confirmação de fatura"
    expected_behavior: >
      O modal de confirmação deve abrir centralizado, sem sobreposição de campos.
      O valor total da fatura e os botões 'Confirmar Envio' e 'Cancelar' devem estar
      visíveis no rodapé. Nenhum texto em inglês deve ser exibido.
```

### Ações Suportadas no Roteiro:
- `goto`: Navega até a URL especificada.
- `click`: Clica em um seletor CSS com efeito luminoso.
- `fill`: Preenche texto em um input ou textarea.
- `select`: Seleciona opção em listas dropdown (`<select>`).
- `press`: Dispara tecla física (ex: `Enter`, `Escape`, `Tab`).
- `hover`: Passa o mouse sobre um elemento para abrir tooltips ou menus.
- `scroll`: Rola a página (`direction: "down"` ou `"up"`).
- `wait_until_ready`: Aguarda o término de requisições ativas e loaders.
- `wait_modal`: Aguarda a renderização de diálogos/modais.
- `wait_modal_close`: Aguarda o fechamento completo do modal.
- `pause`: Pausa temporária em segundos para visualização.
- `checkpoint`: Ponto de inspeção visual, captura de tela e julgamento pela IA.

---

## 📊 Relatórios de Execução

Ao término de cada execução, os resultados são salvos no diretório configurado (`report/`):

1. **Dashboard Visual HTML (`report/<id>_report.html`)**:
   - Página interativa e independente com galeria de capturas de tela.
   - Detalhamento de cada checkpoint com descrição do comportamento esperado.
   - Lista categorizada de inconformidades visuais com badges de severidade (**Bloqueante**, **Alta**, **Média**, **Baixa**).
   - Recomendações acionáveis de correção para o time de desenvolvimento.
2. **Relatório Estruturado JSON (`report/<id>_report.json`)**:
   - Contém métricas brutas, timestamps, contagem de falhas e logs para fácil integração com esteiras de CI/CD (GitHub Actions, GitLab CI, Jenkins).
3. **Screenshots em Alta Resolução (`report/<id>_<checkpoint>.png`)**:
   - Imagens completas capturadas no momento exato de cada checkpoint.

---

## 🛡️ Qualidade de Código, PEPs e Linter Ruff

O projeto segue estritamente as convenções das **PEPs do Python 3.12** e utiliza o **Ruff** com configuração dedicada no arquivo [`ruff.toml`](ruff.toml):

```bash
# Verificar regras de linting (PEP 8, isort, pyupgrade, bugbear)
ambiente/bin/ruff check .

# Aplicar correções automáticas
ambiente/bin/ruff check --fix .

# Aplicar formatação de código no padrão PEP 8
ambiente/bin/ruff format .

# Validar se o código já está perfeitamente formatado
ambiente/bin/ruff format --check .
```

---

## 🧪 Executar Testes Internos do Motor

Para validar todos os componentes (configurações, parsers, geradores de relatórios e Playwright) com o interpretador do venv:

```bash
ambiente/bin/python3 tests/test_engine.py
```

---

## 📚 Documentação Técnica Completa

Para aprofundar na arquitetura e especificações do projeto, consulte a pasta [`docs/`](docs/README.md):

| Documento | Assunto |
| :--- | :--- |
| 📖 [**01. Visão Geral e Arquitetura Universal**](docs/01_visao_e_arquitetura.md) | Arquitetura em camadas, fluxo de orquestração e neutralidade de frameworks. |
| 🔍 [**02. Heurísticas Universais de QA e UX**](docs/02_heuristicas_de_inspecao.md) | Critérios de i18n, prevenção de jargões técnicos, geometria de modais e severidades. |
| 🕹️ [**03. Motor do Agente: Navegação e Visão**](docs/03_agente_navegador_e_visao.md) | Modo visível, highlights em tela, estabilização assíncrona e loop de IA. |
| 📝 [**04. Especificação de Cenários (YAML)**](docs/04_especificacao_cenarios_yaml.md) | Sintaxe dos arquivos de teste e definição de checkpoints de regras de negócio. |
| 🤖 [**05. Configuração de LLMs e Provedores**](docs/05_configuracao_llm_e_provedores.md) | Especificação do `config.yaml` para alternar entre Cloud, Local (Ollama) e SSO/Gateway. |
| 🔌 [**06. Perfis e Plugins de Frameworks**](docs/06_plugins_e_perfis_frameworks.md) | Detalhes do perfil universal e do plugin especializado para Odoo (OWL). |
| 🤖 [**Skill do Projeto (.gemini/skills)**](.gemini/skills/uxsentinel-guide/SKILL.md) | Skill interna para agentes de IA atuarem com máxima consistência no repositório. |

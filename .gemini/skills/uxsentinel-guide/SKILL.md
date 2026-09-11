---
name: uxsentinel-guide
description: Diretrizes de arquitetura, desenvolvimento, criação de cenários YAML e comandos operacionais do agente universal de QA visual e UX UXSentinel (Python 3.12).
---

# UXSentinel - Guia Operacional e Arquitetural do Projeto

Esta skill define as convenções, arquitetura, padrões de código e comandos operacionais para atuar no projeto **UXSentinel**. Sempre que você atuar neste repositório, siga rigorosamente as diretrizes abaixo.

---

## 🎯 1. Visão do Projeto e Proposta de Valor

O **UXSentinel** é um agente autônomo inteligente de **QA Visual, Auditoria de UX e Proteção de Regras de Negócio** para aplicações web.
- **Universal com Perfis de Framework**: Atua em qualquer aplicação web (`generic`), contando com perfis especializados para ecossistemas complexos como o **Odoo** (espera do loader `.o_loading`, modais `.o_dialog`, componentes OWL e captura de notificações de erro).
- **Acompanhamento Visual ao Vivo (Human-in-the-Loop)**: O navegador abre na tela do operador (`headless: false`) com velocidade cadenciada ajustável (`slow_mo`) e destaques visuais animados injetados no DOM (cursor virtual e halo luminoso no elemento clicado/focado).
- **Navegação Híbrida**: Roteiros determinísticos em YAML para proteger regras de negócio e modo autônomo com IA exploratória.
- **Camada Unificada de LLM Multimodal**: Suporte a APIs Cloud (Anthropic, OpenAI, Gemini), Modelos Locais via Ollama/vLLM (privacidade total sem envio para a nuvem) e Gateways Corporativos/SSO com fallback automático.

---

## 🐍 2. Padrões de Código e Ambiente Obrigatório

1. **Python 3.12 Nativo**:
   - Utilize sempre a sintaxe moderna do Python 3.12: `str | None` (nunca `Optional[str]`), `list[...]`, `dict[...]` e f-strings limpas.
   - Validações de dados devem utilizar **Pydantic v2** (`BaseModel`, `Field`).
2. **Ambiente Virtual Local Estrito**:
   - **SEMPRE** utilize o Python do ambiente virtual local em:
     ```bash
     ambiente/bin/python3
     ```
   - Instalação e atualização de pacotes:
     ```bash
     ambiente/bin/pip install -r requirements.txt
     ambiente/bin/pip install -e .
     ```
   - Instalação dos navegadores Playwright:
     ```bash
     ambiente/bin/playwright install chromium
     ```

3. **Padrão de Gerenciador de Pacotes PyPI e PEPs**:
   - O projeto segue o padrão canônico do ecossistema PyPI via `pyproject.toml` (especificações PEP 517, PEP 518 e PEP 621).
   - Metadados formais (`name`, `version`, `requires-python = ">=3.12"`, `authors`, `classifiers`, `keywords`, `project.scripts`).
   - Normas Técnicas PEPs:
     - **PEP 8**: Estilo de código e formatação.
     - **PEP 257**: Convenções de docstrings.
     - **PEP 435 / PEP 667**: Uso nativo de `enum.StrEnum` para enums de texto.
     - **PEP 604**: Type union nativo com `X | Y` (eliminando `typing.Union` e `typing.Optional`).

4. **Revisão Obrigatória de Lint e Formatação com Ruff**:
   - As regras de lint e formatação estão configuradas no arquivo dedicado [`ruff.toml`](file:///mnt/home/alexandre/Projetos/UXSentinel/ruff.toml) na raiz do projeto.
   - Todo código adicionado ou modificado DEVE obrigatoriamente ser verificado e formatado pelo **Ruff**:
     ```bash
     # Verificar regras de linting (PEP 8, isort, pyupgrade, bugbear)
     ambiente/bin/ruff check .

     # Aplicar correções automáticas
     ambiente/bin/ruff check --fix .

     # Aplicar formatação automática no padrão PEP 8
     ambiente/bin/ruff format .
     ```
   - **Gate de Qualidade**: Nunca finalize uma tarefa ou commit sem garantir que `ambiente/bin/ruff check .` retorne com zero erros.

---

## 🏗️ 3. Estrutura Modular da Base de Código

```
UXSentinel/
├── config/
│   ├── config.yaml                       # Configuração ativa de IA e browser
│   └── config.example.yaml               # Modelo de referência
├── docs/                                 # Documentação técnica e especificações
│   ├── README.md                         # Índice mestre
│   ├── 01_visao_e_arquitetura.md         # Arquitetura universal
│   ├── 02_heuristicas_de_inspecao.md     # Heurísticas de QA/UX e severidades
│   ├── 03_agente_navegador_e_visao.md    # Motor de navegação e visual overlays
│   ├── 04_especificacao_cenarios_yaml.md # Gramática dos cenários YAML
│   ├── 05_configuracao_llm_e_provedores.md # Suporte Cloud, Local e SSO
│   └── 06_plugins_e_perfis_frameworks.md # Perfis generic e Odoo
├── uxsentinel/
│   ├── core/
│   │   ├── config.py                     # Parser pydantic do config.yaml e variáveis .env
│   │   ├── models.py                     # Dataclasses/Pydantic (Issue, Checkpoint, TestReport)
│   │   └── agent.py                      # Orquestrador do agente e loop de execução
│   ├── browser/
│   │   ├── session.py                    # Gerenciador da sessão do Playwright
│   │   ├── visual_overlay.py             # Script JS injetado para ripple e highlight
│   │   └── drivers/
│   │       ├── base_driver.py            # Interface abstrata do driver
│   │       ├── generic_driver.py         # Driver para web apps padrão
│   │       └── odoo_driver.py            # Driver especializado para Odoo / OWL
│   ├── vision/
│   │   ├── prompts.py                    # Prompts estruturados para auditoria QA
│   │   ├── client.py                     # Cliente HTTP assíncrono para LLMs com fallback
│   │   └── inspector.py                  # Processamento de screenshots e parser de issues
│   ├── scenarios/
│   │   ├── parser.py                     # Leitor e validador de cenários YAML com interpolação
│   │   └── library/                      # Biblioteca de cenários prontos (.yaml)
│   └── reporter/
│       ├── html_builder.py               # Dashboard visual HTML interativo
│       └── json_builder.py               # Relatório estruturado JSON
├── main.py                               # CLI executável
├── tests/
│   └── test_engine.py                    # Testes de integração de componentes
└── report/                               # Diretório padrão de saída de relatórios e screenshots
```

---

## 🔍 4. Heurísticas de Auditoria de QA e UX

Ao inspecionar uma tela em um `checkpoint`, o modelo de visão avalia rigorosamente:

1. **Internacionalização (i18n)**:
   - Toda a interface deve estar em **Português do Brasil (PT-BR)**.
   - Termos em inglês como *"Save"*, *"Submit"*, *"Discard"*, *"Filter"*, *"Back to top"* são reportados como inconformidades.
2. **Vazamento Técnico e Jargões**:
   - Proibição de nomes de banco de dados em `snake_case` (ex: `user_id`, `created_at`, `client_tax_id`).
   - Proibição de prefixos de framework (ex: `x_studio_` no Odoo).
   - Proibição de números crus de IDs sem contexto, stacktraces ou erros 500 expostos na interface.
3. **Geometria de Modais e Diálogos**:
   - Centralização na viewport e ausência de barra de rolagem horizontal.
   - Botões de ação do rodapé (*Confirmar*, *Cancelar*) devem estar visíveis sem exigir rolagem forçada.
   - O backdrop deve isolar o fundo e impedir cliques vazados.
4. **Regras de Negócio e Estados**:
   - Valida se os campos obrigatórios estão indicados visualmente e se o comportamento na tela bate com o `expected_behavior` declarado.
5. **Matriz de Severidade**:
   - **`bloqueante`**: Impede o usuário de concluir a ação ou causa crash/tela branca.
   - **`alta`**: Violação de regra de negócio, permissão ou perda de dados.
   - **`media`**: Termo não traduzido, nome técnico visível ou desalinhamento considerável.
   - **`baixa`**: Detalhe cosmético leve ou ajuste fino de espaçamento/contraste.

---

## 📝 5. Como Criar Cenários de Teste em YAML

Os cenários de teste devem ser armazenados **dentro da pasta do projeto alvo que está sendo analisado** (por exemplo, no repositório de módulos da Gotryx ou em qualquer app web cliente em `scenarios/<nome>.yaml`).
*(O UXSentinel também mantém cenários de referência na sua biblioteca interna em `uxsentinel/scenarios/library/<nome>.yaml`).*

```yaml
version: "1.0"
id: "meu_cenario"
title: "Título Legível do Teste"
profile: "generic"    # 'generic' para web comum ou 'odoo' para Odoo
tags: ["smoke", "cadastro"]

env:
  base_url: "${APP_BASE_URL:-http://localhost:8000}"

steps:
  - action: "goto"
    url: "${base_url}/login"
    description: "Acessa a tela de login"

  - action: "fill"
    selector: "input#username"
    value: "admin"

  - action: "click"
    selector: "button[type='submit']"

  - action: "wait_until_ready"

  - action: "checkpoint"
    name: "pos_login_dashboard"
    expected_behavior: >
      O usuário deve visualizar a tela principal sem erros, com menus em português
      e layout responsivo alinhado.
```

### Ações Disponíveis:
- `goto`: Navega até a URL especificada.
- `click`: Clica no elemento com efeito luminoso visual.
- `fill`: Digita valor em um input/textarea.
- `select`: Seleciona opção em lista `<select>`.
- `press`: Dispara tecla (ex: `Enter`, `Escape`).
- `hover`: Passa o mouse para testar tooltips e menus suspensos.
- `scroll`: Rola a tela (`direction: "down"` ou `"up"`).
- `wait_until_ready`: Aguarda loaders e rede estabilizarem.
- `wait_modal`: Aguarda abertura e animação de diálogo/modal.
- `wait_modal_close`: Aguarda o fechamento do modal e remoção de backdrop.
- `pause`: Pausa temporária em segundos para visualização ao vivo.
- `checkpoint`: Ponto de captura de screenshot e inspeção multimodal com IA.

---

## 🚀 6. Comandos Operacionais
 
### 🏢 Execução a Partir do Projeto Alvo (Ex: Módulos Odoo Gotryx):
```bash
# 1. Certifique-se de que o symlink global ~/.local/bin/uxsentinel está ativo:
ln -sf /mnt/home/alexandre/Projetos/UXSentinel/ambiente/bin/uxsentinel ~/.local/bin/uxsentinel

# 2. Navegue até a pasta do projeto cliente que deseja analisar:
cd /caminho/do/projeto/cliente

# 3. Execute o UXSentinel diretamente (ele detecta automaticamente os cenários em ./scenarios/):
uxsentinel

# 4. Ou execute especificando o cenário e ritmo de slow motion:
uxsentinel --scenario scenarios/meu_modulo.yaml --slowmo 500
```
*(O relatório HTML e screenshots serão salvos em `./report` da própria pasta do projeto cliente!)*

### Listar cenários disponíveis (no projeto local e biblioteca interna):
```bash
ambiente/bin/uxsentinel --list-scenarios
```

### Executar cenário no navegador visível (ritmo humano padrão 350ms):
```bash
ambiente/bin/uxsentinel --scenario scenarios/meu_cenario.yaml
```

### Executar cenário para Odoo com slow motion de 500ms:
```bash
ambiente/bin/uxsentinel --scenario scenarios/cenario_odoo.yaml --profile odoo --slowmo 500
```

### Alternar provedor de IA via CLI:
```bash
ambiente/bin/python3 main.py --scenario uxsentinel/scenarios/library/exemplo_web_geral.yaml --provider gemini_cloud
# ou openai_cloud, anthropic_cloud, ollama_local, corporate_gateway
```

### Executar em modo headless (para esteiras de CI/CD):
```bash
ambiente/bin/python3 main.py --scenario uxsentinel/scenarios/library/exemplo_web_geral.yaml --headless
```

### Executar bateria de testes de validação interna:
```bash
ambiente/bin/python3 tests/test_engine.py
```

---

## 📊 7. Relatórios Gerados

Ao término de qualquer execução, consulte a pasta `report/`:
- **`report/<id>_report.html`**: Dashboard interativo com galeria de screenshots, filtros de severidade e sugestões de correção para os desenvolvedores.
- **`report/<id>_report.json`**: Dados estruturados para pipelines e automações.
- **`report/<id>_<checkpoint>.png`**: Capturas em resolução nativa de cada checkpoint.

---

## 📚 8. Referências Técnicas Recomendadas

Sempre que a IA for atuar no aprimoramento de recursos, design de novos cenários ou expansão das heurísticas de inspeção, consulte as seguintes referências:

### 8.1 Documentação Técnica Interna do Projeto
* 📐 **Arquitetura Universal**: [01_visao_e_arquitetura.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/01_visao_e_arquitetura.md) — Camadas, desacoplamento e neutralidade de frameworks.
* 🔍 **Heurísticas de QA e UX**: [02_heuristicas_de_inspecao.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/02_heuristicas_de_inspecao.md) — Matriz de severidade, i18n, jargões técnicos e ergonomia de modais.
* 🕹️ **Motor do Agente e Navegação**: [03_agente_navegador_e_visao.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/03_agente_navegador_e_visao.md) — Detalhes do Playwright visível, delays e overlays de clique.
* 📝 **Padrão de Cenários YAML**: [04_especificacao_cenarios_yaml.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/04_especificacao_cenarios_yaml.md) — Dicionário de ações e escrita de regras de negócio.
* 🤖 **Configuração de LLMs**: [05_configuracao_llm_e_provedores.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/05_configuracao_llm_e_provedores.md) — Suporte a APIs Cloud, Ollama Local e SSO corporativo.
* 🔌 **Perfis de Framework**: [06_plugins_e_perfis_frameworks.md](file:///mnt/home/alexandre/Projetos/UXSentinel/docs/06_plugins_e_perfis_frameworks.md) — Perfil genérico e adaptador Odoo OWL.
* ⚙️ **Configuração Global**: [config.example.yaml](file:///mnt/home/alexandre/Projetos/UXSentinel/config/config.example.yaml) — Modelo de parâmetros operacionais.

### 8.2 Skills Globais Complementares (Ecossistema ~/.gemini)
* 👁️ **Validação Visual Rigorosa**: [`ui-visual-validator`](file:///mnt/home/alexandre/.gemini/config/skills/ui-visual-validator/SKILL.md)  
  *Use para*: Princípios de validação reversa (*"assumir defeito até provar o contrário"*), checagem de alinhamento e precisão visual em prompts de IA.
* 🎨 **Diretrizes Avançadas de UX e Usabilidade**: [`ui-ux-pro-max`](file:///mnt/home/alexandre/.gemini/config/skills/ui-ux-pro-max/SKILL.md)  
  *Use para*: Catálogo com mais de 99 regras de UX, anti-patterns de interface, touch targets (44x44px), contraste de cores e recomendações acionáveis de correção.
* 🎭 **Automação Web com Playwright em Python**: [`webapp-testing`](file:///mnt/home/alexandre/.gemini/config/skills/webapp-testing/SKILL.md)  
  *Use para*: Padrões de scripts nativos em Python, padrão *Reconnaissance-Then-Action* (inspecionar antes de interagir) e gestão de servidores locais.
* ♿ **Auditoria de Acessibilidade W3C**: [`wcag-audit-patterns`](file:///mnt/home/alexandre/.gemini/config/skills/wcag-audit-patterns/SKILL.md)  
  *Use para*: Expandir os checkpoints para conformidade com as diretrizes WCAG 2.2 (contraste, foco de teclado e rótulos acessíveis).
* ⚙️ **Especialista em Frontend Odoo 19 / OWL**: [`odoo-frontend-ux-expert`](file:///mnt/home/alexandre/.gemini/config/skills/odoo-frontend-ux-expert/SKILL.md)  
  *Use para*: Aprimoramento do `OdooDriver` com conhecimentos aprofundados sobre componentes OWL 2.0, classes de views QWeb e navbar do Odoo.
* 🌐 **Diretrizes Globais de Design Web**: [`web-design-guidelines`](file:///mnt/home/alexandre/.gemini/config/skills/web-design-guidelines/SKILL.md)  
  *Use para*: Revisão de conformidade de telas com padrões modernos de design para navegadores desktop e mobile.

---

## 🐙 9. Capacidade de Commits e Pushes no Git do Projeto

O agente de IA está **autorizado e capacitado** a gerenciar o ciclo de versionamento Git do repositório **UXSentinel**, realizando commits atômicos e pushes para o repositório remoto.

### 9.1 Protocolo Obrigatório Pré-Commit (Quality Gate Estrito)
Antes de executar qualquer commit ou push, a IA **DEVE obrigatoriamente** rodar a tríade de validação abaixo com o ambiente virtual local e garantir aprovação de 100%:

```bash
# 1. Auditoria estática de regras (PEP 8, isort, bugs) - ZERO erros tolerados:
ambiente/bin/ruff check .

# 2. Verificação de formatação consistente:
ambiente/bin/ruff format --check .

# 3. Execução dos testes de integração de componentes:
ambiente/bin/python3 tests/test_engine.py
```
> [!CAUTION]
> **Bloqueio de Qualidade**: Se qualquer um dos comandos acima falhar, o commit **NÃO PODE** ser realizado até que o problema seja corrigido e revalidado.

### 9.2 Padrão de Mensagens de Commit (Conventional Commits em Português)
As mensagens de commit devem seguir o padrão canônico com descrição clara em português do Brasil:
- `feat(<escopo>)`: Nova funcionalidade adicionada ao motor, novos drivers ou recursos CLI.
- `fix(<escopo>)`: Correção de bug, seletor de modal, timeout ou parser.
- `docs(<escopo>)`: Atualização ou criação de documentação, READMEs ou skills.
- `test(<escopo>)`: Adição ou melhoria de cenários de teste e suites de integração.
- `refactor(<escopo>)`: Refatoração estrutural de código sem alteração funcional.
- `chore(<escopo>)`: Atualização de dependências, `.gitignore` ou configurações de build/linter.

*Exemplos:*
- `feat(cli): adiciona auto-descoberta de cenarios em projetos externos`
- `fix(driver): ajusta sincronizacao com loader .o_loading do odoo`
- `docs(skill): documenta fluxo de trabalho git e qualidade com ruff`

### 9.3 Fluxo Canônico de Comandos Git
```bash
# 1. Inspecione os arquivos modificados
git status

# 2. Adicione os arquivos relevantes ao stage
git add <arquivos>

# 3. Crie o commit semântico estruturado
git commit -m "tipo(escopo): descricao clara em portugues"

# 4. Envie as alterações para a branch remota
git push origin <branch_atual>
```

### 9.4 Guardrails de Segurança para Git
- **Nunca comitar segredos**: Arquivos `.env`, chaves de API (`ANTHROPIC_API_KEY`, etc.) e tokens nunca devem ser comitados.
- **Relatórios Locais Isolados**: O diretório `report/` deve permanecer estritamente no `.gitignore` para evitar envio de imagens de teste e logs locais para o repositório remoto.



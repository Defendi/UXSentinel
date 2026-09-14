# 10. Estado Atual do Desenvolvimento, Inventário e Registro de Riscos

> **Data de Atualização:** 14 de Setembro de 2026  
> **Status do Repositório:** Estável / Produção v0.1.0+  
> **Ambiente de Testes:** 100% verde (`uv run pytest` — 12 testes aprovados)

Este documento foi concebido em atendimento às recomendações levantadas na [Análise da Memória Compactada (Doc 09)](09_analise_memoria_compactada.md). Seu objetivo é estabelecer um **retrato fiel, auditável e sem ambiguidades** do estado de engenharia do UXSentinel, distinguindo rigorosamente o que já está compilado e testado no código do que reside como planejamento nas Fases do Roadmap.

---

## 1. Mapeamento Fiel da Estrutura de Código

Abaixo está a arquitetura real implementada no pacote Python `uxsentinel/`:

```
uxsentinel/
├── __init__.py                  # Versão do pacote (__version__)
├── cli.py                       # CLI principal via argparse + Rich (interface de terminal)
├── assets/                      # Recursos visuais estáticos (logos e templates padrão)
├── browser/                     # Camada de automação de navegador via Playwright
│   ├── session.py               # BrowserSession (ciclo de vida, headless/headed, gravação de screenshots)
│   ├── visual_overlay.py        # Injeção JS de cursor simulado e halos visuais de clique
│   └── drivers/                 # Especialização por framework web
│       ├── base_driver.py       # BaseFrameworkDriver (contrato abstrato de estabilização)
│       ├── generic_driver.py    # GenericDriver (SPAs convencionais, React, Vue, Angular)
│       └── odoo_driver.py       # OdooDriver (tratamento de .o_loading, diálogos OWL e ActionManager)
├── core/                        # Núcleo de domínio e orquestração
│   ├── agent.py                 # UXSentinelAgent (execução de cenários, checkpoints e agregação)
│   ├── config.py                # Modelos Pydantic de configuração (~/.config/uxsentinel/config.yaml)
│   ├── models.py                # Entidades: Inconsistency, Checkpoint, ExecutionResult, Severity
│   └── sso.py                   # Autenticação interativa via browser e cache seguro de tokens SSO
├── integrations/                # Conectores com serviços corporativos
│   ├── __init__.py
│   └── jira.py                  # JiraClient (criação automática de issues via REST API Jira Cloud v3)
├── reporter/                    # Geração de saídas e artefatos de auditoria
│   ├── html_builder.py          # Relatório HTML interativo autocontido com anotações visuais
│   ├── json_builder.py          # Serialização estruturada dos resultados da inspeção
│   └── prompt_builder.py        # Geração de prompts Markdown prontos para correção por agentes LLM
├── scenarios/                   # Mecanismo de cenários declarativos
│   ├── parser.py                # Validação e parser de arquivos YAML de cenários
│   └── library/                 # Cenários pré-construídos para testes de sanidade
└── vision/                      # Inteligência visual multimodal (LMM)
    ├── client.py                # UnifiedVisionClient (OpenAI, Anthropic Claude, Google Gemini, Ollama, DeepSeek)
    ├── inspector.py             # VisionInspector (recorte de telas, OCR semântico e chamadas de visão)
    └── prompts.py               # Engenharia de prompts com Heurísticas de Nielsen, ISO 9241-11 e WCAG 2.2
```

---

## 2. Inventário de Funcionalidades: Concluído vs. Pendente

Para eliminar qualquer divergência entre o "estado desejado" e o "estado real", a tabela a seguir mapeia cada capacidade do produto, indicando seu status de implementação no código e a respectiva tarefa no Jira (quando aplicável):

| Funcionalidade | Componente Técnico | Status Real | Card Jira | Notas de Implementação |
| :--- | :--- | :---: | :---: | :--- |
| **Navegação com visual humano** | `uxsentinel.browser.session` | **Concluído** | — | Suporte a `slow_mo_ms`, cursor visual e highlights injetados na tela. |
| **Execução de cenários YAML** | `uxsentinel.scenarios.parser` | **Concluído** | — | Ações `goto`, `click`, `fill`, `wait`, `checkpoint` totalmente operacionais. |
| **Integração Multiprovedor LMM** | `uxsentinel.vision.client` | **Concluído** | — | OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet), Gemini 1.5, DeepSeek e Ollama local. |
| **Suporte a SSO de IA Corporativo** | `uxsentinel.core.sso` | **Concluído** | — | Login interativo no browser com `--login-sso` e persistência de sessão. |
| **Diagnóstico de Conectividade IA** | `uxsentinel.cli` | **Concluído** | — | Flag `--check-ai` com fallback automático de modelos. |
| **Geração de Prompt de Correção** | `uxsentinel.reporter.prompt_builder` | **Concluído** | — | Flag `--fix-prompt` gera Markdown detalhado para agentes (Cursor, Claude Code). |
| **Abertura Automática de Cards no Jira** | `uxsentinel.integrations.jira` | **Concluído** | — | Flag `--jira` cria issues com severidade, steps e screenshots anexados. |
| **Configurador Interativo Jira CLI** | `uxsentinel.cli` | **Concluído** | — | Flag `--set-jira-token` com validação de conexão e gravação protegida (0600). |
| **Diretório Global de Configuração** | `uxsentinel.core.config` | **Concluído** | — | Padrão XDG em `~/.config/uxsentinel/config.yaml` gerado via `--init-config`. |
| **Suíte de Testes Hermética** | `tests/test_engine.py` | **Concluído** | — | 12/12 testes passando sem mocks frágeis ou dependências externas (`uv run pytest`). |
| **Self-Healing de Seletores** | `uxsentinel.browser` | *Pendente* | `UXS-1` | Fase 1 do Roadmap (Prioridade: Highest). |
| **Gravação de Vídeo e GIF de Sessão** | `uxsentinel.browser.session` | *Pendente* | `UXS-2` | Fase 1 do Roadmap (Prioridade: High). |
| **Auditoria Multi-Viewport** | `uxsentinel.browser` | *Pendente* | `UXS-3` | Desktop, Tablet, Mobile em paralelo. Fase 1 (Prioridade: High). |
| **Controle Headed/Headless na CLI** | `uxsentinel.cli` | *Parcial* | `UXS-4` | Flag `--headless` existe; falta aprimorar flags complementares `--headed`/`--no-gui`. |
| **Arquitetura Mixture of Evaluators (>95%)** | `uxsentinel.vision` | *Pendente* | `UXS-5` | 4 subagentes especializados com contexto focado. Fase 2 (Prioridade: Highest). |
| **Árbitro Reverso & Anti-Alucinação** | `uxsentinel.vision` | *Pendente* | `UXS-6` | Devil's Advocate e validação cruzada para zero falsos positivos. Fase 2 (Prioridade: Highest). |
| **Baseline Visual com Slider Antes/Depois**| `uxsentinel.reporter` | *Pendente* | `UXS-7` | Regressão visual perceptual com delta visual. Fase 2 (Prioridade: Medium). |
| **Motor Axe-Core Integrado** | `uxsentinel.browser` | *Pendente* | `UXS-8` | Auditoria determinística WCAG 2.2 via injeção JS de axe.min.js. Fase 2 (Prioridade: Medium). |
| **Ações Semânticas `ai_action`** | `uxsentinel.scenarios` | *Pendente* | `UXS-9` | Passos no YAML em linguagem natural resolvidos por visão. Fase 2 (Prioridade: Medium). |
| **UXSentinel Studio (Live Mission Control)**| Novo módulo `studio/` | *Pendente* | `UXS-10` | Frontend Web com visualização e controle em tempo real. Fase 4 (Prioridade: High). |
| **YAML Studio com IA Assistente** | Novo módulo `studio/` | *Pendente* | `UXS-11` | Interface visual para criação e teste de YAMLs com IA. Fase 4 (Prioridade: Medium). |
| **Modo Exploratório Autônomo (`--crawl`)** | `uxsentinel.engine` | *Pendente* | `UXS-12` | Descoberta autônoma de fluxos e páginas. Fase 3 (Prioridade: Low). |
| **Auto-PR no GitHub (`--create-pr`)** | `uxsentinel.integrations` | *Pendente* | `UXS-13` | Abertura automática de PR com patch de correção de CSS/HTML. Fase 3 (Prioridade: Low). |
| **Painel Histórico de Qualidade (Hub)** | `uxsentinel.reporter` | *Pendente* | `UXS-14` | Banco local SQLite de tendências de regressão. Fase 3 (Prioridade: Low). |

---

## 3. Matriz e Registro de Riscos (Técnicos e de Produto)

A gestão proativa de riscos assegura a estabilidade do agente em ambientes corporativos e esteiras de CI/CD:

| ID | Categoria | Descrição do Risco | Impacto | Probabilidade | Estratégia de Mitigação |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **R-01** | **Técnico / IA** | **Alucinação do LMM:** Apontar problemas inexistentes ou ignorar defeitos evidentes em layouts complexos. | **Crítico** | Média | Implementar o *Mixture of Evaluators* (`UXS-5`) com *Árbitro Reverso* (`UXS-6`), exigindo evidência em coordenadas e validação por consenso. |
| **R-02** | **Operacional** | **Vazamento de Credenciais:** Persistência indevida de tokens do Jira ou chaves LLM em logs ou commits. | **Alto** | Baixa | Armazenamento restrito a `~/.config/uxsentinel/config.yaml` com permissão estrita `0600`, exclusão via `.gitignore` e suporte a variáveis de ambiente `${VAR}`. |
| **R-03** | **Performance** | **Custo e Latência de LMM:** Alto tempo de resposta e consumo excessivo de tokens durante inspeção de muitas telas. | **Alto** | Alta | Cache de screenshots não alterados (hashing de imagem), suporte a modelos locais (Ollama/vLLM) e execução seletiva de checkpoints. |
| **R-04** | **Automação** | **Flakiness em SPAs Dinâmicas:** Seletores quebram ou páginas demoram para hidratar (React, Vue, Odoo). | **Médio** | Média | Especialização de drivers (`OdooDriver` com checagem de `.o_loading`) e implementação do *Self-Healing* (`UXS-1`) guiado por acessibilidade e visão. |
| **R-05** | **Integração** | **Incompatibilidade de Versões do Playwright:** Diferença de binários do Chromium entre ambientes de desenvolvimento e CI Linux. | **Médio** | Baixa | Travamento de versões via `uv.lock` e Dockerfile hermético com instalação controlada de dependências de sistema (`playwright install --with-deps`). |

---

## 4. Registro de Decisões de Arquitetura (ADRs Implementadas e Descartadas)

### 4.1 Decisões Implementadas

1. **ADR-01: Configuração Global em Diretório XDG do Usuário (`~/.config/uxsentinel/`)**
   - *Contexto:* Inicialmente, configurações ficavam restritas ao diretório do projeto ou exigiam permissão de escrita local.
   - *Decisão:* Adotar `~/.config/uxsentinel/config.yaml` com fallback para variáveis de ambiente e arquivos locais.
   - *Consequência:* Usuários podem rodar o UXSentinel em qualquer repositório sem necessidade de reconfigurar chaves ou exigir privilégios `sudo`.

2. **ADR-02: Isolamento Hermético dos Testes Automatizados**
   - *Contexto:* Testes de engine falhavam se o desenvolvedor tivesse uma sessão expirada de Claude Code salva no sistema operacional.
   - *Decisão:* Isolar totalmente a busca de credenciais em `tests/test_engine.py` através de *mocking* seguro no nível da chamada de configuração.
   - *Consequência:* Execução reproduzível com 100% de sucesso em qualquer máquina (`uv run pytest`), viabilizando esteiras de CI sem falsos negativos.

3. **ADR-03: Conexão REST Nativa com Atlassian Jira Cloud**
   - *Contexto:* Necessidade de transformar achados de inspeção visual em ações concretas no fluxo do time de engenharia.
   - *Decisão:* Implementar cliente REST nativo (`JiraClient`) com autenticação via Basic Auth (e-mail + API Token), payload estruturado em Atlassian Document Format (ADF) e suporte a anexo de screenshots.
   - *Consequência:* Automação ponta a ponta: inspeção visual $\rightarrow$ geração de issue categorizada no Jira com severidade mapeada.

### 4.2 Decisões Descartadas / Rejeitadas

1. **DESC-01: Dependência Exclusiva de Modelos Proprietários em Nuvem (OpenAI / Anthropic)**
   - *Motivo do Descarte:* Empresas com requisitos rígidos de conformidade (LGPD, sigilo bancário) não podem enviar screenshots de sistemas internos para APIs externas.
   - *Alternativa Adotada:* Arquitetura agnóstica via `UnifiedVisionClient`, permitindo uso de modelos locais (Ollama, vLLM) e gateways privados corporativos com autenticação SSO.

2. **DESC-02: Interface Baseada Apenas em Headless Silencioso**
   - *Motivo do Descarte:* Ferramentas tradicionais de QA falham em gerar confiança no time porque os testes rodam em "caixas pretas" sem rastreabilidade visual do que o robô está fazendo.
   - *Alternativa Adotada:* Modo visual humano como cidadão de primeira classe (`headless=False`, `slow_mo`, cursor animado e anotações na tela), tornando o modo `headless` uma opção para esteiras headless de CI/CD.

3. **DESC-03: Execução de Inspeção por Heurística em Única Chamada LLM Genérica**
   - *Motivo do Descarte:* Apresentou taxa de assertividade inferior a 70% em testes empíricos de mercado, gerando falsos positivos sobre cores e textos contextuais.
   - *Alternativa Adotada:* Planejamento do *Mixture of Evaluators* (`UXS-5`), onde subagentes independentes avaliam eixos isolados e um árbitro reverso filtra inconsistências.

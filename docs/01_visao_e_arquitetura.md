<p align="center">
  <img src="../images/logo_completa.png" alt="UXSentinel Logo" width="450"/>
</p>

# UXSentinel: Visão Geral e Arquitetura Universal

O **UXSentinel** é um agente autônomo e inteligente de **Garantia de Qualidade Visual (QA) e Auditoria de Experiência do Usuário (UX)**, projetado para operar em **qualquer aplicação web moderna** (ecossistemas Odoo, React, Vue, Angular, Next.js, Django, portais corporativos e SaaS em geral).

---

## 1. Missão e Proposta de Valor

A maioria dos testes automatizados de software (testes unitários, testes de integração ou suites E2E rígidas) verifica se um endpoint retornou status 200 ou se um elemento HTML existe na árvore do DOM. No entanto, eles são **cegos para a experiência humana real**.

Um sistema pode passar com 100% de sucesso em testes tradicionais e ainda assim:
- Apresentar janelas modais cortadas ou sobrepostas que impedem o clique em botões vitais.
- Deixar textos em inglês em uma interface voltada a usuários brasileiros.
- Expor termos técnicos do banco de dados, nomes de colunas ou stacktraces de erro.
- Apresentar botões de confirmação fora da viewport ou escondidos atrás da barra de rolagem.
- Violar regras de negócio sutis que apenas uma inspeção cognitiva humana perceberia.

O **UXSentinel** resolve essa lacuna atuando como um **Auditor de QA Humano Digital**: ele abre o navegador visualmente na tela, executa jornadas de usuário, analisa cada cena com modelos multimodais de visão computacional e relata problemas com base em regras de negócio e boas práticas de UX.

---

## 2. Arquitetura em Camadas

O sistema adota uma arquitetura limpa, desacoplada e orientada a extensibilidade:

```mermaid
graph TD
    subgraph Entrada e Configuração
        CLI[UXSentinel CLI] --> ConfigEngine[Config Engine / config.yaml]
        CLI --> ScenarioParser[Scenario Loader / YAML]
        ConfigEngine --> LLMRegistry[LLM Registry (Cloud / Local / SSO)]
    end

    subgraph Agente Central
        ScenarioParser --> Orchestrator[UXSentinel Orchestrator]
        Orchestrator --> ModeRouter{Modo de Execução}
        ModeRouter -->|Roteirizado| ScriptedEngine[Scripted Playbook Engine]
        ModeRouter -->|Autônomo| AutonomousEngine[Autonomous Exploration Agent]
    end

    subgraph Camada de Automação Visual (Browser)
        ScriptedEngine --> ProfileSelector[Driver Profile Selector]
        AutonomousEngine --> ProfileSelector
        ProfileSelector --> GenericProfile[Generic Web Profile]
        ProfileSelector --> OdooProfile[Odoo Framework Profile]
        ProfileSelector --> CustomProfile[Custom SPA Profile]
        GenericProfile --> PlaywrightCore[Playwright Engine (Visível + SlowMo + Cursor)]
        OdooProfile --> PlaywrightCore
        CustomProfile --> PlaywrightCore
    end

    subgraph Camada Cognitiva e Relatórios
        PlaywrightCore --> ScreenObserver[Screen & DOM Observer]
        ScreenObserver --> LLMRegistry
        LLMRegistry --> VisionAuditor[Vision & UX Auditor]
        VisionAuditor --> ReportEngine[Report Engine]
        ReportEngine --> HTMLDashboard[Dashboard HTML Interativo]
        ReportEngine --> JSONSummary[Relatório Estruturado JSON]
end
```

---

## 3. Pilares Fundamentais

### 3.1 Acompanhamento Visual em Tempo Real (Human-in-the-Loop)
Ao contrário de robôs de CI/CD que rodam silenciosamente em background (*headless*), o UXSentinel prioriza a **observabilidade humana**:
- O navegador gráfico se abre na tela do operador (`headless=False`).
- Um ritmo natural de interação (`slow_mo` configurável de 300ms a 600ms) garante que a equipe veja a transição de telas.
- Um cursor virtual desenhado na página e halos luminosos destacam visualmente exatamente onde o agente está clicando ou preenchendo dados.

### 3.2 Navegação Híbrida
1. **Modo Roteirizado (Scripted YAML)**: Execução determinística de fluxos de regras de negócio definidos em arquivos YAML fáceis de ler, com checkpoints de inspeção visual.
2. **Modo Autônomo Exploratório (Autonomous QA Agent)**: O agente recebe uma URL de entrada e uma meta em linguagem natural (ex: *"Teste a jornada de checkout e avalie o tratamento de dados inválidos"*), explorando e tomando decisões com base no que visualiza.

### 3.3 Neutralidade de Aplicação com Perfis de Framework
O núcleo da ferramenta opera exclusivamente com padrões web universais (HTML5, CSS, WAI-ARIA, canvas visual). Caso a aplicação alvo utilize frameworks com comportamentos específicos (como o loader `.o_loading` e componentes OWL do Odoo), ativa-se o **Perfil Especializado**, garantindo tolerância a esperas assíncronas sem poluir o núcleo genérico.

### 3.4 Gerenciamento Unificado de LLM Multimodal
Total liberdade para alternar o "cérebro" de visão através do arquivo `config.yaml`:
- **APIs Cloud**: Claude (Anthropic), GPT-4o (OpenAI), Gemini (Google).
- **Modelos Locais**: Ollama / vLLM (Qwen2-VL, LLaVA) para ambientes air-gapped ou privacidade total de dados.
- **SSO / Enterprise Gateways**: Proxies corporativos com autenticação Bearer ou headers proprietários.

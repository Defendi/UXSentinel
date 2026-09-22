<p align="center">
  <img src="../images/logo_completa.png" alt="UXSentinel Logo" width="500"/>
</p>

# Documentação Técnica e de Contexto — UXSentinel

Bem-vindo à central de documentação e engenharia do **UXSentinel**, o agente inteligente universal de QA visual, inspeção de UX e validação de regras de negócio para aplicações web (Odoo, React, Vue, Angular, Django, SaaS e portais corporativos).

---

## 📚 Índice da Documentação

Os documentos abaixo fornecem o embasamento teórico, técnico e operacional do projeto:

1. **[01. Visão Geral e Arquitetura Universal](01_visao_e_arquitetura.md)**  
   Conheça a proposta de valor, a arquitetura em camadas, a neutralidade de frameworks e a orquestração entre Playwright (Navegador com acompanhamento visual ao vivo), Visão Computacional e Motores de Relatório.

2. **[02. Heurísticas Universais de Inspeção de QA e UX](02_heuristicas_de_inspecao.md)**  
   Catálogo completo de heurísticas de auditoria visual: internacionalização (i18n), prevenção de vazamento de jargões técnicos e nomes de banco (`snake_case`), ergonomia e geometria de modais, integridade de regras de negócio e matriz de severidade (Bloqueante, Alta, Média, Baixa).

3. **[03. Motor do Agente: Navegação Visual e Inspeção Cognitiva](03_agente_navegador_e_visao.md)**  
   Como o agente opera em modo visual humano (`headless=False`, `slow_mo`, cursor animado e highlights de clique na tela), inspeção ao vivo via DevTools/Console acoplado (`--devtools`), telemetria de performance W3C (TTFB, Dom Interactive, Page Load), captura de erros de JavaScript e rede, e execução de ações semânticas.

4. **[04. Especificação Declarativa de Cenários (YAML)](04_especificacao_cenarios_yaml.md)**  
   Manual e gramática para escrita de cenários e fluxos de teste em arquivos YAML, dicionário de ações suportadas (`goto`, `click`, `fill`, `wait_modal`, `ai_click`, `ai_assert`, etc.) e definição de checkpoints com regras de negócio em português.

5. **[05. Configuração Unificada de Modelos de Linguagem e Visão (LLMs)](05_configuracao_llm_e_provedores.md)**  
   Arquitetura de conexão agnóstica para inteligência artificial via `config/config.yaml`. Suporte aos três pilares: **APIs Cloud** (Anthropic Claude, OpenAI GPT-4o, Google Gemini), **Modelos Locais** (Ollama, vLLM, Qwen2-VL) e **Gateways Corporativos / SSO** com tokens e cabeçalhos customizados.

6. **[06. Perfis e Plugins de Frameworks](06_plugins_e_perfis_frameworks.md)**  
   Como a arquitetura extensível adapta o agente a ecossistemas específicos: perfil universal `generic`, perfil especializado `odoo` (tratamento de `.o_loading`, diálogos OWL e ActionManager) e perfis para SPAs modernas.

7. **[07. Guia de Criação de Releases e Publicação no PyPI](07_guia_de_publicacao_e_releases.md)**  
   Procedimento passo a passo para criar novas releases no GitHub (via CLI `gh` ou interface web) e acionar a esteira de CI/CD automatizada com validação e deploy no PyPI.

8. **[08. Roadmap de Melhorias e Evolução Técnica](08_roadmap_melhorias_e_evolucao.md)**  
   Plano diretor de evolução inspirado nas melhores ferramentas de QA com IA do mercado: *Self-Healing* de seletores, gravação de vídeos/GIFs, auditoria multi-viewport, arquitetura multiagente com árbitro reverso, baseline visual, motor Axe-Core WCAG 2.2, modo crawler exploratório e **UXSentinel Studio** (interface gráfica web desacoplada em pacote próprio `uxsentinel-studio` via UV Workspace).

9. **[10. Estado Atual do Desenvolvimento, Inventário e Registro de Riscos](10_estado_atual_inventario_e_riscos.md)**  
   Retrato fiel e operacional do código: mapeamento exato dos pacotes Python, inventário de funcionalidades concluídas vs. pendentes vinculado aos cards do Jira (`UXS-1` a `UXS-47`), matriz de riscos e registro de decisões de arquitetura (ADRs).

10. **[Especificações de Design Arquitetural (Specs)](superpowers/specs/)**  
    Documentos formais de decisão e detalhamento técnico de engenharia:
    - **[`2026-09-21-backend-refactoring-design.md`](superpowers/specs/2026-09-21-backend-refactoring-design.md)**: Desacoplamento do motor de passos (`ActionContext`, `ActionRegistry`) e `ScenarioRunnerService`.
    - **[`2026-09-22-uxsentinel-studio-design.md`](superpowers/specs/2026-09-22-uxsentinel-studio-design.md)**: Arquitetura completa do **UXSentinel Studio**, modelo de 2 pacotes PyPI independentes via UV Workspace, API REST e SPA Vue 3.

---

## 🎯 Pilares Estratégicos do UXSentinel

- **Acompanhamento Visual ao Vivo & DevTools**: O agente navega com o navegador visível na tela em velocidade humanizada, com suporte a DevTools/Console acoplado e telemetria de rede e performance W3C.
- **Universalidade Real**: Funciona com qualquer interface web, com adaptadores opcionais para frameworks complexos.
- **Relatórios Duplos Ricos**: Gera relatórios visuais interativos em HTML e relatórios estruturados em Markdown (.md) específicos para os editores MarkText e Obsidian.
- **Liberdade de Provedores de IA**: Alternância fluida entre APIs proprietárias na nuvem, inferência 100% local com Ollama ou gateways corporativos com SSO.
- **Decisões Baseadas em Regras de Negócio**: Não é apenas um detector de quebras de layout, mas um validador cognitivo que confronta a tela com o que foi especificado para o fluxo.

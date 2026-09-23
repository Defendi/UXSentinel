# 🛡️ Diretrizes Operacionais e Regras Mandatórias do Projeto (AGENTS.md)

Este documento estabelece as regras mandatórias que TODOS os agentes de IA, subagentes e desenvolvedores DEVEM seguir rigorosamente no repositório **UXSentinel**.

---

## 🚦 0. Ciclo de Vida Mandatório de Toda Tarefa

> [!CAUTION]
>
> ### REGRA INEGOCIÁVEL: TODA TAREFA SEGUE 5 FASES DISTINTAS, CADA UMA COM GATE DE AUTORIZAÇÃO HUMANA
>
> Toda e qualquer tarefa (feature, bugfix, refatoração, melhoria ou release) deve obrigatoriamente passar pelas **5 fases abaixo, nesta ordem exata**. O agente **NÃO DEVE avançar para a próxima fase sem autorização explícita por escrito do usuário**, exceto quando o usuário indicar expressamente que determinada fase deve ser executada sem necessidade de aprovação.

---

### Fase 1 — 📋 Especificação

> [!IMPORTANT]
> **Bloqueada até: autorização do usuário para iniciar a implementação.**

- Criar (ou atualizar) o card no Jira projeto `UXS` com título, descrição do problema/objetivo e contexto.
- Documentar no card todas as **características**, **comportamentos esperados**, **restrições técnicas** e **critérios de aceitação**.
- Apresentar o card ao usuário com um resumo claro das specs.
- ✋ **PARAR e aguardar aprovação** antes de qualquer ação de implementação.
- 🚫 É **proibido** ler arquivos com intenção de implementar, escrever código, delegar a subagentes de implementação ou executar qualquer ação técnica antes da aprovação desta fase.

---

### Fase 2 — 🛠️ Implementação

> [!IMPORTANT]
> **Bloqueada até: autorização do usuário para iniciar os testes.**

- Somente iniciar após aprovação da Fase 1.
- Toda implementação deve ser executada por **subagentes especializados** (nunca diretamente pelo agente principal).
- Seguir rigorosamente as specs aprovadas no card Jira.
- Ao concluir, apresentar ao usuário o resumo das alterações realizadas.
- ✋ **PARAR e aguardar aprovação** antes de executar a bateria de testes.

---

### Fase 3 — 🧪 Testes

> [!IMPORTANT]
> **Bloqueada até: autorização do usuário para publicar.**

- Somente iniciar após aprovação da Fase 2.
- Executar **100% da bateria de testes**: `ambiente/bin/pytest tests studio/tests`.
- Executar a **tríade de qualidade**: `ruff check .` e `ruff format --check .` sem erros.
- Todos os testes devem ser **100% herméticos** (sem chamadas a redes externas reais ou credenciais de produção).
- Exibir claramente ao usuário o sumário completo dos resultados.
- ✋ **PARAR e aguardar aprovação** antes de publicar qualquer versão.

---

### Fase 4 — 🚀 Publicação

> [!IMPORTANT]
> **Bloqueada até: autorização do usuário para finalizar.**

- Somente iniciar após aprovação da Fase 3.
- É **terminantemente proibido** de forma autônoma:
  - Alterar versão em `pyproject.toml` ou `uxsentinel/__init__.py`;
  - Criar tags Git de versão (`git tag vX.Y.Z`);
  - Criar ou publicar Releases no GitHub;
  - Publicar ou disparar deploys para o PyPI.
- Executar: bump de versão → commit semântico → tag git → push → release GitHub → pipeline PyPI.
- ✋ **PARAR e aguardar aprovação** antes de finalizar o card.

---

### Fase 5 — ✅ Finalização

> [!IMPORTANT]
> **Bloqueada até: autorização do usuário.**

- Somente iniciar após aprovação da Fase 4.
- Atualizar o card Jira com o status final, versão publicada e links da release.
- Atualizar o `UXSentinel_Studio_Manual_do_Usuario.pdf` se houver mudanças de funcionalidade ou interface.
- Fazer commit e push final de qualquer documentação pendente.
- Fechar o card no Jira.

---



## 🛑 1. Gate Mandatório de Nova Versão e Deploy

> [!CAUTION]
> 
> ### REGRA INEGOCIÁVEL: SOMENTE GERAR VERSÃO NOVA APÓS TESTES E APROVAÇÃO DO USUÁRIO
> 
> É **terminantemente proibido** realizar qualquer uma das seguintes ações de forma autônoma:
> 
> - Alterar a versão em `pyproject.toml` ou `uxsentinel/__init__.py`;
> - Criar tags Git de versão (`git tag vX.Y.Z`);
> - Criar ou publicar Releases no GitHub (`gh release create`);
> - Publicar ou disparar deploys para o PyPI.
> - Executar implementações no código diretamente, sempre use subagentes.

> **Fluxo Estrito Pré-Release:**
> 
> 1. ✅ **Implementação Concluída**: Toda a funcionalidade e seus testes unitários herméticos devem estar prontos.
> 2. 🧪 **Bateria Completa de Testes**: Executar `uv run pytest` e obter **100% de testes aprovados**.
> 3. 🧹 **Tríade de Qualidade e Linter**: Executar `uv run ruff check .` e `uv run ruff format --check .` sem nenhum erro.
> 4. 📢 **Apresentação de Resultados**: Exibir claramente ao usuário o sumário de testes e o que foi realizado.
> 5. ✋ **Gate de Aprovação Humana**: **Perguntar ao usuário e aguardar autorização expressa** para avançar com a geração de versão e deploy.
> 6. 🚀 **Execução do Deploy**: Somente após a confirmação por escrito do usuário, efetuar o bump de versão, commit semântico, tag git e disparo da release.
> 7. 🚀 **Jira**: Toda documentação das tarefas devem ser feitas nos cards no Jira no espaço "UXSentinel Tarefas". Mantenha os cards organizados por épico + tarefa/bug mais importante. Sempre execute um card por vez, nunca execute cards em lote. Antes de qualquer ação, verifique se o MCP do Jira está autenticado; caso contrário, bloqueie a execução e avise o usuário imediatamente.

---

## 🇧🇷 2. Idioma e Comunicação

> [!IMPORTANT]
> 
> - Toda comunicação com o usuário, documentação, mensagens de commit, artefatos e respostas devem ser entregues **estritamente em Português do Brasil**.

---

## 🛡️ 3. Escopo Exclusivo e Projetos Circunstanciais

> [!IMPORTANT]
> 
> - **Foco Estrito no UXSentinel**: Neste espaço de trabalho, a atuação do agente trata **exclusivamente** do produto **UXSentinel** (sua arquitetura, funcionalidades, código, testes e evolução).
> - **Outros Projetos são Circunstanciais**: Quaisquer outros repositórios, sistemas ou aplicações externas (como Gotryx, módulos Odoo, APIs ou frontends de clientes) são **estritamente circunstanciais**. Eles atuam unicamente como alvos de teste, casos de uso externos ou cenários temporários de auditoria.
> - **Isolamento de Operações de Repositório**: Verificações de repositório (`git status`, `git diff`, commits, branches, releases, auditoria de arquivos) devem se concentrar primariamente no **UXSentinel**. Não desvie o escopo do projeto para gerenciar outros repositórios, exceto sob solicitação expressa do usuário.
> - **Neutralidade e Desacoplamento**: O UXSentinel é um agente autônomo e universal de Visual QA, neutro em relação a frameworks (React, Vue, Angular, Odoo, Django, etc.). Não introduza dependências de negócio nem acople o projeto a regras de outros sistemas sem solicitação expressa do usuário.

---

## 🧪 4. Hermeticidade dos Testes

- Todos os testes em `tests/` devem ser **100% herméticos**, rápidos e isolados (sem chamadas a redes externas reais ou credenciais de produção).

---

## 🎯 5. Skill Oficial do Projeto e Proibição Expressa

> [!IMPORTANT]
> 
> - A skill oficial, exclusiva e mandatória para qualquer tarefa técnica ou operacional neste repositório é **`UXSentinel/.gemini/skills/uxsentinel-guide`** ([`uxsentinel-guide`](file:///mnt/home/alexandre/Projetos/UXSentinel/.gemini/skills/uxsentinel-guide/SKILL.md)).
> - **PROIBIÇÃO EXPRESSA**: É **terminantemente proibido** utilizar, carregar, consultar ou fazer qualquer menção à skill `gotryx-project` ou a regras do ecossistema Gotryx no repositório **UXSentinel**.
> - O **UXSentinel** é um projeto de código aberto, universal, neutro e totalmente desacoplado de projetos específicos de clientes.

---

## 🎫 6. Conexão Obrigatória com o MCP do Jira (Atlassian)

> [!CAUTION]
> 
> ### REGRA MANDATÓRIA: VALIDAÇÃO PRÉVIA DA CONEXÃO COM O MCP DO JIRA
> 
> - **Verificação Prévia Obrigatória**: Antes de iniciar qualquer tarefa, planejamento ou execução de código no repositório, o agente DEVE obrigatoriamente checar a conexão e autenticação com o **servidor MCP do Jira (Atlassian)**.
> - **Bloqueio Total por Falha de Conexão**: Se o MCP do Jira não estiver autenticado ou falhar na inicialização/chamada, **NADA DEVE SER FEITO NO REPOSITÓRIO**.
> - **Aviso Imediato ao Usuário**: O agente deve interromper o fluxo imediatamente e avisar o usuário que o MCP do Jira não está autenticado, solicitando que a autenticação seja reestabelecida antes de prosseguir com qualquer trabalho.

---

## 📄 7. Manual do Usuário e Padronização da Qualidade do Studio

> [!IMPORTANT]
> 
> ### REGRA MANDATÓRIA: MANTER O MANUAL DO STUDIO SEMPRE ATUALIZADO NA RAIZ
> 
> - **Localização Obrigatória:** O manual oficial do usuário deve residir **obrigatoriamente na pasta principal (raiz do projeto)** sob o nome `UXSentinel_Studio_Manual_do_Usuario.pdf`.
> - **Atualização Obrigatória Pré-Release:** Sempre que novas funcionalidades, telas, opções de configuração, novos endpoints, regras de conformidade ou alterações arquiteturais forem implementadas no **UXSentinel Studio**, o manual em PDF DEVE ser obrigatoriamente atualizado e recompilado antes da conclusão dos cards ou de qualquer ciclo de release.
> - **Fidelidade ao Padrão de Qualidade:** O documento deve preservar rigorosamente a linguagem acessível para leigos e cobrir os três blocos fundamentais:
>   1. **Especificações Técnicas:** Dados de desempenho, consumo, portas de loopback, segurança e dimensões multi-viewport;
>   2. **Critérios de Aceitação:** Matriz de severidade de defeitos (bloqueante, alta, média, baixa) e termômetro de saúde (score ring);
>   3. **Instruções de Uso Passo a Passo:** Manuseio prático de cada componente da interface e do assistente de IA.



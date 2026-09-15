# 🛡️ Diretrizes Operacionais e Regras Mandatórias do Projeto (AGENTS.md)

Este documento estabelece as regras mandatórias que TODOS os agentes de IA, subagentes e desenvolvedores DEVEM seguir rigorosamente no repositório **UXSentinel**.

---

## 🛑 1. Gate Mandatório de Nova Versão e Deploy

> [!CAUTION]
> ### REGRA INEGOCIÁVEL: SOMENTE GERAR VERSÃO NOVA APÓS TESTES E APROVAÇÃO DO USUÁRIO
>
> É **terminantemente proibido** realizar qualquer uma das seguintes ações de forma autônoma:
> - Alterar a versão em `pyproject.toml` ou `uxsentinel/__init__.py`;
> - Criar tags Git de versão (`git tag vX.Y.Z`);
> - Criar ou publicar Releases no GitHub (`gh release create`);
> - Publicar ou disparar deploys para o PyPI.
>
> **Fluxo Estrito Pré-Release:**
> 1. ✅ **Implementação Concluída**: Toda a funcionalidade e seus testes unitários herméticos devem estar prontos.
> 2. 🧪 **Bateria Completa de Testes**: Executar `uv run pytest` e obter **100% de testes aprovados**.
> 3. 🧹 **Tríade de Qualidade e Linter**: Executar `uv run ruff check .` e `uv run ruff format --check .` sem nenhum erro.
> 4. 📢 **Apresentação de Resultados**: Exibir claramente ao usuário o sumário de testes e o que foi realizado.
> 5. ✋ **Gate de Aprovação Humana**: **Perguntar ao usuário e aguardar autorização expressa** para avançar com a geração de versão e deploy.
> 6. 🚀 **Execução do Deploy**: Somente após a confirmação por escrito do usuário, efetuar o bump de versão, commit semântico, tag git e disparo da release.

---

## 🇧🇷 2. Idioma e Comunicação

> [!IMPORTANT]
> - Toda comunicação com o usuário, documentação, mensagens de commit, artefatos e respostas devem ser entregues **estritamente em Português do Brasil**.

---

## 🛡️ 3. Escopo Exclusivo e Projetos Circunstanciais

> [!IMPORTANT]
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
> - A skill oficial, exclusiva e mandatória para qualquer tarefa técnica ou operacional neste repositório é **`UXSentinel/.gemini/skills/uxsentinel-guide`** ([`uxsentinel-guide`](file:///mnt/home/alexandre/Projetos/UXSentinel/.gemini/skills/uxsentinel-guide/SKILL.md)).
> - **PROIBIÇÃO EXPRESSA**: É **terminantemente proibido** utilizar, carregar, consultar ou fazer qualquer menção à skill `gotryx-project` ou a regras do ecossistema Gotryx no repositório **UXSentinel**.
> - O **UXSentinel** é um projeto de código aberto, universal, neutro e totalmente desacoplado de projetos específicos de clientes.

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

## 🛡️ 3. Autonomia e Neutralidade do UXSentinel

- O **UXSentinel** é um agente autônomo e universal de Visual QA, neutro em relação a frameworks (React, Vue, Angular, Odoo, Django, etc.).
- Não introduza dependências de negócio nem acople o projeto a regras de outros sistemas sem solicitação expressa do usuário.

---

## 🧪 4. Hermeticidade dos Testes

- Todos os testes em `tests/` devem ser **100% herméticos**, rápidos e isolados (sem chamadas a redes externas reais ou credenciais de produção).

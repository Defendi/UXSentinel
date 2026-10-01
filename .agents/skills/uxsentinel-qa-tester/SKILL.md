---
name: uxsentinel-qa-tester
description: Espelho compacto do checklist da Fase 3 do UXSentinel.
---

# Fase 3 — espelho de QA

> Fonte canônica: [`.agents/skills/uxsentinel-qa-tester/SKILL.md`](../../../.agents/skills/uxsentinel-qa-tester/SKILL.md). Em caso de divergência, ela prevalece.

Execute na etapa de testes herméticos e qualidade (status `Testando` no Jira). Ao obter 100% de sucesso, transicione para `Concluído` (criando novos cards em `Backlog` para sugestões); se houver apontamentos ou falhas, anote ponto a ponto em diversos comentários no card e mova para `A Fazer`, conforme [`AGENTS.md`](../../../AGENTS.md). Da raiz, execute:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests studio/tests -v
```

## Critérios mínimos

- Relate sucesso, contagens, falhas, erros, ignorados e causa raiz conhecida.
- Não use rede, produção, provedores ou serviços externos reais;empregue simulações, dublês ou fixtures.
- Não use credenciais reais ou dados sensíveis; elimine estado global e controle ordem, tempo, aleatoriedade e portas.
- Isole e limpe recursos temporários; não deixe artefatos versionáveis.
- Não prometa cobertura inexistente; percentuais exigem ferramenta configurada.

Relate resultados em Português do Brasil e consulte o [roteiro canônico](../../../.agents/skills/uxsentinel-guide/SKILL.md) sob demanda.

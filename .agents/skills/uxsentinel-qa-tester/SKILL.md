---
name: uxsentinel-qa-tester
description: Checklist compacto da Fase 3 do UXSentinel para testes autorizados, qualidade e hermeticidade.
---

# Fase 3 — testes e qualidade

Use esta skill após a implementação aprovada e somente com autorização expressa para testes. A [governança canônica](../../../AGENTS.md) prevalece.

## Tríade obrigatória

Execute da raiz:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests studio/tests -v
```

## Checklist

- Exija sucesso dos três comandos e relate contagens, falhas, erros, ignorados e causa raiz conhecida.
- Execute a suíte disponível sem inventar ou prometer cobertura ausente.
- Não declare percentual sem ferramenta configurada e execução autorizada.
- Falhas retornam à fase responsável; não ampliem escopo nem mascarem regressões.

## Hermeticidade

- Sem rede, produção, provedores ou serviços externos reais; use simulações, dublês ou fixtures locais.
- Sem credenciais reais, dados sensíveis, estado global ou dependência de ordem.
- Controle tempo, aleatoriedade e portas; limpe arquivos temporários e recursos de navegador.
- Não altere ambientes externos nem deixe artefatos versionáveis.

Relate os resultados em Português do Brasil. Consulte o [roteiro canônico](../uxsentinel-guide/SKILL.md) apenas para contexto adicional.

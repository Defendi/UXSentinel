# Agente de QA Visual (Python) — Frontend Odoo

Mesma ideia da versão Node: Playwright em modo visível navegando o
frontend Odoo como um usuário/QA, com cada tela-chave analisada pelo
Claude (texto não traduzido, texto técnico exposto, layout de modais,
aderência a regras de negócio).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate       # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Crie um `.env` na raiz do projeto:

```
ANTHROPIC_API_KEY=sk-ant-...
QA_BASE_URL=https://seu-ambiente-de-teste.exemplo.com
QA_USER=usuario_teste
QA_PASSWORD=senha_teste
```

⚠️ Use sempre um ambiente de homologação/staging com dados fictícios —
nunca rode contra produção com dados reais de segurados.

## Rodar

```bash
cd src
python run.py
```

O navegador abre visível (`headless=False`) e você acompanha cada
passo. Ao final, o relatório fica em `report/report.json`, com um
screenshot por fluxo em `report/<nome-do-fluxo>.png`.

## Como estender

Edite `src/flows.py` e adicione um dict por regra de negócio que você
quer proteger — ex: emissão de boleto, geração de PIX, cadastro via
FIPE, fluxo por cooperativa/cliente (dado o seu cenário multi-cliente).

Cada flow tem:
- `steps`: sequência determinística de ações (goto/click/fill/wait)
- `checkpoint.expected_behavior`: descrição em português do que a tela
  DEVE mostrar — é isso que o Claude usa como critério de julgamento

## Próximos passos sugeridos

- **Multi-cliente**: parametrizar `QA_BASE_URL`/credenciais por
  cooperativa e rodar a mesma suíte de flows contra cada uma (dá pra
  fazer um loop externo carregando `.env.<cliente>` por execução).
- **CI**: trocar `headless=False` por `True` e usar
  `context.tracing.start(...)` / `context.tracing.stop(path=...)` do
  Playwright para gravar trace e revisar depois com
  `playwright show-trace report/trace.zip`.
- **Regressão visual**: combinar com comparação de imagem (ex:
  `Pillow` + `imagehash`, ou `pixelmatch` via subprocess) além da
  análise semântica do Claude.
- **Paralelismo**: como é `asyncio`, dá pra rodar múltiplos `contexts`
  (um por cliente/cooperativa) concorrentemente com `asyncio.gather`.

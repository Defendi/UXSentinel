# Especificação Técnica de Design: Exportação de Eventos em JSON Lines (`--stream-events`)

- **Data:** 2026-09-23
- **Card Jira:** [UXS-27](https://mygotryx.atlassian.net/browse/UXS-27)
- **Status:** Especificado (Fase 1)
- **Classificação:** Bounded

---

## 1. Visão Geral e Motivação

Atualmente, o UXSentinel conta com um barramento interno e desacoplado de eventos (`EventBus` implementado em `uxsentinel/core/events.py`), que emite eventos estruturados durante o ciclo de vida da execução de cenários (início/fim de passos, auditorias do Axe-core, inspeções visuais da IA, checkpoints e auto-healing).

Entretanto, esteiras de CI/CD, ferramentas de observabilidade e usuários em linha de comando que precisam inspecionar o progresso da IA em tempo real ("ver o que a IA está pensando e executando") dependem hoje apenas dos logs do console ou do relatório final estático em Markdown/HTML gerado ao término do processo.

O objetivo do **UXS-27** é introduzir a capacidade de transmitir os eventos da execução para um arquivo contínuo no formato **JSON Lines** (`.jsonl`), gravado em tempo real com `flush` imediato por linha, garantindo sanitização estrita de credenciais e sem impacto na execução padrão.

---

## 2. Requisitos Funcionais e Não Funcionais

### Requisitos Funcionais
1. **Flag CLI:** Adicionar `--stream-events <arquivo.jsonl>` à interface de linha de comando (`uxsentinel`).
2. **Serialização em Tempo Real:** Cada evento (`ExecutionEvent`) emitido no barramento deve ser serializado como uma única linha JSON válida.
3. **Escrita com Flush Imediato:** O arquivo deve receber `flush()` síncrono a cada linha escrita, permitindo acompanhamento externo concorrente (ex.: `tail -f logs.jsonl` ou agentes coletores).
4. **Sanitização de Segredos:** Garantir que nenhuma credencial ou segredo (ex.: API tokens do Atlassian Jira, chaves de API de provedores de IA como Google Gemini / OpenAI, senhas e tokens Bearer) seja serializado no fluxo de eventos.
5. **Encerramento Seguro:** Garantir que o handle do arquivo seja fechado adequadamente ao término da execução do cenário ou em caso de exceção/interrupção.

### Requisitos Não Funcionais
1. **Retrocompatibilidade e Desligamento Padrão:** Na ausência da flag `--stream-events`, nenhum arquivo deve ser criado e nenhum assinante adicional deve sobrecarregar o ciclo de vida do runner.
2. **Hermeticidade dos Testes:** Todos os testes unitários devem ser 100% herméticos, rodando em milissegundos sem dependências de rede.
3. **Manutenibilidade e Tipagem Estrita:** Uso de recursos modernos do Python 3.12+ (Type Hints, Pydantic, gerenciadores de contexto).

---

## 3. Arquitetura e Componentes

### 3.1. `JsonLinesEventStreamer` (`uxsentinel/core/events.py`)

Será implementada a classe `JsonLinesEventStreamer`, atuando como assinante do `EventBus`.

```python
class JsonLinesEventStreamer:
    """Assinante do barramento de eventos que escoa eventos para um arquivo JSON Lines."""

    def __init__(self, target_path: str | Path) -> None:
        self.target_path = Path(target_path)
        self._file: TextIO | None = None

    def open(self) -> None:
        """Abre o arquivo garantindo diretórios pais."""
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.target_path, "a", encoding="utf-8")

    def handle_event(self, event: ExecutionEvent) -> None:
        """Sanitiza o evento, serializa em JSON de linha única e executa flush."""
        if not self._file or self._file.closed:
            return
        sanitized_event = sanitize_event_data(event)
        line = sanitized_event.model_dump_json()
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        """Fecha com segurança o handle do arquivo."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> "JsonLinesEventStreamer":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
```

### 3.2. Sanitização Recursiva de Segredos (`sanitize_event_data`)

Uma função utilitária pura irá sanitizar recursivamente o dicionário `data` do evento antes da serialização:
- Termos sensíveis mascarados (case-insensitive):
  `api_key`, `token`, `secret`, `password`, `authorization`, `auth`, `bearer`, `private_key`.
- Valores substituídos por: `***REDACTED***`.

### 3.3. Orquestração e Repasse na CLI (`uxsentinel/cli.py`)

1. **Adição do Argumento no Argparse:**
   ```python
   parser.add_argument(
       "--stream-events",
       type=Path,
       default=None,
       metavar="ARQUIVO",
       help="Caminho para arquivo .jsonl onde os eventos da execução serão gravados em tempo real.",
   )
   ```

2. **Propagação no `ExecutionOptions`:**
   Adicionar o campo `stream_events: Path | None = None` em `ExecutionOptions` (`uxsentinel/service/execution_service.py`), ou instanciar e gerenciar o `JsonLinesEventStreamer` e seu `EventBus` correspondente diretamente antes de invocar o `execution_service.run()`.

3. **Ciclo de Vida Limpo:**
   Garantir através de bloco `with` ou `try...finally` que o streamer feche o arquivo após a conclusão do(s) cenário(s).

---

## 4. Estrutura do JSON Lines Emitido

Cada linha do arquivo será uma representação JSON independente e completa do `ExecutionEvent`:

```json
{"event_type":"scenario_started","timestamp":"2026-09-23T19:00:00Z","scenario_id":"login_fluxo","viewport":"desktop","step_index":null,"action":null,"data":{"title":"Login Principal"}}
{"event_type":"step_started","timestamp":"2026-09-23T19:00:01Z","scenario_id":"login_fluxo","viewport":"desktop","step_index":1,"action":"fill","data":{"selector":"#usuario"}}
{"event_type":"step_completed","timestamp":"2026-09-23T19:00:02Z","scenario_id":"login_fluxo","viewport":"desktop","step_index":1,"action":"fill","data":{"duration_ms":120}}
{"event_type":"ai_inspection_completed","timestamp":"2026-09-23T19:00:03Z","scenario_id":"login_fluxo","viewport":"desktop","step_index":2,"action":"inspect","data":{"verdict":"APROVADO","observations":"Layout íntegro"}}
{"event_type":"scenario_completed","timestamp":"2026-09-23T19:00:05Z","scenario_id":"login_fluxo","viewport":"desktop","step_index":null,"action":null,"data":{"status":"PASS"}}
```

---

## 5. Critérios de Aceitação

1. **Validade do Formato:** O arquivo gerado é JSON Lines estritamente válido (cada linha é um JSON independente parseável por `json.loads`).
2. **Escrita Incremental:** Um leitor concorrente (ou `tail -f`) consegue ler linhas à medida que cada passo do cenário é finalizado.
3. **Hermeticidade da Sanitização:** Se dados sensíveis forem passados em `data` (ex.: `{"api_key": "xyz123", "nested": {"password": "pass"}}`), eles são substituídos por `***REDACTED***`.
4. **Comportamento Padrão Inerte:** Quando `--stream-events` não é passada, nenhum arquivo é criado e nenhum resíduo em disco permanece.
5. **Cobertura Hermética de Testes:** Bateria de testes unitários herméticos cobrindo todos os cenários com 100% de sucesso.
6. **Conformidade de Estilo:** `ruff check .` e `ruff format --check .` sem nenhum erro.

---

## 6. Plano de Verificação e Testes

- **`tests/test_event_streamer.py`**:
  - Teste unitário do `JsonLinesEventStreamer`: registrar no `EventBus`, emitir eventos variados e verificar linhas gravadas no arquivo temporário.
  - Teste de sanitização: verificar se chaves sensíveis e valores aninhados são mascarados como `***REDACTED***`.
  - Teste de context manager (`__enter__` e `__exit__`).
  - Teste de CLI: invocar o parser de argumentos com `--stream-events log.jsonl` e validar que o parâmetro é reconhecido.

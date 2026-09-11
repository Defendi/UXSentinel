# Perfis e Plugins de Frameworks

O **UXSentinel** foi projetado sob o princípio da **Neutralidade de Plataforma**: seu motor central interage com o navegador através do DOM padrão, eventos do W3C e visão computacional da tela renderizada.

No entanto, sistemas baseados em frameworks complexos (como Odoo, React SPAs, Angular ou Salesforce) possuem ciclos de vida específicos de carregamento e componentes proprietários. Para isso, o UXSentinel adota o padrão de **Perfis de Framework (Plugins)**.

---

## 1. O que é um Perfil de Framework?

Um Perfil é uma classe adaptadora que ensina o agente:
1. **Como saber que a aplicação terminou de carregar** (estabilização de rede e loaders de tela).
2. **Quais são os seletores padrão de modais e gavetas**.
3. **Como detectar erros nativos silenciosos** (ex: caixas de erro do framework que não quebram o HTTP).
4. **Padrões de nomes técnicos específicos do framework** a serem proibidos na interface.

---

## 2. Perfis Nativos

### 2.1 Perfil Genérico (`generic`) — O Padrão Universal
- **Aplicabilidade**: Qualquer aplicação web (HTML5, Bootstrap, Tailwind, Vue, Django, Rails, etc.).
- **Detecção de Loading**: Monitora o término de requisições de rede ativas (Fetch / XHR) com silêncio de 500ms.
- **Seletores de Modais**:
  ```css
  dialog[open], .modal.show, [role="dialog"], [aria-modal="true"], .modal-dialog
  ```
- **Fechamento de Modais**: Busca por botões com atributos `[data-dismiss="modal"]`, `[aria-label="Close"]`, classes `.btn-close` ou disparo da tecla `Escape`.

### 2.2 Perfil Odoo Framework (`odoo`)
- **Aplicabilidade**: Instâncias Odoo (versões 16, 17, 18, 19 e OWL Web Client).
- **Estabilização de Rede e OWL**:
  - Aguarda o desaparecimento completo do loader `.o_loading`.
  - Verifica se o microtask do JavaScript do OWL assentou.
- **Detecção de Modais**:
  - Reconhece diálogos de wizard/assistente com classes `.o_dialog`, `.modal-dialog` e `.o_form_view`.
- **Tratamento de Erros e Jargões Específicos**:
  - Intercepta popups `.o_error_dialog` e notificações `.o_notification`.
  - Audita violação de termos específicos do Odoo (ex: prefixos `x_studio_`, `res.partner`, `sale.order` visíveis).

### 2.3 Perfil Single Page Application (`spa`)
- **Aplicabilidade**: Aplicações React, Next.js, Vue e Angular.
- **Estabilização**: Aguarda término de hidratação do cliente (*hydration complete*) e ausência de skeletons de carregamento (`.skeleton`, `[aria-busy="true"]`).

---

## 3. Interface de um Perfil (Código Python)

Todos os perfis herdam da classe base `BaseProfile`:

```python
from abc import ABC, abstractmethod
from playwright.async_api import Page


class BaseProfile(ABC):
    name: str = "base"

    @abstractmethod
    async def wait_until_ready(self, page: Page, timeout: int = 10_000) -> None:
        """Aguarda a aplicação estabilizar após uma ação ou navegação."""
        pass

    @abstractmethod
    async def wait_for_modal(self, page: Page, timeout: int = 8_000) -> bool:
        """Aguarda que um modal seja renderizado e estabilizado."""
        pass

    @abstractmethod
    async def get_modal_selectors(self) -> list[str]:
        """Retorna a lista de seletores CSS representativos de modais."""
        pass

    @abstractmethod
    async def check_unhandled_errors(self, page: Page) -> list[str]:
        """Inspeciona o DOM procurando diálogos de erro específicos do framework."""
        pass
```

---

## 4. Como Ativar um Perfil

1. **No arquivo de cenário (YAML)**:
   ```yaml
   profile: "odoo"   # ou 'generic', 'spa'
   ```
2. **Pela linha de comando**:
   ```bash
   python main.py --profile odoo --scenario scenarios/meu_teste.yaml
   ```

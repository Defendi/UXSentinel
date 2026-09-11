# Guia de Criação de Releases no GitHub e Publicação no PyPI 🚀

Este guia descreve o processo oficial para criar uma nova **Release no GitHub** e disparar a esteira automatizada de CI/CD para compilar, testar e publicar o pacote **UXSentinel** no **PyPI**.

---

## 🏗️ Como Funciona o Ciclo de Publicação

A publicação do UXSentinel é automatizada pelo GitHub Actions através do arquivo [`.github/workflows/python-publish.yml`](../.github/workflows/python-publish.yml).

A esteira executa automaticamente as seguintes etapas em um ambiente limpo Ubuntu com Python 3.12:
1. **Setup & Dependências**: Instala dependências do projeto e o navegador Chromium do Playwright com dependências de sistema (`playwright install --with-deps chromium`).
2. **Quality Gate**: Valida o código com o linter `ruff check .` e o formatador `ruff format --check .`.
3. **Bateria de Testes**: Executa a suíte interna `python tests/test_engine.py`.
4. **Build do Pacote**: Constrói o pacote wheel (`.whl`) e o pacote de código-fonte (`.tar.gz`) com `python -m build`.
5. **Checagem de Integridade**: Valida os metadados e o README com `twine check --strict dist/*`.
6. **Publicação no PyPI**: Envia os pacotes com a action oficial `pypa/gh-action-pypi-publish@release/v1` utilizando o token seguro configurado nos secrets (`PYPI_API_TOKEN` ou `PYPI_TOKEN`).

---

## 📋 Pré-requisitos Antes de Publicar

Antes de gerar uma nova release, certifique-se de que a nova versão semântica foi definida nos dois arquivos principais do projeto:

1. **[`pyproject.toml`](../pyproject.toml)**:
   ```toml
   [project]
   name = "uxsentinel"
   version = "1.0.2"   # <-- Altere para a versão desejada
   ```

2. **[`uxsentinel/__init__.py`](../uxsentinel/__init__.py)**:
   ```python
   __version__ = "1.0.2"  # <-- Sincronizado com o pyproject.toml
   ```

3. **Commit & Push**:
   Todos os arquivos devem estar comitados e enviados para o branch `main`:
   ```bash
   git add .
   git commit -m "chore: bump version to 1.0.2"
   git push origin main
   ```

> [!IMPORTANT]
> **Imutabilidade de Versões no PyPI:**  
> O PyPI proíbe estritamente sobrescrever versões já publicadas. Cada nova publicação **precisa obrigatoriamente ter uma versão superior** (ex: `1.0.2` ➔ `1.0.3` ou `1.1.0`), caso contrário o deploy falhará com erro `HTTP 400: File already exists`.

---

## ⚡ Método 1: Criando a Release pelo Terminal (GitHub CLI `gh`)

Se você utiliza o terminal, pode criar a tag, publicar a release e disparar a pipeline com um **único comando**:

```bash
gh release create v1.0.2 \
  --title "v1.0.2 - Suporte Multi-IA e Validação Obrigatória de Cenários" \
  --notes "Versão 1.0.2 do UXSentinel com suporte a múltiplos provedores (Gemini, Claude, GPT, Ollama), validação estrita de cenários e comandos de versão na CLI."
```

### O que este comando faz:
1. Cria a tag Git remota `v1.0.2`.
2. Publica a Release na aba de releases do repositório no GitHub.
3. Dispara o evento `release: [published]`, ativando o workflow de publicação no PyPI.

---

## 🌐 Método 2: Criando a Release pela Interface Web do GitHub

1. Acesse o repositório oficial no navegador:  
   👉 **`https://github.com/Defendi/UXSentinel`**
2. Na coluna lateral direita, na seção **Releases**, clique em:  
   👉 **Create a new release** (ou **Draft a new release**).
3. Preencha os campos do formulário:
   - **Choose a tag**: Digite o número da versão precedido de `v` (ex: `v1.0.2`) e clique em **Create new tag: v1.0.2 on publish**.
   - **Target**: Confirme que está apontando para o branch **`main`**.
   - **Release title**: Digite o título da release (ex: `v1.0.2 - Suporte Multi-IA e Validação de Cenários`).
   - **Description**: Descreva as novidades da versão ou clique no botão **Generate release notes** para puxar os títulos dos commits automaticamente.
4. Clique no botão verde:  
   👉 **Publish release**.

---

## 🔘 Método 3: Publicação Manual via GitHub Actions (`workflow_dispatch`)

Caso você queira publicar o pacote diretamente no PyPI **sem criar uma Release formal no GitHub**:

1. Acesse: `https://github.com/Defendi/UXSentinel/actions`
2. Na lista de workflows à esquerda, clique em: **`Publish UXSentinel to PyPI`**.
3. No banner superior à direita, clique em: **`Run workflow`** ➔ selecione o branch `main` ➔ clique em **Run workflow**.

---

## 🔍 Como Acompanhar a Publicação

Assim que a release for disparada por qualquer um dos métodos acima:

### 1. Pelo Terminal (tempo real)
Execute na raiz do projeto:
```bash
gh run watch
```
Ele exibirá o progresso detalhado de cada step (checkout, linter, testes, build e envio ao PyPI).

### 2. Pelo Navegador
Acesse:
👉 **`https://github.com/Defendi/UXSentinel/actions`**

---

## 📦 Verificando a Publicação no PyPI

Após o término da esteira (com status verde ✅), a nova versão estará disponível mundialmente:

👉 **`https://pypi.org/project/uxsentinel/`**

Qualquer desenvolvedor poderá atualizar ou instalar executando:
```bash
pip install --upgrade uxsentinel
```

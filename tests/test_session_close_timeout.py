"""Encerramento da sessão do navegador sob processo travado.

Se o Chromium deixa de responder (renderer travado, processo zumbi), o fechamento
não pode bloquear para sempre: em CI isso pendura o pipeline inteiro.
"""

import asyncio
from types import SimpleNamespace

import pytest

from uxsentinel.browser import session as session_mod
from uxsentinel.browser.session import BrowserSession
from uxsentinel.core.config import BrowserSettings


@pytest.mark.asyncio
async def test_close_gives_up_on_unresponsive_browser(monkeypatch):
    monkeypatch.setattr(session_mod, "CLOSE_TIMEOUT_SECONDS", 0.05, raising=False)

    async def travado(*args, **kwargs):
        await asyncio.sleep(3600)

    sessao = BrowserSession(BrowserSettings())
    sessao.page = None
    sessao.context = None
    sessao.browser = SimpleNamespace(close=travado)
    sessao.playwright = SimpleNamespace(stop=travado)

    await asyncio.wait_for(sessao.close(), timeout=2)

    assert sessao.browser is None
    assert sessao.playwright is None

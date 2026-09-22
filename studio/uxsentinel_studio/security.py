"""Segurança e autenticação efêmera por token de sessão para o UXSentinel Studio."""

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

SESSION_TOKEN: str = secrets.token_hex(32)
API_KEY_HEADER = APIKeyHeader(name="X-Studio-Token", auto_error=False)


def get_session_token() -> str:
    """Retorna o token efêmero ativo da sessão."""
    return SESSION_TOKEN


def set_session_token(new_token: str) -> None:
    """Define um novo token efêmero de sessão (usado em testes)."""
    global SESSION_TOKEN
    SESSION_TOKEN = new_token


async def verify_studio_token(token: str | None = Security(API_KEY_HEADER)) -> str:
    """Valida o cabeçalho X-Studio-Token com comparação segura contra timing attacks."""
    if not token or not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sessão inválido ou ausente. Acesso não autorizado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def verify_studio_token_or_query(
    token: str | None = None,
    header_token: str | None = Security(API_KEY_HEADER),
) -> str:
    """Valida o token por cabeçalho X-Studio-Token ou por query param ?token= (SSE EventSource)."""
    effective_token = header_token or token
    if not effective_token or not secrets.compare_digest(effective_token, SESSION_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sessão inválido ou ausente. Acesso não autorizado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return effective_token

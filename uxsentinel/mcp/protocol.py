"""Modelos e protocolos para comunicação MCP (Model Context Protocol) via JSON-RPC 2.0.

Define as estruturas de dados Pydantic v2 para requisições, respostas,
notificações, ferramentas (tools) e recursos (resources) do protocolo MCP.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from uxsentinel import __version__

# Códigos de erro padrão da especificação JSON-RPC 2.0
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Versão do protocolo MCP suportada
MCP_PROTOCOL_VERSION = "2024-11-05"


class JsonRpcError(BaseModel):
    """Representa um erro em uma resposta JSON-RPC 2.0."""

    code: int
    message: str
    data: Any | None = None

    model_config = ConfigDict(extra="ignore")


class JsonRpcRequest(BaseModel):
    """Representa uma chamada de método JSON-RPC 2.0."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None

    model_config = ConfigDict(extra="ignore")


class JsonRpcResponse(BaseModel):
    """Representa a resposta de uma requisição JSON-RPC 2.0."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcError | None = None

    model_config = ConfigDict(extra="ignore")


class JsonRpcNotification(BaseModel):
    """Representa uma notificação unidirecional JSON-RPC 2.0 (sem id)."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None

    model_config = ConfigDict(extra="ignore")


class TextContent(BaseModel):
    """Conteúdo textual retornado por ferramentas MCP."""

    type: str = "text"
    text: str

    model_config = ConfigDict(extra="ignore")


class CallToolResult(BaseModel):
    """Resultado da invocação de uma ferramenta MCP."""

    content: list[TextContent] = Field(default_factory=list)
    isError: bool = False

    model_config = ConfigDict(extra="ignore")


class ToolDefinition(BaseModel):
    """Definição de uma ferramenta exposta pelo servidor MCP."""

    name: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class ResourceDefinition(BaseModel):
    """Definição de um recurso exposto para leitura via MCP."""

    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = "application/json"

    model_config = ConfigDict(extra="ignore")


class ResourceContent(BaseModel):
    """Conteúdo estruturado retornado na leitura de um recurso MCP."""

    uri: str
    mimeType: str | None = "application/json"
    text: str | None = None
    blob: str | None = None

    model_config = ConfigDict(extra="ignore")


class ServerCapabilities(BaseModel):
    """Capacidades declaradas pelo servidor MCP durante o handshake."""

    tools: dict[str, Any] = Field(default_factory=lambda: {"listChanged": False})
    resources: dict[str, Any] = Field(default_factory=lambda: {"subscribe": False, "listChanged": False})

    model_config = ConfigDict(extra="ignore")


class ServerInfo(BaseModel):
    """Informações de identificação do servidor MCP."""

    name: str = "uxsentinel"
    version: str = __version__

    model_config = ConfigDict(extra="ignore")


class InitializeParams(BaseModel):
    """Parâmetros recebidos no método 'initialize' do MCP."""

    protocolVersion: str = MCP_PROTOCOL_VERSION
    capabilities: dict[str, Any] = Field(default_factory=dict)
    clientInfo: dict[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")


class InitializeResult(BaseModel):
    """Resultado retornado pelo servidor no handshake 'initialize'."""

    protocolVersion: str = MCP_PROTOCOL_VERSION
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)
    serverInfo: ServerInfo = Field(default_factory=ServerInfo)

    model_config = ConfigDict(extra="ignore")

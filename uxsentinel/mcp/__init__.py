"""Pacote do Servidor MCP (Model Context Protocol) nativo do UXSentinel.

Permite integração autônoma e padronizada com agentes de IA e IDEs
modernas através de transporte JSON-RPC 2.0 sobre stdio.
"""

from uxsentinel.mcp.protocol import (
    CallToolResult,
    InitializeParams,
    InitializeResult,
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    ResourceContent,
    ResourceDefinition,
    ServerCapabilities,
    TextContent,
    ToolDefinition,
)
from uxsentinel.mcp.server import MCPServer

__all__ = [
    "CallToolResult",
    "InitializeParams",
    "InitializeResult",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "MCPServer",
    "ResourceContent",
    "ResourceDefinition",
    "ServerCapabilities",
    "TextContent",
    "ToolDefinition",
]

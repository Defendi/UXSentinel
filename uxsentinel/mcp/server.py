"""Servidor MCP (Model Context Protocol) nativo para o UXSentinel.

Implementa a comunicação assíncrona JSON-RPC 2.0 sobre transporte stdio,
permitindo controle autônomo por agentes de IA e IDEs como Claude Desktop,
Cursor, Antigravity, VS Code Copilot e Windsurf.
"""

import asyncio
import json
import logging
import sys

from uxsentinel.core.config import GlobalConfig, load_config
from uxsentinel.mcp.handlers import (
    RESOURCES_REGISTRY,
    TOOLS_REGISTRY,
    get_last_report,
    handle_resource_read,
    inspect_url,
    list_scenarios,
    run_scenario,
    validate_scenario,
)
from uxsentinel.mcp.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    CallToolResult,
    InitializeResult,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    ServerCapabilities,
    ServerInfo,
    TextContent,
)

logger = logging.getLogger("uxsentinel.mcp.server")


class MCPServer:
    """Servidor MCP oficial do UXSentinel executado sobre transporte stdio."""

    def __init__(self, config: GlobalConfig | None = None) -> None:
        self.config = config or load_config()
        self.initialized = False

    async def dispatch_request(self, req: JsonRpcRequest) -> JsonRpcResponse | None:
        """Despacha uma requisição JSON-RPC para o manipulador correspondente."""
        method = req.method
        params = req.params if isinstance(req.params, dict) else {}

        # 1. Handshake do Protocolo MCP
        if method == "initialize":
            self.initialized = True
            result = InitializeResult(
                protocolVersion=MCP_PROTOCOL_VERSION,
                capabilities=ServerCapabilities(),
                serverInfo=ServerInfo(),
            )
            return JsonRpcResponse(id=req.id, result=result.model_dump())

        if method in ("notifications/initialized", "initialized"):
            self.initialized = True
            # Notificações em JSON-RPC não retornam payload de resposta
            return None

        # 2. Ping de Liveness
        if method == "ping":
            return JsonRpcResponse(id=req.id, result={})

        # 3. Descoberta de Ferramentas (tools/list)
        if method == "tools/list":
            tools_list = [tool.model_dump() for tool in TOOLS_REGISTRY]
            return JsonRpcResponse(id=req.id, result={"tools": tools_list})

        # 4. Execução de Ferramentas (tools/call)
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}

            if not name:
                return JsonRpcResponse(
                    id=req.id,
                    error=JsonRpcError(
                        code=INVALID_PARAMS,
                        message="O parâmetro 'name' é obrigatório em 'tools/call'.",
                    ),
                )

            tool_result: CallToolResult
            try:
                if name == "list_scenarios":
                    tool_result = await list_scenarios(
                        tag=arguments.get("tag"),
                        profile=arguments.get("profile"),
                    )
                elif name == "validate_scenario":
                    scenario_path = arguments.get("scenario_path")
                    if not scenario_path:
                        tool_result = CallToolResult(
                            content=[TextContent(text="O argumento 'scenario_path' é obrigatório.")],
                            isError=True,
                        )
                    else:
                        tool_result = await validate_scenario(scenario_path=scenario_path)
                elif name == "run_scenario":
                    scenario_path = arguments.get("scenario_path")
                    if not scenario_path:
                        tool_result = CallToolResult(
                            content=[TextContent(text="O argumento 'scenario_path' é obrigatório.")],
                            isError=True,
                        )
                    else:
                        tool_result = await run_scenario(
                            scenario_path=scenario_path,
                            profile=arguments.get("profile"),
                            headless=arguments.get("headless", True),
                            slowmo=arguments.get("slowmo", 0),
                            devtools=arguments.get("devtools", False),
                            viewport=arguments.get("viewport"),
                            ai_provider=arguments.get("ai_provider"),
                            config=self.config,
                        )
                elif name == "inspect_url":
                    url = arguments.get("url")
                    if not url:
                        tool_result = CallToolResult(
                            content=[TextContent(text="O argumento 'url' é obrigatório.")],
                            isError=True,
                        )
                    else:
                        tool_result = await inspect_url(
                            url=url,
                            viewport=arguments.get("viewport", "desktop"),
                            check_a11y=arguments.get("check_a11y", True),
                            check_visual=arguments.get("check_visual", True),
                            config=self.config,
                        )
                elif name == "get_last_report":
                    tool_result = await get_last_report(
                        format=arguments.get("format", "summary"),
                        config=self.config,
                    )
                else:
                    tool_result = CallToolResult(
                        content=[TextContent(text=f"Ferramenta MCP desconhecida: '{name}'.")],
                        isError=True,
                    )
            except Exception as err:
                logger.exception(f"Erro ao executar a ferramenta MCP '{name}'")
                tool_result = CallToolResult(
                    content=[TextContent(text=f"Exceção interna na execução da ferramenta: {err}")],
                    isError=True,
                )

            return JsonRpcResponse(id=req.id, result=tool_result.model_dump())

        # 5. Descoberta de Recursos (resources/list)
        if method == "resources/list":
            resources_list = [res.model_dump() for res in RESOURCES_REGISTRY]
            return JsonRpcResponse(id=req.id, result={"resources": resources_list})

        # 6. Leitura de Recursos (resources/read)
        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return JsonRpcResponse(
                    id=req.id,
                    error=JsonRpcError(
                        code=INVALID_PARAMS,
                        message="O parâmetro 'uri' é obrigatório em 'resources/read'.",
                    ),
                )
            try:
                content = await handle_resource_read(uri)
                return JsonRpcResponse(id=req.id, result={"contents": [content.model_dump()]})
            except Exception as exc:
                return JsonRpcResponse(
                    id=req.id,
                    error=JsonRpcError(
                        code=INVALID_PARAMS,
                        message=f"Falha ao ler o recurso '{uri}': {exc}",
                    ),
                )

        # Método não reconhecido pelo servidor MCP
        return JsonRpcResponse(
            id=req.id,
            error=JsonRpcError(
                code=METHOD_NOT_FOUND,
                message=f"Método '{method}' não suportado pelo servidor MCP.",
            ),
        )

    async def handle_line(self, line: str) -> str | None:
        """Processa uma linha contendo mensagem JSON-RPC e retorna a resposta formatada."""
        line_clean = line.strip()
        if not line_clean:
            return None

        try:
            data = json.loads(line_clean)
        except json.JSONDecodeError as err:
            err_resp = JsonRpcResponse(
                error=JsonRpcError(code=PARSE_ERROR, message=f"Erro de decodificação JSON: {err}")
            )
            return err_resp.model_dump_json(exclude_none=True)

        if not isinstance(data, dict):
            err_resp = JsonRpcResponse(
                error=JsonRpcError(
                    code=INVALID_REQUEST,
                    message="A mensagem JSON-RPC deve ser um objeto JSON.",
                )
            )
            return err_resp.model_dump_json(exclude_none=True)

        try:
            req = JsonRpcRequest.model_validate(data)
        except Exception as val_err:
            err_resp = JsonRpcResponse(
                id=data.get("id"),
                error=JsonRpcError(
                    code=INVALID_REQUEST,
                    message=f"Requisição inválida: {val_err}",
                ),
            )
            return err_resp.model_dump_json(exclude_none=True)

        resp = await self.dispatch_request(req)
        if resp is not None:
            return resp.model_dump_json(exclude_none=True)
        return None

    async def run_stdio(
        self,
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
    ) -> int:
        """Executa o loop assíncrono do servidor MCP sobre stdio.

        Garante o isolamento estrito de sys.stdout, redirecionando qualquer saída
        espúria (prints, logs do Playwright/Axe) para sys.stderr para assegurar
        que apenas payloads JSON-RPC válidos trafeguem pelo canal de dados.
        """
        original_stdout = sys.stdout
        # Redireciona sys.stdout para sys.stderr durante a vida do servidor MCP
        sys.stdout = sys.stderr

        try:
            if reader is None or writer is None:
                loop = asyncio.get_running_loop()
                real_reader = asyncio.StreamReader()
                protocol = asyncio.StreamReaderProtocol(real_reader)
                await loop.connect_read_pipe(lambda: protocol, sys.stdin)

                w_transport, w_protocol = await loop.connect_write_pipe(
                    asyncio.streams.FlowControlMixin, original_stdout
                )
                real_writer = asyncio.StreamWriter(w_transport, w_protocol, real_reader, loop)
            else:
                real_reader = reader
                real_writer = writer

            while True:
                line_bytes = await real_reader.readline()
                if not line_bytes:
                    break

                line_str = line_bytes.decode("utf-8")
                response_str = await self.handle_line(line_str)

                if response_str:
                    real_writer.write((response_str + "\n").encode("utf-8"))
                    await real_writer.drain()

            return 0

        except Exception as exc:
            logger.exception("Erro crítico no loop de execução do servidor MCP")
            print(f"[UXSentinel MCP] Erro crítico: {exc}", file=sys.stderr)
            return 1
        finally:
            # Restaura sys.stdout original ao encerrar o servidor
            sys.stdout = original_stdout

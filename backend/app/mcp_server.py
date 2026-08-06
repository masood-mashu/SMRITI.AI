"""Small MCP-compatible JSON-RPC surface for patient context tools.

This intentionally implements only the protocol methods Smriti needs. It keeps
the transport independent from the repository gateway so a hosted MCP runtime
can be added later without changing the tool contracts.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from .db import session_scope
from .integrations import MCPContextGateway
from .security import enforce_patient_access, require_security


router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(require_security)])

TOOLS = [
    {
        "name": "get_current_facts",
        "description": "Return current, non-superseded health facts for a patient.",
        "inputSchema": {
            "type": "object",
            "required": ["patient_id"],
            "properties": {"patient_id": {"type": "string", "format": "uuid"}},
        },
    },
    {
        "name": "get_emergency_facts",
        "description": "Return current emergency-relevant facts for a patient.",
        "inputSchema": {
            "type": "object",
            "required": ["patient_id"],
            "properties": {"patient_id": {"type": "string", "format": "uuid"}},
        },
    },
    {
        "name": "get_contradictions",
        "description": "Return unresolved contradiction descriptions for a patient.",
        "inputSchema": {
            "type": "object",
            "required": ["patient_id"],
            "properties": {"patient_id": {"type": "string", "format": "uuid"}},
        },
    },
]


def rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@router.post("")
def mcp_json_rpc(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if payload.get("jsonrpc") != "2.0" or not method:
        return rpc_error(request_id, -32600, "Invalid JSON-RPC request")
    if method == "initialize":
        return rpc_result(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "smriti-context", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return rpc_result(request_id, {})
    if method == "tools/list":
        return rpc_result(request_id, {"tools": TOOLS})
    if method != "tools/call":
        return rpc_error(request_id, -32601, f"Method not found: {method}")

    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name not in {tool["name"] for tool in TOOLS}:
        return rpc_error(request_id, -32602, f"Unknown tool: {name}")
    try:
        arguments = dict(arguments)
        arguments["patient_id"] = enforce_patient_access(request, str(arguments["patient_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        return rpc_error(request_id, -32602, f"Invalid tool arguments: {exc}")
    try:
        with session_scope() as session:
            result = MCPContextGateway(session).call_tool(name, arguments)
    except (KeyError, TypeError, ValueError) as exc:
        return rpc_error(request_id, -32602, f"Invalid tool arguments: {exc}")
    return rpc_result(
        request_id,
        {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result},
    )

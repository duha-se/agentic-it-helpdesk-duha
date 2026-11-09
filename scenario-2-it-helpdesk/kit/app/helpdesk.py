"""MCP client for the helpdesk system. Starts the MCP server as a subprocess and keeps it open."""
import asyncio
import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack

from app import config
from app.state import Turn

log = logging.getLogger("helpdesk.mcp")


def tool_json(result) -> dict:
    """Read an MCP tool result as a dict (structured content first, then the JSON text)."""
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict):
        return data["result"] if set(data) == {"result"} and isinstance(data["result"], dict) else data
    for part in result.content or []:
        if getattr(part, "type", "") == "text":
            try:
                return json.loads(part.text)
            except ValueError:
                return {"ok": False, "error": {"code": "bad_tool_output", "message": part.text[:200]}}
    return {"ok": False, "error": {"code": "empty_tool_output", "message": "The tool returned nothing."}}


class Helpdesk:
    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._session = None
        self._restart_lock = asyncio.Lock()

    async def start(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        # The SDK starts the server with a minimal environment unless we pass ours on.
        env = {**os.environ, "HELPDESK_API_URL": config.HELPDESK_API_URL,
               "HELPDESK_API_KEY": config.HELPDESK_API_KEY}
        params = StdioServerParameters(command=sys.executable, args=["-m", "services.helpdesk_mcp"],
                                       cwd=str(config.KIT_DIR), env=env)
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        log.info("MCP server started")

    async def stop(self) -> None:
        if self._stack:
            await self._stack.aclose()
        self._stack = self._session = None

    async def _restart(self) -> None:
        async with self._restart_lock:
            try:
                await self.stop()
            except Exception:  # noqa: BLE001 - a dead server cannot always be closed cleanly
                self._stack = self._session = None
            await self.start()

    async def call(self, tool: str, args: dict, turn: Turn | None = None) -> dict:
        """Call one MCP tool. Never raises: failures come back as {"ok": False, "error": {...}}."""
        started = time.perf_counter()
        try:
            data = await self._call_once(tool, args)
        except Exception as exc:  # noqa: BLE001
            log.warning("MCP transport problem on %s (%s): restarting the server once", tool, exc)
            try:
                await self._restart()
                data = await self._call_once(tool, args)
            except Exception as exc2:  # noqa: BLE001
                data = {"ok": False, "error": {"code": "mcp_unavailable",
                                               "message": f"The helpdesk tools are not reachable ({exc2.__class__.__name__})."}}
        ms = round((time.perf_counter() - started) * 1000)
        ok = data.get("ok") is True
        if turn is not None:
            turn.tool_calls.append({"tool": tool, "ok": ok, "ms": ms})
        if ok:
            log.info("tool=%s ok ms=%d", tool, ms)
        else:
            log.warning("tool=%s FAILED ms=%d error=%s", tool, ms, data.get("error"))
        return data

    async def _call_once(self, tool: str, args: dict) -> dict:
        if self._session is None:
            raise RuntimeError("MCP session is not started")
        result = await asyncio.wait_for(self._session.call_tool(tool, args), timeout=config.TOOL_TIMEOUT_S)
        return tool_json(result)

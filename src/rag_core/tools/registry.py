from __future__ import annotations

from typing import Dict, Any

from .base import Tool, ToolResult


class ToolsRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, payload: Dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(content=f"tool '{name}' not found")
        return tool.run(payload)


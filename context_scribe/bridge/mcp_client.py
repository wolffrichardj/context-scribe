import asyncio
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

class MemoryBankClient:
    def __init__(self, command: str = "npx", args: list[str] = None):
        import os
        self.command = command
        self.args = args or ["-y", "@allpepper/memory-bank-mcp"]
        
        env = os.environ.copy()
        if "MEMORY_BANK_ROOT" not in env:
            env["MEMORY_BANK_ROOT"] = os.path.expanduser("~/.memory-bank")
            
        self.server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=env
        )
        self.exit_stack = AsyncExitStack()
        self.session = None

    async def connect(self):
        """Connect to the Memory Bank MCP server."""
        try:
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
            self.read_stream, self.write_stream = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(self.read_stream, self.write_stream))
            await self.session.initialize()
            print("Connected to Memory Bank MCP Server.")
        except Exception as e:
            print(f"Failed to connect to MCP server: {e}")
            raise

    async def save_rule(self, rule: str, project_name: str = "global"):
        """Save a new rule to the memory bank using the update_memory tool."""
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
            
        try:
            # Check available tools to see which one to use
            # Usually memory-bank has something like "memory_bank_update" or "memory_bank_write"
            # For this example we use memory_bank_write
            result = await self.session.call_tool(
                "memory_bank_write", 
                arguments={
                    "projectName": project_name,
                    "fileName": "global_rules.md",
                    "content": rule
                }
            )
            return result
        except Exception as e:
            print(f"Error saving to memory bank: {e}")
            return None

    async def close(self):
        """Close the connection."""
        await self.exit_stack.aclose()

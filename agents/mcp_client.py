import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


def create_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "case": {
                "url": os.getenv(
                    "CASE_MCP_URL",
                    "http://localhost:8001/mcp",
                ),
                "transport": "streamable_http",
            },
            "policy": {
                "url": os.getenv(
                    "POLICY_MCP_URL",
                    "http://localhost:8002/mcp",
                ),
                "transport": "streamable_http",
            },
            "documents": {
                "url": os.getenv(
                    "DOCUMENTS_MCP_URL",
                    "http://localhost:8003/mcp",
                ),
                "transport": "streamable_http",
            },
            "workflow": {
                "url": os.getenv(
                    "WORKFLOW_MCP_URL",
                    "http://localhost:8004/mcp",
                ),
                "transport": "streamable_http",
            },
        }
    )


async def load_all_tools():
    client = create_mcp_client()
    return await client.get_tools()


def select_tools(all_tools, allowed_names: set[str]):
    return [
        tool
        for tool in all_tools
        if tool.name.split("_")[-1] in allowed_names
        or tool.name in allowed_names
    ]

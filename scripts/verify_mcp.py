"""Exercise the real MCP transport and the authenticated application boundary."""

import asyncio
import json
import os
from pathlib import Path
import sys

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    base = os.getenv("ASSISTANT_API_URL", "http://127.0.0.1:8100")
    with httpx.Client(base_url=base, timeout=20) as client:
        token = client.post("/api/dev-session").json()["access_token"]
        session = client.post(
            "/api/session", json={"role": "doctor"}, headers={"Authorization": "Bearer " + token}
        ).json()
    env = {
        **os.environ,
        "ASSISTANT_API_URL": base,
        "ASSISTANT_ACCESS_TOKEN": token,
        "ASSISTANT_WORKSPACE_ID": session["workspace_id"],
        "ASSISTANT_ROLE": "doctor",
    }
    evidence = []
    for role in ["doctor", "editor"]:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "services.assistant.mcp_server"],
            env={**env, "ASSISTANT_ROLE": role},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as mcp:
                await mcp.initialize()
                listed = await mcp.list_tools()
                result = await mcp.call_tool("get_preparation_status", {})
                invalid = await mcp.call_tool("get_schedule", {"date": 42})
                data = {
                    "role": role,
                    "tools": [tool.name for tool in listed.tools],
                    "preparation_denied": bool(result.isError),
                    "invalid_arguments_denied": bool(invalid.isError),
                }
                if role == "doctor":
                    assert not result.isError
                    structured = result.structuredContent
                    if not structured:
                        structured = json.loads(result.content[0].text)
                    assert (
                        next(row for row in structured["preparation"] if row["id"] == "admin-maya")[
                            "minutes_remaining"
                        ]
                        == 45
                    )
                    data["deadline_minutes"] = 45
                else:
                    assert result.isError
                assert invalid.isError
                evidence.append(data)
    out = Path("artifacts/verification")
    out.mkdir(parents=True, exist_ok=True)
    (out / "mcp.json").write_text(json.dumps({"passed": True, "cases": evidence}, indent=2))
    print(json.dumps({"mcp_transport": "stdio", "passed": True, "roles_tested": 2, "schema_rejection": True}))


if __name__ == "__main__":
    asyncio.run(main())

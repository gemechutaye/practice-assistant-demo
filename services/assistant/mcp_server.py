"""MCP client entry point using the same authenticated application endpoints."""

import os

from dotenv import load_dotenv
import httpx
from mcp.server.fastmcp import FastMCP

if os.getenv("MCP_ENV_FILE"):
    load_dotenv(os.environ["MCP_ENV_FILE"])

mcp = FastMCP(
    "Practice Assistant",
    instructions="Tools act only inside the caller's isolated fictional office. Read a plan's exact changes before approving. No employer system or real email delivery is connected.",
)


def call(path: str, body: dict | None = None):
    base = os.environ["ASSISTANT_API_URL"].rstrip("/")
    headers = {
        "Authorization": "Bearer " + os.environ["ASSISTANT_ACCESS_TOKEN"],
        "X-Workspace-Id": os.environ["ASSISTANT_WORKSPACE_ID"],
        "X-Demo-Role": os.getenv("ASSISTANT_ROLE", "doctor"),
    }
    with httpx.Client(base_url=base, headers=headers, timeout=90) as client:
        response = client.get("/api" + path) if body is None else client.post("/api" + path, json=body)
        if response.is_error:
            try:
                reason = response.json().get("detail", "The operation failed.")
            except ValueError:
                reason = "The operation failed."
            raise ValueError(f"HTTP {response.status_code}: {reason}")
        return response.json()


@mcp.tool()
def get_schedule(date: str | None = None) -> dict:
    """Read permitted calendar events and current versions."""
    return call("/tools/read", {"name": "get_schedule", "arguments": {"date": date} if date else {}})


@mcp.tool()
def get_preparation_status() -> dict:
    """Read fictional paperwork status and calculated administrative deadlines."""
    return call("/tools/read", {"name": "get_preparation_status", "arguments": {}})


@mcp.tool()
def get_open_tasks() -> dict:
    """Read unfinished tasks in the current role."""
    return call("/tools/read", {"name": "get_open_tasks", "arguments": {}})


@mcp.tool()
def search_sources(query: str) -> dict:
    """Search scoped source notes with real embeddings and text retrieval."""
    return call("/tools/read", {"name": "search_sources", "arguments": {"query": query}})


@mcp.tool()
def get_preferences() -> dict:
    """Read the confirmed preferences accessible to the current role."""
    return call("/tools/read", {"name": "get_preferences", "arguments": {}})


@mcp.tool()
def ask_assistant(message: str) -> dict:
    """Start a live model-driven request. Changes remain pending until approved."""
    return call("/runs", {"message": message})


@mcp.tool()
def inspect_run(run_id: str) -> dict:
    """Inspect the plan, sources, tool results, and recorded effects of a run."""
    return call("/runs/" + run_id)


@mcp.tool()
def approve_plan(plan_id: str) -> dict:
    """Approve the exact inspected plan, or resume its already approved remaining actions."""
    return call("/plans/" + plan_id + "/approve", {})


@mcp.tool()
def submit_demo_handoff(event_id: str, event_type: str, record_id: str) -> dict:
    """Queue an idempotent synthetic paperwork_completed or content_reviewed event."""
    return call(
        "/integrations/handoff",
        {
            "event_id": event_id,
            "event_type": event_type,
            "record_id": record_id,
            "source_system": "practice-demo",
        },
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

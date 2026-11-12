"""
SAM Core — Model Context Protocol (MCP) & Plugins Hub

Manages Model Context Protocol (MCP) servers and third-party integrations (GitHub,
Google Workspace, Slack, Filesystem, and Custom stdio/SSE MCP servers).
Stores configuration under ~/.sam_data/config/mcp_servers.json.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SAM.MCPHub")

SAM_DATA_DIR = Path.home() / ".sam_data"
MCP_CONFIG_PATH = SAM_DATA_DIR / "config" / "mcp_servers.json"

# Built-in Catalog Templates for Popular MCP Providers
MCP_CATALOG_TEMPLATES = [
    {
        "id": "github",
        "name": "GitHub",
        "description": "Search repositories, read source code, inspect PRs, and manage GitHub issues.",
        "icon": "github",
        "category": "developer",
        "auth_type": "token",
        "token_label": "Personal Access Token (classic or fine-grained)",
        "docs_url": "https://github.com/settings/tokens",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_keys": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
    },
    {
        "id": "filesystem",
        "name": "Local Filesystem",
        "description": "Safe, bounded file read, search, and directory navigation across allowed workspace paths.",
        "icon": "folder",
        "category": "system",
        "auth_type": "none",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path.home() / "Desktop"), str(Path.home() / "Projects")],
        "env_keys": [],
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "description": "Search and retrieve documents, spreadsheets, and files from Google Drive.",
        "icon": "google",
        "category": "productivity",
        "auth_type": "oauth",
        "token_label": "Google Cloud API Client Credentials / Token",
        "docs_url": "https://developers.google.com/drive/api/guides/quickstart/python",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "env_keys": ["GOOGLE_DRIVE_CREDENTIALS"],
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Send notifications, read thread messages, and inspect channels in your Slack workspace.",
        "icon": "slack",
        "category": "communication",
        "auth_type": "token",
        "token_label": "Slack Bot User OAuth Token (xoxb-...)",
        "docs_url": "https://api.slack.com/apps",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env_keys": ["SLACK_BOT_TOKEN"],
    },
    {
        "id": "postgres",
        "name": "PostgreSQL Database",
        "description": "Inspect database schemas, query tables, and read database models safely in read-only mode.",
        "icon": "database",
        "category": "database",
        "auth_type": "token",
        "token_label": "Database Connection URI (postgresql://user:pass@host:5432/db)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env_keys": ["DATABASE_URL"],
    },
]


def load_mcp_config() -> Dict[str, Any]:
    """Load MCP server configurations from disk."""
    if not MCP_CONFIG_PATH.exists():
        return {"servers": {}}
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {"servers": {}}
    except Exception as e:
        logger.warning(f"Failed to load MCP config: {e}")
        return {"servers": {}}


def save_mcp_config(data: Dict[str, Any]) -> None:
    """Save MCP server configurations securely with user-only permissions."""
    MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(MCP_CONFIG_PATH, 0o600)


def list_servers() -> List[Dict[str, Any]]:
    """Return all configured MCP servers and merge with catalog metadata."""
    config = load_mcp_config()
    servers = config.get("servers", {})
    results = []

    for s_id, s_data in servers.items():
        # Mask sensitive env keys
        masked_env = {}
        for k, v in s_data.get("env", {}).items():
            if len(v) > 8:
                masked_env[k] = v[:4] + "..." + v[-4:]
            else:
                masked_env[k] = "****" if v else ""

        results.append({
            "id": s_id,
            "name": s_data.get("name", s_id),
            "description": s_data.get("description", ""),
            "enabled": s_data.get("enabled", True),
            "command": s_data.get("command", ""),
            "args": s_data.get("args", []),
            "url": s_data.get("url", ""),
            "transport": s_data.get("transport", "stdio"),
            "masked_env": masked_env,
            "tools_count": s_data.get("tools_count", 0),
            "status": s_data.get("status", "configured"),
        })

    return results


def get_catalog() -> List[Dict[str, Any]]:
    """Return available templates for MCP connections."""
    config = load_mcp_config()
    existing_ids = set(config.get("servers", {}).keys())

    catalog = []
    for tmpl in MCP_CATALOG_TEMPLATES:
        is_installed = tmpl["id"] in existing_ids
        catalog.append({
            **tmpl,
            "installed": is_installed,
            "enabled": config.get("servers", {}).get(tmpl["id"], {}).get("enabled", False) if is_installed else False,
        })
    return catalog


def add_or_update_server(
    server_id: str,
    name: str,
    description: str = "",
    command: str = "npx",
    args: Optional[List[str]] = None,
    url: str = "",
    transport: str = "stdio",
    env: Optional[Dict[str, str]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Register or update an MCP server configuration."""
    server_id = server_id.lower().strip()
    config = load_mcp_config()
    servers = config.setdefault("servers", {})

    existing = servers.get(server_id, {})
    # Merge existing environment variables if new values are empty / masked
    current_env = existing.get("env", {})
    merged_env = dict(current_env)
    if env:
        for k, v in env.items():
            if v and not v.startswith("****") and not "..." in v:
                merged_env[k] = v.strip()

    servers[server_id] = {
        "id": server_id,
        "name": name.strip(),
        "description": description.strip(),
        "command": command.strip(),
        "args": args or [],
        "url": url.strip(),
        "transport": transport,
        "env": merged_env,
        "enabled": enabled,
        "status": "ready" if (merged_env or transport == "sse" or server_id == "filesystem") else "configured",
    }

    save_mcp_config(config)
    return servers[server_id]


def toggle_server(server_id: str, enabled: bool) -> bool:
    """Enable or disable a configured MCP server."""
    server_id = server_id.lower().strip()
    config = load_mcp_config()
    servers = config.get("servers", {})
    if server_id in servers:
        servers[server_id]["enabled"] = enabled
        save_mcp_config(config)
        return True
    return False


def delete_server(server_id: str) -> bool:
    """Remove a configured MCP server."""
    server_id = server_id.lower().strip()
    config = load_mcp_config()
    servers = config.get("servers", {})
    if server_id in servers:
        del servers[server_id]
        save_mcp_config(config)
        return True
    return False


def test_server_connection(server_id: str) -> Dict[str, Any]:
    """Test availability of an MCP server executable or token."""
    server_id = server_id.lower().strip()
    config = load_mcp_config()
    server = config.get("servers", {}).get(server_id)
    if not server:
        return {"ok": False, "error": f"Server '{server_id}' not found."}

    cmd = server.get("command", "")
    if cmd:
        resolved = shutil.which(cmd)
        if not resolved:
            return {
                "ok": False,
                "error": f"Command '{cmd}' not found in system PATH. Ensure Node.js (npx) or Python is installed."
            }

    # Verify required tokens if specified
    for tmpl in MCP_CATALOG_TEMPLATES:
        if tmpl["id"] == server_id:
            for env_key in tmpl.get("env_keys", []):
                if not server.get("env", {}).get(env_key):
                    return {
                        "ok": False,
                        "error": f"Missing required credential: {env_key}. Please save your API token."
                    }

    return {"ok": True, "message": f"MCP server '{server['name']}' is configured and ready."}

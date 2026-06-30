"""
MCP (Model Context Protocol) Server for Amazon ASIN Monitor

Exposes the monitor's capabilities as MCP tools, enabling AI assistants
like Claude Desktop, Cline, and Codex to interact with the monitor.

Usage:
    python mcp-server.py

Configure in Claude Desktop (claude_desktop_config.json):
{
    "mcpServers": {
        "amazon-asin-monitor": {
            "command": "python",
            "args": ["path/to/mcp-server.py"],
            "cwd": "path/to/amazon-asin-monitor"
        }
    }
}

Configure in Cline (VS Code):
    Add to cline_mcp_settings.json with the same format as above.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure the project directory is on sys.path so we can import scraper
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Change working directory so data/ paths resolve correctly
os.chdir(str(PROJECT_DIR))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from scraper import (
    scrape_amazon_page,
    add_asin,
    get_summary,
    clear_cookies,
    load_config,
    save_config,
    load_asin_data,
)

server = Server("amazon-asin-monitor")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="amz_fetch",
            description="Fetch real-time data for a single Amazon ASIN. Returns price, rating, review count, and stock status. Uses anti-detection measures (UA rotation, cookie persistence, homepage warm-up).",
            inputSchema={
                "type": "object",
                "properties": {
                    "asin": {
                        "type": "string",
                        "description": "Amazon ASIN (10-character product code, e.g. B0FKHC8PPV)"
                    },
                    "marketplace": {
                        "type": "string",
                        "description": "Amazon marketplace code (default: amazon.us). Options: amazon.us, amazon.uk, amazon.de, amazon.fr, amazon.jp, amazon.ca, amazon.it, amazon.es",
                        "default": "amazon.us"
                    }
                },
                "required": ["asin"]
            }
        ),
        Tool(
            name="amz_add",
            description="Add a new ASIN to the monitoring list. The ASIN will be tracked in future fetch runs. Optionally provide a display name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asin": {
                        "type": "string",
                        "description": "Amazon ASIN to add (10-character code)"
                    },
                    "marketplace": {
                        "type": "string",
                        "description": "Amazon marketplace (default: amazon.us)",
                        "default": "amazon.us"
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional display name for the product",
                        "default": ""
                    }
                },
                "required": ["asin"]
            }
        ),
        Tool(
            name="amz_remove",
            description="Remove an ASIN from the monitoring list. Historical data files are preserved but the ASIN will no longer be updated.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asin": {
                        "type": "string",
                        "description": "ASIN to remove from monitoring"
                    }
                },
                "required": ["asin"]
            }
        ),
        Tool(
            name="amz_summary",
            description="Get a summary of all monitored ASINs with their latest data. Shows price, rating, review count, stock status, last updated time, and data points count.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="amz_fetch_all",
            description="Fetch real-time data for ALL monitored ASINs at once. Uses anti-detection with delays between requests. Returns summary of successes and failures.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="amz_clear_cookies",
            description="Clear all saved browser cookies. Use this if you're getting blocked/CAPTCHA — fresh cookies may help bypass detection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "marketplace": {
                        "type": "string",
                        "description": "Clear cookies for specific marketplace only (e.g. amazon.us). If omitted, clears ALL cookies.",
                        "default": ""
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="amz_history",
            description="Get historical data for a specific ASIN. Returns all stored data points (timestamp, price, rating, review_count, stock status).",
            inputSchema={
                "type": "object",
                "properties": {
                    "asin": {
                        "type": "string",
                        "description": "ASIN to retrieve history for"
                    }
                },
                "required": ["asin"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "amz_fetch":
            asin = arguments["asin"]
            marketplace = arguments.get("marketplace", "amazon.us")
            result = scrape_amazon_page(asin, marketplace)

            if result is None:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "blocked",
                        "message": f"Failed to fetch {asin}. Amazon may be blocking this request. Try clearing cookies and retrying later.",
                        "asin": asin
                    }, ensure_ascii=False, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "asin": result["asin"],
                    "marketplace": result["marketplace"],
                    "name": result.get("name", ""),
                    "url": result["url"],
                    "data": {
                        "price": result["price"],
                        "currency": result["currency"],
                        "rating": result["rating"],
                        "review_count": result["review_count"],
                        "in_stock": result["in_stock"],
                    },
                    "timestamp": result["timestamp"]
                }, ensure_ascii=False, indent=2)
            )]

        elif name == "amz_add":
            asin = arguments["asin"]
            marketplace = arguments.get("marketplace", "amazon.us")
            product_name = arguments.get("name", "")
            success = add_asin(asin, marketplace, product_name)

            if success:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "success",
                        "message": f"Added {asin} to monitoring list",
                        "asin": asin,
                        "marketplace": marketplace
                    }, ensure_ascii=False, indent=2)
                )]
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "message": f"{asin} already exists in monitoring list"
                    }, ensure_ascii=False, indent=2)
                )]

        elif name == "amz_remove":
            asin = arguments["asin"]
            config = load_config()
            config["asins"] = [e for e in config["asins"] if e["asin"] != asin]
            save_config(config)

            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "message": f"Removed {asin} from monitoring list (data file preserved)",
                    "asin": asin
                }, ensure_ascii=False, indent=2)
            )]

        elif name == "amz_summary":
            summary = get_summary()
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "count": len(summary),
                    "products": summary
                }, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "amz_fetch_all":
            from scraper import run_all
            run_all()
            summary = get_summary()
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "message": f"Fetched {len(summary)} ASINs",
                    "products": summary
                }, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "amz_clear_cookies":
            marketplace = arguments.get("marketplace", "")
            clear_cookies(marketplace if marketplace else None)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "message": f"Cleared cookies {'for ' + marketplace if marketplace else 'for all marketplaces'}"
                }, ensure_ascii=False, indent=2)
            )]

        elif name == "amz_history":
            asin = arguments["asin"]
            data = load_asin_data(asin)
            history = data.get("history", [])

            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "asin": asin,
                    "name": data.get("name", ""),
                    "url": data.get("url", ""),
                    "data_points": len(history),
                    "history": history
                }, ensure_ascii=False, indent=2, default=str)
            )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"status": "error", "message": f"Unknown tool: {name}"})
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "message": f"{type(e).__name__}: {str(e)}"
            }, ensure_ascii=False)
        )]


async def main():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

# Amazon ASIN Monitor

A local web dashboard that tracks Amazon product price, rating, review count, and stock status over time. Scrapes real data with anti-detection measures. Works with any AI agent platform.

![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)

## Features

- **Real-time Amazon scraping** — 7-layer anti-detection (UA rotation, cookie persistence, homepage warm-up, referrer chain, human-like delays, exponential backoff, graceful degradation)
- **Interactive dashboard** — Price/rating/review/stock trend charts (Chart.js), sidebar product list, CSV export
- **MCP Server** — Works with **Claude Desktop**, **Cline** (VS Code), **Codex**, and any MCP-compatible AI agent
- **CLI tool** — Simple command-line interface for scripting and cron jobs
- **Never fabricates data** — Returns `null` for fields that can't be fetched, dashboard shows `--`
- **Multi-marketplace** — Amazon US, UK, DE, FR, JP, CA, IT, ES

## Quick Start

```bash
# 1. Clone
git clone https://github.com/CookieCN/amazon-asin-monitor.git
cd amazon-asin-monitor

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your first ASIN
python scraper.py add --asin=B0FKHC8PPV

# 4. Start the dashboard
python server.py

# 5. Open http://localhost:8932
```

## Platform Integration

### Claude Desktop (MCP)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "amazon-asin-monitor": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-server.py"],
      "cwd": "/absolute/path/to/amazon-asin-monitor"
    }
  }
}
```

Then in Claude, you can say:

> "Fetch the latest data for ASIN B0FKHC8PPV"
> "Add B0F7RS9MLJ to my Amazon monitor"
> "Show me the summary of all my monitored products"

### Cline (VS Code)

Add to your `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "amazon-asin-monitor": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-server.py"],
      "cwd": "/absolute/path/to/amazon-asin-monitor"
    }
  }
}
```

### Cursor / Windsurf / Terminal

Use the CLI directly:

```bash
# Fetch all monitored ASINs
python scraper.py run

# Fetch single ASIN
python scraper.py run --asin=B0FKHC8PPV

# Add ASIN for Japan marketplace
python scraper.py add --asin=B0XXXXXXXXX --marketplace=amazon.jp

# Show summary
python scraper.py summary

# Clear cookies if blocked
python scraper.py clear-cookies
```

### Cron / Scheduled Automation

```bash
# Daily at 9:30 AM and 6:30 PM (Linux/macOS)
crontab -e
30 9,18 * * * cd /path/to/amazon-asin-monitor && python scraper.py run >> cron.log 2>&1
```

On Windows Task Scheduler, set the action to run `python scraper.py run` with start-in set to the project directory.

## MCP Tools Reference

When connected via MCP, the AI assistant has access to these tools:

| Tool | Description |
|------|-------------|
| `amz_fetch` | Fetch real-time data for a single ASIN |
| `amz_fetch_all` | Fetch data for all monitored ASINs |
| `amz_add` | Add a new ASIN to monitoring |
| `amz_remove` | Remove an ASIN from monitoring |
| `amz_summary` | Get summary of all ASINs (latest data) |
| `amz_history` | Get full history for an ASIN |
| `amz_clear_cookies` | Clear session cookies (anti-block) |

## Anti-Detection Stack

The scraper uses 7 layers to avoid Amazon bot detection:

1. **UA Pool** — 30+ real browser User-Agent strings with matching Sec-Ch-Ua headers
2. **Cookie Persistence** — Saves cookies across runs, builds session trust over time
3. **Homepage Warm-up** — Visits Amazon homepage first (from Google referrer) before product pages
4. **Jittered Delays** — Human-like random delays between requests (3-8 seconds)
5. **Referrer Chain** — Simulates organic navigation (Google → Amazon → product)
6. **Multi-strategy Parsing** — Multiple CSS selectors per data field, graceful fallback
7. **Exponential Backoff** — Auto-retry with increasing delays (10s → 20s → 40s)

## Dashboard

The dashboard (`index.html`) is served by `server.py` at `http://localhost:8932`:

- Left sidebar: ASIN list with quick stats (price, stock indicator)
- Main panel: Product info card + 4 interactive charts
- Time range toggle: 7 days / 30 days / 90 days / All
- CSV export per product
- Price chart: **red = increase, green = decrease** (Chinese stock convention)

## File Structure

```
amazon-asin-monitor/
├── scraper.py          # Core scraper with anti-detection
├── server.py           # HTTP API + dashboard server (port 8932)
├── index.html          # Interactive dashboard (Chart.js)
├── mcp-server.py       # MCP server for AI agent integration
├── requirements.txt    # Python dependencies
├── data/               # Runtime data (config.json + {ASIN}.json)
│   └── cookies/        # Persistent browser cookies
└── README.md
```

## Known Limitations

- **Amazon blocks** — Anti-detection is not 100% bulletproof. If persistently blocked, clear cookies (`python scraper.py clear-cookies`) and wait a few hours.
- **Review count threshold** — Parsing requires ≥10 reviews to prevent false positives from similar numbers on the page.
- **Stock status** — Some product pages don't clearly expose stock status; returns `null` in those cases.
- **Rate limits** — Don't run more than 2-3 times per day to avoid triggering additional defenses.

## License

MIT — use it, fork it, share it.

## Credits

Built for AI agent workflows. Designed to provide truthful, actionable Amazon product data without fabricated values.

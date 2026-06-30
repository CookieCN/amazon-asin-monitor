"""
Amazon ASIN Monitor - Backend Server
Serves the HTML dashboard and handles API requests for data management.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import random
import math

# Add scraper functions
sys.path.insert(0, str(Path(__file__).parent))
from scraper import (
    load_config, save_config, load_asin_data, save_asin_data,
    fetch_and_save, get_summary, add_asin as scraper_add_asin
)

DATA_DIR = Path(__file__).parent / "data"
PORT = 8932


class APIHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler with API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def log_message(self, format, *args):
        """Custom log format."""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}", file=sys.stderr)
        except Exception:
            pass

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # Strip query string for all requests so static file serving works
        parsed = urlparse(self.path)
        clean_path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if clean_path == '/api/summary':
            self._json_response(get_summary())
            return

        if clean_path == '/api/config':
            self._json_response(load_config())
            return

        if clean_path.startswith('/api/data/'):
            asin = clean_path.split('/')[-1].split('.')[0]
            data = load_asin_data(asin)
            self._json_response(data)
            return

        if clean_path == '/api/refresh':
            use_sample = params.get('sample', ['0'])[0] == '1'
            try:
                from scraper import run_all
                run_all(use_sample=use_sample)
                self._json_response({"status": "ok", "message": "Data refreshed"})
            except Exception as e:
                self._json_response({"status": "error", "message": str(e)}, 500)
            return

        # Serve static files (preserve self.path without query string)
        self.path = clean_path
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                # Try form-encoded
                try:
                    from urllib.parse import parse_qs
                    body = {k: v[0] if len(v) == 1 else v 
                            for k, v in parse_qs(raw.decode()).items()}
                except:
                    pass

        if path == '/api/add':
            asin = body.get('asin', '').strip().upper()
            marketplace = body.get('marketplace', 'amazon.us')
            name = body.get('name', '')

            if not asin:
                self._json_response({"status": "error", "message": "ASIN required"}, 400)
                return

            config = load_config()
            if any(e['asin'] == asin and e['marketplace'] == marketplace for e in config['asins']):
                self._json_response({"status": "error", "message": "ASIN already exists"}, 409)
                return

            # Use scraper to add ASIN (creates empty data, tries real fetch)
            success = scraper_add_asin(asin, marketplace, name)

            if success:
                self._json_response({"status": "ok", "asin": asin})
            else:
                self._json_response({"status": "error", "message": "Failed to add ASIN"}, 500)

        elif path == '/api/remove':
            asin = body.get('asin', '')
            if not asin:
                self._json_response({"status": "error", "message": "ASIN required"}, 400)
                return

            config = load_config()
            config['asins'] = [e for e in config['asins'] if e['asin'] != asin]
            save_config(config)
            self._json_response({"status": "ok", "message": f"Removed {asin}"})

        elif path == '/api/refresh':
            try:
                from scraper import run_all
                run_all()
                self._json_response({"status": "ok", "message": "Data refreshed"})
            except Exception as e:
                self._json_response({"status": "error", "message": str(e)}, 500)

        else:
            self._json_response({"status": "error", "message": "Not found"}, 404)

    def do_PUT(self):
        """Handle PUT requests for updating config files."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except:
                pass

        # Allow updating config.json via PUT
        if path == '/data/config.json':
            try:
                save_config(body)
                self._json_response({"status": "ok"})
            except Exception as e:
                self._json_response({"status": "error", "message": str(e)}, 500)
        else:
            self._json_response({"status": "error", "message": "Not allowed"}, 405)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/remove/'):
            asin = path.split('/')[-1]
            config = load_config()
            config['asins'] = [e for e in config['asins'] if e['asin'] != asin]
            save_config(config)
            self._json_response({"status": "ok", "message": f"Removed {asin}"})
        else:
            self._json_response({"status": "error", "message": "Not found"}, 404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))


def main():
    # Set stdout encoding for Windows
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print(f"""
============================================
       Amazon ASIN Monitor Server
============================================
  Dashboard:  http://localhost:{PORT}
  API:        http://localhost:{PORT}/api/
  Press Ctrl+C to stop
============================================
""")

    server = HTTPServer(('0.0.0.0', PORT), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped")
        server.shutdown()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Share server with short URL routing for video sharing.

Routes /v/<key> to video folders using .share_registry.json.
Supports range requests for video seeking.

Usage:
    python3 share_server.py <share_root> [--port <port>]
"""

import sys
import os
import json
import argparse
import socket
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler


MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".vtt": "text/vtt; charset=utf-8",
    ".srt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".css": "text/css",
    ".js": "application/javascript",
}

REGISTRY_FILE = ".share_registry.json"


def load_registry(share_root):
    path = os.path.join(share_root, REGISTRY_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def guess_type(path):
    ext = os.path.splitext(path)[1].lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


class ShareHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urllib.parse.unquote(self.path)

        # Only serve /v/<key> routes
        if not path.startswith("/v/"):
            self.send_error(404, "Not found")
            return

        rest = path[3:]  # strip "/v/"
        parts = rest.split("/", 1)
        key = parts[0]

        if not key:
            self.send_error(404, "Not found")
            return

        registry = load_registry(self.server.share_root)
        if key not in registry:
            self.send_error(404, "Not found")
            return

        folder = registry[key]["folder"]
        folder_path = os.path.join(self.server.share_root, folder)

        if len(parts) == 1:
            # No trailing slash — redirect so relative URLs resolve correctly
            self.send_response(301)
            self.send_header("Location", "/v/" + key + "/")
            self.end_headers()
            return
        elif parts[1] == "":
            # Trailing slash — serve index.html
            file_path = os.path.join(folder_path, "index.html")
        else:
            # Serve requested file — prevent path traversal
            filename = parts[1]
            if ".." in filename or filename.startswith("/"):
                self.send_error(403, "Forbidden")
                return
            file_path = os.path.join(folder_path, filename)

        if not os.path.isfile(file_path):
            self.send_error(404, "Not found")
            return

        # Check for range request
        range_header = self.headers.get("Range")
        if range_header:
            self._serve_range(file_path, range_header)
        else:
            self._serve_full(file_path)

    def _serve_full(self, file_path):
        file_size = os.path.getsize(file_path)
        self.send_response(200)
        self.send_header("Content-Type", guess_type(file_path))
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _serve_range(self, file_path, range_header):
        file_size = os.path.getsize(file_path)
        try:
            range_spec = range_header.replace("bytes=", "").strip()
            parts = range_spec.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            self.send_response(206)
            self.send_header("Content-Type", guess_type(file_path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            self.send_error(500)

    def do_HEAD(self):
        path = urllib.parse.unquote(self.path)
        if not path.startswith("/v/"):
            self.send_error(404)
            return

        rest = path[3:]
        parts = rest.split("/", 1)
        key = parts[0]
        registry = load_registry(self.server.share_root)
        if key not in registry:
            self.send_error(404)
            return

        folder = registry[key]["folder"]
        if len(parts) == 1:
            self.send_response(301)
            self.send_header("Location", "/v/" + key + "/")
            self.end_headers()
            return
        elif parts[1] == "":
            file_path = os.path.join(self.server.share_root, folder, "index.html")
        else:
            file_path = os.path.join(self.server.share_root, folder, parts[1])

        if os.path.isfile(file_path):
            self.send_response(200)
            self.send_header("Content-Type", guess_type(file_path))
            self.send_header("Content-Length", str(os.path.getsize(file_path)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
        else:
            self.send_error(404)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logging


def find_free_port(start=8080, max_attempts=20):
    for port in range(start, start + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Share server with short URL routing")
    parser.add_argument("share_root", help="Root directory containing video folders")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    args = parser.parse_args()

    if not os.path.isdir(args.share_root):
        print(f"Error: {args.share_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    port = find_free_port(args.port)
    if port is None:
        print(f"Error: no free port found starting from {args.port}", file=sys.stderr)
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", port), ShareHandler)
    server.share_root = os.path.abspath(args.share_root)

    print(f"Serving {args.share_root} on http://localhost:{port}", flush=True)
    print(f"PORT={port}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()

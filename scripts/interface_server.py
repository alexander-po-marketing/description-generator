"""Minimal HTTP server to bridge the static interface with the CLI wrapper.

The server exposes a small JSON API:
- GET /api/health -> {"status": "ok"}
- POST /api/run    -> executes scripts/run_pipeline.py with provided arguments

Run with:
    python scripts/interface_server.py --port 8000

This keeps dependencies to the Python standard library to make local testing
simple. CORS headers are intentionally permissive so the static UI can be
opened from the filesystem or any localhost port.
"""
from __future__ import annotations

import json
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "scripts" / "run_pipeline.py"
DEFAULT_OUTPUTS = {
    "database_json": str(ROOT / "outputs" / "database.json"),
    "descriptions_json": str(ROOT / "outputs" / "api_descriptions.json"),
    "descriptions_xml": str(ROOT / "outputs" / "api_descriptions.xml"),
}


class InterfaceHandler(BaseHTTPRequestHandler):
    server_version = "InterfaceServer/0.1"

    def _set_headers(self, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return

        self._set_headers(HTTPStatus.NOT_FOUND)
        self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Unknown endpoint"}).encode())
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode())
        except json.JSONDecodeError:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        args = self._build_args(payload)
        result, returncode = self._invoke_pipeline(args)
        status = HTTPStatus.OK if returncode == 0 else HTTPStatus.INTERNAL_SERVER_ERROR
        self._set_headers(status)
        self.wfile.write(json.dumps(result).encode())

    def _build_args(self, payload: Dict[str, str]) -> Tuple[str, ...]:
        args = ["python", str(PIPELINE)]
        args.extend(["--xml-path", payload.get("xmlPath", "")])
        args.extend(["--database-json", payload.get("databaseJson", DEFAULT_OUTPUTS["database_json"])])
        args.extend(["--descriptions-json", payload.get("descriptionsJson", DEFAULT_OUTPUTS["descriptions_json"])])
        args.extend(["--descriptions-xml", payload.get("descriptionsXml", DEFAULT_OUTPUTS["descriptions_xml"])])

        if payload.get("validDrugIds"):
            args.extend(["--valid-drug-ids", payload["validDrugIds"]])
        if payload.get("validDrugFile"):
            args.extend(["--valid-drug-file", payload["validDrugFile"]])
        if payload.get("maxDrugs"):
            args.extend(["--max-drugs", str(payload["maxDrugs"])])
        if payload.get("logLevel"):
            args.extend(["--log-level", payload["logLevel"]])
        if payload.get("apiKey"):
            args.extend(["--api-key", payload["apiKey"]])
        if payload.get("apiOrg"):
            args.extend(["--api-org", payload["apiOrg"]])
        if payload.get("apiProject"):
            args.extend(["--api-project", payload["apiProject"]])
        if payload.get("model"):
            args.extend(["--model", payload["model"]])
        if payload.get("temperature") is not None:
            args.extend(["--temperature", str(payload["temperature"])])
        if payload.get("maxTokens"):
            args.extend(["--max-tokens", str(payload["maxTokens"])])
        if payload.get("overwrite"):
            args.append("--overwrite")
        if payload.get("dryRun"):
            args.append("--dry-run")
        if payload.get("logFile"):
            args.extend(["--log-file", payload["logFile"]])
        if payload.get("cacheDir"):
            args.extend(["--cache-dir", payload["cacheDir"]])
        return tuple(args)

    def _invoke_pipeline(self, args: Tuple[str, ...]) -> Tuple[Dict[str, object], int]:
        try:
            completed = subprocess.run(args, capture_output=True, text=True, check=False)
            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            try:
                result = json.loads(stdout) if stdout else {}
            except json.JSONDecodeError:
                result = {"raw_output": stdout}

            if stderr:
                result["stderr"] = stderr
            result.setdefault("command", " ".join(args))
            result.setdefault("returncode", completed.returncode)
            return result, completed.returncode
        except FileNotFoundError:
            return {"error": "Pipeline script not found.", "command": " ".join(args)}, 1


def run_server(port: int) -> None:
    server = HTTPServer(("", port), InterfaceHandler)
    print(f"Interface server listening on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the DrugBank UI helper API")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the HTTP server")
    args = parser.parse_args()
    run_server(args.port)

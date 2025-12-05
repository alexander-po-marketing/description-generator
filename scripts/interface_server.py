"""Serve the interactive UI and forward requests to the CLI pipeline.

Endpoints
---------
- GET /api/files: return repository-relative files for common extensions so the UI
  can suggest local paths.
- POST /api/run: validate paths, prepare environment variables for OpenAI
  credentials, and launch ``src/main.py`` using ``subprocess``.
- POST /api/sections: generate section-level HTML snippets from ``api_pages.json``
  without rerunning the full pipeline.

The server intentionally keeps all paths inside the repository root to avoid
accidental traversal into the host machine while providing a simple bridge
between the browser UI and the existing Python CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Dict, Iterable
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = REPO_ROOT / "interface"

DIRECTORIES: Dict[str, Path] = {
    "inputs": REPO_ROOT / "inputs",
    "outputs": REPO_ROOT / "outputs",
    "logs": REPO_ROOT / "logs",
    "cache": REPO_ROOT / "cache",
}


def ensure_layout() -> None:
    """Create the expected folder layout if it does not exist."""

    for path in DIRECTORIES.values():
        path.mkdir(parents=True, exist_ok=True)


def discover_files(extensions: Iterable[str]) -> Dict[str, list[str]]:
    """Return repo-relative file paths grouped by extension."""

    results: Dict[str, list[str]] = {ext: [] for ext in extensions}
    search_roots = list(DIRECTORIES.values()) + [REPO_ROOT]
    for ext in extensions:
        pattern = f"**/*.{ext}"
        seen = set()
        for root in search_roots:
            for match in root.glob(pattern):
                if match.is_file():
                    relative = str(match.relative_to(REPO_ROOT))
                    if relative not in seen:
                        results[ext].append(relative)
                        seen.add(relative)
        results[ext].sort()
    return results


def resolve_path(value: str | None, default_dir: Path | None = None) -> Path | None:
    """Normalize a path and ensure it remains inside the repository root."""

    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        base = default_dir or REPO_ROOT
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(REPO_ROOT):
        raise ValueError(f"Path {candidate} is outside the repository root")
    return candidate


def build_command(options: dict, template_path: Path | None = None) -> list[str]:
    """Assemble the CLI command from UI-provided options."""

    xml_path = resolve_path(options.get("xmlPath"), DIRECTORIES["inputs"])
    if not xml_path or not xml_path.exists():
        raise FileNotFoundError("DrugBank XML path is missing or does not exist")

    database_json = resolve_path(options.get("databasePath") or "outputs/database.json", DIRECTORIES["outputs"])
    page_models_json = resolve_path(options.get("pageModelsJson") or "outputs/api_pages.json", DIRECTORIES["outputs"])
    import_json = resolve_path(options.get("importJson") or "outputs/api_pages_import.json", DIRECTORIES["outputs"])
    preview_html = resolve_path("outputs/api_pages_preview.html", DIRECTORIES["outputs"])

    for path in (database_json, page_models_json, import_json, preview_html):
        if path and path.exists() and not (options.get("overwrite") or options.get("continueExisting")):
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    command = [
        sys.executable,
        "-m", "src.main",
        "--xml-path",
        str(xml_path),
        "--output-database-json",
        str(database_json),
        "--output-page-models-json",
        str(page_models_json),
        "--output-import-json",
        str(import_json),
        "--log-level",
        options.get("logLevel", "INFO"),
    ]

    valid_drugs_value = options.get("validIdsFile") or options.get("validIds")
    if valid_drugs_value:
        valid_drugs_path = resolve_path(valid_drugs_value, DIRECTORIES["inputs"])
        command.extend(["--valid-drugs", str(valid_drugs_path) if valid_drugs_path else valid_drugs_value])

    if options.get("maxDrugs"):
        command.extend(["--max-drugs", str(options["maxDrugs"])])

    if template_path:
        command.extend(["--template-definition", str(template_path)])

    return command


def build_section_command(options: dict) -> list[str]:
    """Build the command to render section-level HTML snippets."""

    page_models_json = resolve_path(
        options.get("pageModelsJson") or "outputs/api_pages.json", DIRECTORIES["outputs"]
    )
    if not page_models_json or not page_models_json.exists():
        raise FileNotFoundError("Page models JSON is missing; run the main pipeline first")

    sections_output = resolve_path(
        options.get("sectionsOutput") or "outputs/section_html/section_blocks.json",
        DIRECTORIES["outputs"],
    )
    if sections_output and sections_output.exists() and not options.get("overwrite"):
        raise FileExistsError(f"Refusing to overwrite existing file: {sections_output}")

    return [
        sys.executable,
        "-m",
        "src.section_renderer",
        "--input",
        str(page_models_json),
        "--output",
        str(sections_output),
    ]


def persist_template_definition(payload: dict | None) -> Path | None:
    if not payload:
        return None
    destination = DIRECTORIES["cache"] / "template_definition.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def build_env(options: dict) -> dict:
    """Prepare environment variables for the CLI process."""

    env = os.environ.copy()
    mapping = {
        "apiKey": "OPENAI_API_KEY",
        "orgId": "OPENAI_ORG",
        "projectId": "OPENAI_PROJECT",
        "model": "OPENAI_MODEL",
        "summaryModel": "OPENAI_SUMMARY_MODEL",
    }
    for source, target in mapping.items():
        value = options.get(source)
        if value:
            env[target] = str(value)
    return env


class InterfaceRequestHandler(SimpleHTTPRequestHandler):
    """Serve static files alongside API endpoints for the UI."""

    def _set_headers(self, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # pragma: no cover - handled by browsers
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/api/preview"):
            self.handle_preview()
            return
        if self.path.startswith("/api/files"):
            self.handle_file_suggestions()
            return
        return super().do_GET()

    def handle_file_suggestions(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        extensions = []
        for ext in (query.get("ext") or [""])[0].split(","):
            if ext:
                extensions.append(ext)
        extensions = extensions or ["xml", "json", "log", "txt"]
        payload = discover_files(extensions)
        self._set_headers()
        self.wfile.write(json.dumps(payload).encode())

    def handle_preview(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        preview_path = (query.get("path") or [None])[0]
        try:
            resolved = resolve_path(preview_path, DIRECTORIES["outputs"])
        except ValueError as exc:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return

        if not resolved or not resolved.exists():
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Preview HTML not found"}).encode())
            return

        content = resolved.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if self.path == "/api/run":
            self.handle_run()
            return
        if self.path == "/api/sections":
            self.handle_sections()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def handle_run(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        template_path = persist_template_definition(payload.get("templateDefinition"))
        try:
            command = build_command(payload, template_path=template_path)
            env = build_env(payload)
        except (FileNotFoundError, FileExistsError, ValueError) as exc:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        except Exception as exc:  # pragma: no cover - unexpected parsing error
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return

        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        status = HTTPStatus.OK if completed.returncode == 0 else HTTPStatus.BAD_REQUEST
        self._set_headers(status)
        response = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        self.wfile.write(json.dumps(response).encode())

    def handle_sections(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        try:
            command = build_section_command(payload)
            env = build_env(payload)
        except (FileNotFoundError, FileExistsError, ValueError) as exc:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        except Exception as exc:  # pragma: no cover - unexpected parsing error
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return

        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        status = HTTPStatus.OK if completed.returncode == 0 else HTTPStatus.BAD_REQUEST
        self._set_headers(status)
        response = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        self.wfile.write(json.dumps(response).encode())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local web server for the DrugBank pipeline UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="Port for the HTTP server")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ensure_layout()
    args = parse_args(list(argv) if argv is not None else None)
    handler = lambda *h_args, **h_kwargs: InterfaceRequestHandler(*h_args, directory=str(STATIC_ROOT), **h_kwargs)
    with HTTPServer((args.host, args.port), handler) as server:
        print(f"Serving interface on http://{args.host}:{args.port} (root: {STATIC_ROOT})")
        server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual server startup
    raise SystemExit(main())

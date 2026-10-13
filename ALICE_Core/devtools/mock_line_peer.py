#!/usr/bin/env python3
"""Tiny local LINE API peer and signed webhook client for manual Core checks."""

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


CONTENTS: dict[str, bytes] = {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes = b"{}", content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        match = re.fullmatch(r"/mock/content/([^/]+)", path)
        if match:
            CONTENTS[match.group(1)] = body
            self._send(201)
            return
        # LINE SDK response models require one sent-message record per message.
        print(f"[mock LINE] POST {path}: {body[:500].decode('utf-8', 'replace')}", flush=True)
        if path.endswith("/message/reply") or path.endswith("/message/push"):
            try:
                message_count = len(json.loads(body).get("messages", []))
            except (json.JSONDecodeError, TypeError):
                message_count = 1
            response = json.dumps({
                "sentMessages": [{"id": f"mock-{uuid4()}"} for _ in range(max(message_count, 1))]
            }).encode()
            self._send(200, response)
            return
        self._send(200)

    def do_GET(self):
        path = urlparse(self.path).path
        match = re.fullmatch(r"/v2/bot/message/([^/]+)/content", path)
        if match:
            content = CONTENTS.get(match.group(1))
            if content is None:
                self._send(404, b"content not found", "text/plain")
            else:
                self._send(200, content, "application/octet-stream")
            return
        match = re.fullmatch(r"/v2/bot/profile/([^/]+)", path)
        if match:
            body = json.dumps({"userId": match.group(1), "displayName": "Local Mock User"}).encode()
            self._send(200, body)
            return
        self._send(200)

    def do_DELETE(self):
        print(f"[mock LINE] DELETE {urlparse(self.path).path}", flush=True)
        self._send(200)

    def log_message(self, fmt, *args):
        pass


def send_event(core: str, secret: str, event: dict):
    body = json.dumps({"destination": "U_LOCAL_MOCK", "events": [event]}, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    req = urllib.request.Request(
        core.rstrip("/") + "/callback",
        data=body,
        headers={"Content-Type": "application/json", "X-Line-Signature": signature},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            print(f"Core replied HTTP {response.status}: {response.read().decode()}")
    except urllib.error.HTTPError as exc:
        print(f"Core replied HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}")
        raise


def event_base(user_id: str, reply_token: str):
    return {"timestamp": 0, "source": {"type": "user", "userId": user_id}, "replyToken": reply_token, "mode": "active"}


def _read_data_dir_from_env_file(env_file: Path) -> str | None:
    """Read only ALICE_DATA_DIR without requiring python-dotenv in the mock client."""
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key.strip() != "ALICE_DATA_DIR":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value
    return None


def _default_workspace_dir() -> Path:
    project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2])).expanduser()
    if not project_root.is_absolute():
        project_root = Path.cwd() / project_root
    project_root = project_root.resolve()

    data_dir = os.getenv("ALICE_DATA_DIR")
    if data_dir is None:
        data_dir = _read_data_dir_from_env_file(project_root / "ALICE_Core" / ".env")
    if data_dir is None:
        data_dir = "data"

    resolved_data_dir = Path(data_dir).expanduser()
    if not resolved_data_dir.is_absolute():
        resolved_data_dir = project_root / resolved_data_dir
    return resolved_data_dir / "runtime" / "workspaces"


def _find_job(workspace_dir: Path, user_id: str, filename: str, submitted_at: float):
    matches = []
    try:
        job_files = workspace_dir.glob("job_*/job.json")
        for job_file in job_files:
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
                created_at = datetime.fromisoformat(job["created_at"]).timestamp()
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            original_name = job.get("input_metadata", {}).get("original_name")
            if (
                job.get("user_id") == user_id
                and original_name == filename
                and created_at >= submitted_at - 3
            ):
                matches.append((created_at, job_file, job))
    except OSError:
        pass
    return max(matches, key=lambda item: item[0])[1:] if matches else None


def wait_for_transcription(
    workspace_dir: Path, user_id: str, filename: str, submitted_at: float, timeout: float
) -> int:
    deadline = time.monotonic() + timeout
    job_file = None
    job = None

    while time.monotonic() < deadline:
        match = _find_job(workspace_dir, user_id, filename, submitted_at)
        if match:
            job_file, job = match
            if job.get("status") in {"COMPLETED", "FAILED"}:
                break
        time.sleep(1)

    if not job_file or not job or job.get("status") not in {"COMPLETED", "FAILED"}:
        print(
            f"Timed out waiting for transcription ({timeout:g}s). "
            f"Check job.json under {workspace_dir}.",
            flush=True,
        )
        return 1

    job_id = job.get("job_id", job_file.parent.name)
    if job.get("status") == "FAILED":
        print(f"Transcription failed: {job_id}: {job.get('error_message') or 'unknown error'}", flush=True)
        return 1

    transcript_path = job_file.parent / "transcript" / "transcript.txt"
    if not transcript_path.is_file():
        print(f"Job completed but transcript file is missing: {transcript_path}", flush=True)
        return 1

    print(f"Transcription completed: {job_id}", flush=True)
    print("----- transcript.txt -----", flush=True)
    print(transcript_path.read_text(encoding="utf-8").rstrip(), flush=True)
    print("--------------------------", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", default="http://127.0.0.1:8010", help="Mock LINE API base URL")
    parser.add_argument("--core", default="http://127.0.0.1:8000", help="ALICE_Core base URL")
    parser.add_argument("--user", default="U_LOCAL_MOCK_USER", help="Stable mock LINE user ID")
    parser.add_argument("--secret", default=os.getenv("CHANNEL_SECRET"), help="Same channel secret configured in Core")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the local LINE API mock")
    sub.add_parser("follow", help="Simulate a LINE follow event")
    text_parser = sub.add_parser("text", help="Send a text message (for example invite code, then 文字起こし)")
    text_parser.add_argument("text")
    file_parser = sub.add_parser(
        "file", help="Upload audio through LINE mock and wait for the transcript"
    )
    file_parser.add_argument("path", type=Path)
    file_parser.add_argument(
        "--timeout", type=float, default=1800,
        help="Seconds to wait for transcription completion (default: 1800)",
    )
    file_parser.add_argument(
        "--workspace-dir", type=Path, default=None,
        help="Workspace directory to poll (defaults to ALICE_DATA_DIR/runtime/workspaces)",
    )
    args = parser.parse_args()

    if args.command == "serve":
        host = urlparse(args.peer).hostname or "127.0.0.1"
        port = urlparse(args.peer).port or 8010
        print(f"Mock LINE API listening on http://{host}:{port}")
        ThreadingHTTPServer((host, port), Handler).serve_forever()
        return
    if not args.secret:
        parser.error("--secret or CHANNEL_SECRET is required")

    token = str(uuid4())
    base = event_base(args.user, token)
    if args.command == "follow":
        event = {**base, "type": "follow", "follow": {"isUnblocked": True}}
    elif args.command == "text":
        event = {**base, "type": "message", "message": {"id": str(uuid4()), "type": "text", "text": args.text}}
    else:
        path = args.path.expanduser().resolve()
        if not path.is_file():
            parser.error(f"File does not exist: {path}")
        if args.timeout <= 0:
            parser.error("--timeout must be greater than 0")
        message_id = str(uuid4())
        req = urllib.request.Request(
            args.peer.rstrip("/") + f"/mock/content/{message_id}",
            data=path.read_bytes(),
            headers={"Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            pass
        event = {**base, "type": "message", "message": {"id": message_id, "type": "file", "fileName": path.name, "fileSize": path.stat().st_size}}
        submitted_at = time.time()
    send_event(args.core, args.secret, event)
    if args.command == "file":
        workspace_dir = args.workspace_dir.expanduser() if args.workspace_dir else _default_workspace_dir()
        if not workspace_dir.is_absolute():
            workspace_dir = Path.cwd() / workspace_dir
        return wait_for_transcription(
            workspace_dir.resolve(), args.user, path.name, submitted_at, args.timeout
        )


if __name__ == "__main__":
    raise SystemExit(main())

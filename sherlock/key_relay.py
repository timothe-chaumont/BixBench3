#!/usr/bin/env python3
"""Per-job OpenAI relay that switches API keys when one runs out, without interrupting the run.

Runs inside the Slurm job (started by run_job.sbatch, killed with it), on 127.0.0.1 only.
Inspect, the judge and the gateway adjudicator talk to it through OPENAI_BASE_URL with a random
per-job token as OPENAI_API_KEY; real keys never enter the run directory or any log.

Keys: ~/.bixbench3_secrets, used in this order (re-read on every switch, so keys added later count):
    OPENAI_API_KEY, OPENAI_API_KEY_2, OPENAI_API_KEY_3, ...
A key is retired when OpenAI answers 429 `insufficient_quota` or 401 (invalid / revoked key). The
request is then replayed with the next key, so the caller only sees the successful answer. Retired
key NAMES (never values) are shared by all jobs in ~/.bixbench3_keystate.json, so new jobs start on
the current key. To re-enable a refilled key, delete its name from that file.
Ordinary rate limits (429 rate_limit_exceeded, many runs sharing one key) are absorbed here: the
relay waits as OpenAI's reset headers say and replays the request, for up to RATE_WAIT_BUDGET seconds
per request, before passing the 429 to the caller (Inspect then applies its own retries on top).
Server errors pass through unchanged.

usage: key_relay.py PORT   (token in env BB3_RELAY_TOKEN; log lines on stdout)
"""

from __future__ import annotations

import fcntl
import http.client
import json
import os
import random
import re
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

SECRETS = Path(os.environ.get("BB3_SECRETS_FILE", str(Path.home() / ".bixbench3_secrets")))
STATE = Path(os.environ.get("BB3_KEYSTATE_FILE", str(Path.home() / ".bixbench3_keystate.json")))
UPSTREAM = urlsplit(os.environ.get("BB3_RELAY_UPSTREAM", "https://api.openai.com"))
ROTATION_LOG = os.environ.get("BB3_ROTATION_LOG")  # optional shared log of key switches (names only)
TOKEN = os.environ["BB3_RELAY_TOKEN"]
JOB = os.environ.get("SLURM_JOB_ID", "?")
HOP = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding",
       "proxy-connection", "te", "upgrade"}


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} job {JOB} {message}"
    print(line, flush=True)
    if ROTATION_LOG and ("retired" in message or "ALL KEYS" in message):
        try:
            with open(ROTATION_LOG, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def load_keys() -> list[tuple[str, str]]:
    keys: dict[str, str] = {}
    for raw in SECRETS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(?:export\s+)?(OPENAI_API_KEY(?:_(\d+))?)\s*=\s*(.*)$", raw)
        if match and match.group(3).strip().strip("'\""):
            keys[match.group(1)] = match.group(3).strip().strip("'\"")
    order = lambda name: 1 if name == "OPENAI_API_KEY" else int(name.rsplit("_", 1)[1])  # noqa: E731
    return sorted(keys.items(), key=lambda item: order(item[0]))


def _locked_state(update=None) -> list[str]:
    STATE.touch(mode=0o600, exist_ok=True)
    with STATE.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            retired = json.loads(handle.read() or "{}").get("retired", [])
        except ValueError:
            retired = []
        if update and update not in retired:
            retired.append(update)
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"retired": retired, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        return retired


def current_key() -> tuple[str, str] | None:
    retired = set(_locked_state())
    for name, value in load_keys():
        if name not in retired:
            return name, value
    return None


RATE_WAIT_BUDGET = float(os.environ.get("BB3_RATE_WAIT_BUDGET", "300"))
_rate_stats = {"waits": 0, "seconds": 0.0, "last_log": 0.0}


def _duration(text: str | None) -> float | None:
    """'1.5s', '120ms', '6m0s', '2' -> seconds."""
    if not text:
        return None
    total, found = 0.0, False
    for number, unit in re.findall(r"([0-9.]+)\s*(ms|s|m|h)?", text):
        found = True
        total += float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "": 1}[unit or ""]
    return total if found else None


def rate_limit_wait(headers: list[tuple[str, str]], attempt: int) -> float:
    h = {k.lower(): v for k, v in headers}
    ms = h.get("retry-after-ms")
    hinted = float(ms) / 1000 if ms and ms.replace(".", "").isdigit() else _duration(h.get("retry-after"))
    if hinted is None:
        resets = [_duration(h.get(k)) for k in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")]
        resets = [r for r in resets if r is not None]
        hinted = max(resets) if resets else None
    backoff = min(30.0, 2.0 * (2 ** attempt))
    wait = max(hinted or 0.0, 1.0) if hinted is not None else backoff
    return min(60.0, wait) * (1 + 0.25 * random.random())


def key_exhausted(status: int, body: bytes) -> bool:
    if status == 401:
        return True
    return status == 429 and b"insufficient_quota" in body


class Relay(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # silence per-request logs
        pass

    def _forward(self) -> None:
        if self.headers.get("Authorization", "") != f"Bearer {TOKEN}":
            self.send_error(403)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers["Host"] = UPSTREAM.netloc
        if body or self.command in ("POST", "PUT", "PATCH"):
            headers["Content-Length"] = str(len(body))
        tried: list[str] = []
        waited, rate_attempt = 0.0, 0
        status, reason, resp_headers = 429, "Too Many Requests", [("Content-Type", "application/json")]
        err_body = b'{"error":{"message":"all configured OpenAI keys are exhausted","type":"insufficient_quota","code":"insufficient_quota"}}'
        while True:
            key = current_key()
            if key is None:
                log(f"ALL KEYS EXHAUSTED (tried {tried}); passing the error to the caller")
                self._reply_raw(status, reason, resp_headers, err_body)
                return
            name, value = key
            conn_cls = http.client.HTTPSConnection if UPSTREAM.scheme == "https" else http.client.HTTPConnection
            conn = conn_cls(UPSTREAM.hostname, UPSTREAM.port, timeout=3600)
            try:
                conn.request(self.command, self.path, body=body, headers={**headers, "Authorization": f"Bearer {value}"})
                resp = conn.getresponse()
            except OSError as error:
                conn.close()
                self.send_error(502, f"upstream unreachable: {type(error).__name__}")
                return
            if resp.status in (401, 429):
                err_body = resp.read()
                status, reason, resp_headers = resp.status, resp.reason, resp.getheaders()
                conn.close()
                if key_exhausted(resp.status, err_body):
                    tried.append(name)
                    _locked_state(update=name)
                    log(f"key {name} retired (HTTP {resp.status}); switching to the next key and replaying the request")
                    continue
                if resp.status == 429 and waited < RATE_WAIT_BUDGET:
                    pause = min(rate_limit_wait(resp_headers, rate_attempt), RATE_WAIT_BUDGET - waited + 1)
                    rate_attempt += 1
                    waited += pause
                    _rate_stats["waits"] += 1
                    _rate_stats["seconds"] += pause
                    now = time.time()
                    if now - _rate_stats["last_log"] > 300:
                        _rate_stats["last_log"] = now
                        log(f"rate limited on {name}: {_rate_stats['waits']} waits, {_rate_stats['seconds']:.0f}s total so far (absorbed, request replayed)")
                    time.sleep(pause)
                    continue
                if resp.status == 429:
                    log(f"rate limit wait budget ({RATE_WAIT_BUDGET:.0f}s) used up for one request; passing 429 to the caller")
                self._reply_raw(status, reason, resp_headers, err_body)
                return
            self._stream(resp)
            conn.close()
            return

    def _reply_raw(self, status, reason, headers, body: bytes) -> None:
        self.send_response(status, reason)
        for k, v in headers:
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, resp) -> None:
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True

    do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = _forward


def main() -> None:
    port = int(sys.argv[1])
    names = [name for name, _ in load_keys()]
    key = current_key()
    log(f"relay on 127.0.0.1:{port}, keys configured: {names}, starting with: {key[0] if key else None}")
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), Relay).serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""bixdash web server — serves the dashboard and the run snapshots.

Source of snapshots:
  --source gs://bixbench3-task11-jex20-results/_dashboard   (needs google-cloud-storage + ADC)
  --source ./demo_data                                       (local folder, same layout)

Layout expected under the source:  <run_id>/{meta.json,latest.json,history.jsonl}

Optional shared password: set BIXDASH_TOKEN; open http://host:8050/?token=XXX once
(a cookie is set). Read-only: the server never writes to the bucket.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
CACHE_TTL = 30.0


class Source:
    def __init__(self, uri: str):
        self.uri = uri.rstrip("/")
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}
        if self.uri.startswith("gs://"):
            from google.cloud import storage  # lazy import

            bucket, _, prefix = self.uri[5:].partition("/")
            self.bucket = storage.Client().bucket(bucket)
            self.prefix = (prefix + "/") if prefix else ""
        else:
            self.root = Path(self.uri)

    def _get(self, key: str, loader):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        value = loader()
        with self._lock:
            self._cache[key] = (time.time(), value)
        return value

    def _read(self, rel: str) -> str | None:
        if self.uri.startswith("gs://"):
            blob = self.bucket.blob(self.prefix + rel)
            try:
                return blob.download_as_text()
            except Exception:
                return None
        p = self.root / rel
        return p.read_text(encoding="utf-8") if p.exists() else None

    def run_ids(self) -> list[str]:
        def load():
            if self.uri.startswith("gs://"):
                ids = set()
                for blob in self.bucket.list_blobs(prefix=self.prefix):
                    rest = blob.name[len(self.prefix):]
                    if rest.endswith("/meta.json"):
                        ids.add(rest.rsplit("/", 1)[0])
                return sorted(ids)
            return sorted(p.parent.name for p in self.root.glob("*/meta.json"))
        return self._get("ids", load)

    def comparison_budget(self, latest: dict, run_id: str) -> dict | None:
        """Expose missing terminal budgets as explicitly labelled observed lower bounds.

        Keep raw latest intact: an old live snapshot is not a final usage total.
        """
        if not latest.get("score_is_final"):
            return None
        exact_text = self._read(f"{run_id}/final_usage.json")
        if exact_text:
            exact = json.loads(exact_text)
            fields = ("cost_usd", "n_model_calls", "tokens_total", "elapsed_s")
            if exact.get("source") == "final_inspect_eval" and all(
                isinstance(exact.get(k), (int, float)) and exact[k] >= 0 for k in fields
            ):
                return {k: exact.get(k) for k in (*fields, "ts")} | {
                    "source": "final_inspect_eval", "is_lower_bound": False}
        if all(latest.get(k) is not None for k in ("cost_usd", "n_model_calls")) and (
            latest.get("tokens") is not None or latest.get("tokens_total") is not None
        ):
            return None
        candidates = [h for h in self.history(run_id)
                      if all(h.get(k) is not None for k in
                             ("cost_usd", "n_model_calls", "tokens_total", "elapsed_s"))]
        if not candidates:
            return None
        observed = max(candidates, key=lambda h: h["elapsed_s"])
        return {k: observed.get(k) for k in
                ("cost_usd", "n_model_calls", "tokens_total", "elapsed_s", "ts")} | {
                    "is_lower_bound": True, "source": "last_live_snapshot"}

    def run(self, run_id: str) -> dict:
        def load():
            meta = json.loads(self._read(f"{run_id}/meta.json") or "{}")
            latest = json.loads(self._read(f"{run_id}/latest.json") or "{}")
            return {"run_id": run_id, "meta": meta, "latest": latest,
                    "comparison_budget": self.comparison_budget(latest, run_id)}
        return self._get(f"run:{run_id}", load)

    def history(self, run_id: str) -> list[dict]:
        def load():
            text = self._read(f"{run_id}/history.jsonl") or ""
            return [json.loads(l) for l in text.splitlines() if l.strip()]
        return self._get(f"hist:{run_id}", load)


def make_handler(source: Source, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter
            pass

        def _authorized(self, query) -> bool:
            if not token:
                return True
            if query.get("token", [""])[0] == token:
                return True
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            return "bixdash" in c and c["bixdash"].value == token

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if not self._authorized(query):
                return self._send(401, b"Unauthorized: open /?token=...", "text/plain")
            extra = {}
            if token and query.get("token"):
                extra["Set-Cookie"] = f"bixdash={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800" + ("; Secure" if os.environ.get("K_SERVICE") else "")
            parts = [p for p in url.path.split("/") if p]
            try:
                if not parts:
                    return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8", extra)
                if parts in (["comparisons"], ["comparisons.html"]):
                    return self._send(200, (HERE / "comparisons.html").read_bytes(), "text/html; charset=utf-8", extra)
                if parts == ["comparisons.js"]:
                    return self._send(200, (HERE / "comparisons.js").read_bytes(), "text/javascript; charset=utf-8")
                if parts == ["api", "runs"]:
                    return self._json([source.run(r) for r in source.run_ids()])
                if len(parts) == 4 and parts[:2] == ["api", "run"] and parts[3] == "history":
                    return self._json(source.history(parts[2]))
            except Exception as error:
                return self._send(500, str(error).encode(), "text/plain")
            self._send(404, b"not found", "text/plain")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--host", default="0.0.0.0" if os.environ.get("K_SERVICE") else "127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8050")))
    args = ap.parse_args()
    public = os.environ.get("BIXDASH_PUBLIC") == "1"
    token = None if public else (os.environ.get("BIXDASH_TOKEN") or None)
    if os.environ.get("K_SERVICE") and not token and not public:
        raise RuntimeError("BIXDASH_TOKEN is required on Cloud Run")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Source(args.source), token))
    print(f"bixdash on http://{args.host}:{args.port}  (source={args.source}, token={'on' if token else 'off'})")
    server.serve_forever()


if __name__ == "__main__":
    main()

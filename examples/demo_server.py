"""演示服务：让示例用例在没有后端时也能跑。

只用标准库。故意保留一个 /api/slow 接口，用来演示 TIMEOUT 的失败归因。
"""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RULES: dict[str, dict] = {}
SEQ = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status: int, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, status: int, code: str, message: str):
        self._send(status, {"code": code, "message": message})

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path == "/api/health":
            return self._send(200, {"status": "ok", "service": "caseforge-demo"})

        if url.path == "/api/slow":
            ms = int((query.get("ms") or ["3000"])[0])
            time.sleep(ms / 1000)
            return self._send(200, {"sleptMs": ms})

        if url.path == "/api/boom":
            return self._error(500, "INTERNAL_ERROR", "演示用的服务端错误")

        if url.path == "/api/metrics/current":
            host = (query.get("hostId") or [None])[0]
            if not host:
                return self._error(400, "INVALID_PARAM", "hostId 必填")
            return self._send(200, {
                "hostId": host,
                "timestamp": int(time.time() * 1000),
                "metrics": {"cpu": 12.5, "mem": 63.2, "disk": 71.0, "net": 1.2},
            })

        if url.path == "/api/alert/rules":
            items = list(RULES.values())
            return self._send(200, {"total": len(items), "items": items})

        prefix = "/api/alert/rules/"
        if url.path.startswith(prefix):
            rule = RULES.get(url.path[len(prefix):])
            if not rule:
                return self._error(404, "RULE_NOT_FOUND", "规则不存在")
            return self._send(200, rule)

        return self._error(404, "NOT_FOUND", f"接口不存在: {url.path}")

    def do_POST(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._error(400, "INVALID_JSON", "请求体不是合法 JSON")

        if url.path == "/api/echo":
            return self._send(200, {"echo": data})

        if url.path != "/api/alert/rules":
            return self._error(404, "NOT_FOUND", f"接口不存在: {url.path}")

        for field in ("name", "metric", "operator", "threshold"):
            if field not in data:
                return self._error(400, "INVALID_PARAM", f"{field} 必填")
        if not isinstance(data["threshold"], (int, float)) or not 0 <= data["threshold"] <= 100:
            return self._error(400, "INVALID_PARAM", "threshold 取值范围 0..100")

        SEQ["n"] += 1
        rule = {
            "id": f"r-{SEQ['n']}",
            "name": data["name"],
            "metric": data["metric"],
            "operator": data["operator"],
            "threshold": data["threshold"],
            "enabled": True,
            "createdAt": int(time.time() * 1000),
        }
        RULES[rule["id"]] = rule
        return self._send(201, rule)

    def do_DELETE(self):
        url = urlparse(self.path)
        prefix = "/api/alert/rules/"
        if not url.path.startswith(prefix):
            return self._error(404, "NOT_FOUND", f"接口不存在: {url.path}")
        rule_id = url.path[len(prefix):]
        if rule_id not in RULES:
            return self._error(404, "RULE_NOT_FOUND", "规则不存在")
        RULES.pop(rule_id)
        return self._send(204, None)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"caseforge demo listening on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

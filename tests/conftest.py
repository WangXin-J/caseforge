"""测试夹具：起一个真实的演示服务，保证集成用例跑的是真 HTTP，不是 mock 对象。"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "examples" / "demo_server.py"), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                if requests.get(f"{url}/api/health", timeout=0.3).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            pytest.fail("演示服务启动超时")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

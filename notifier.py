from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from typing import Any


def send_message(config: dict[str, Any], title: str, text: str) -> None:
    notify_cfg = config.get("notify", {})
    if not notify_cfg.get("enabled", True):
        return

    provider = notify_cfg.get("provider", "serverchan")
    if provider == "serverchan":
        _send_serverchan(notify_cfg, title, text)
        return
    if provider == "openclaw":
        _send_openclaw(notify_cfg.get("openclaw", {}), title, text)
        return
    raise RuntimeError(f"Unsupported notify provider: {provider}")


def _send_serverchan(notify_cfg: dict[str, Any], title: str, text: str):
    env_name = notify_cfg.get("serverchan_sendkey_env", "SERVERCHAN_SENDKEY")
    sendkey = os.getenv(env_name, "")
    if not sendkey:
        raise RuntimeError(f"Missing ServerChan sendkey env: {env_name}")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = urllib.parse.urlencode({"title": title, "desp": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("code") != 0:
        raise RuntimeError(f"ServerChan push failed: {body}")


def _send_openclaw(openclaw_cfg: dict[str, Any], title: str, text: str):
    binary = openclaw_cfg.get("binary", "openclaw")
    channel = openclaw_cfg.get("channel", "").strip()
    target = openclaw_cfg.get("target", "").strip()
    account = openclaw_cfg.get("account", "").strip()
    if not channel or not target or not account:
        raise RuntimeError("OpenClaw notify requires channel, target and account")

    cmd = [
        binary,
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--account",
        account,
        "--message",
        f"{title}\n{text}",
    ]
    proc = subprocess.run(cmd, timeout=30, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"openclaw send failed: rc={proc.returncode}, stderr={stderr}")

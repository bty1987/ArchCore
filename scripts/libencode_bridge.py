"""libencode 实时桥：pywechat_libencode（协议级 4.x）→ ArchCore /api/v1/ingest。

前置：pip install pywechat-libencode（Msky QQ 群 705791428 分发，PyPI 暂无）；
微信 4.1.8.67 已登录。用法：
    python scripts/libencode_bridge.py [--version 4.1.8.67] [--allow-dm]

- 白名单从服务端 /ingest/whitelist 拉取（60s 刷新）；
- svr_id = libencode 消息 id（字段名做防御性多候选），与解密轨去重并存；
- 群消息发送者在 content 前缀（"wxid:\n正文"），与 padlocal/wxhook 同语义。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "collector" / "src"))

from archcore_collector.config import load_config  # noqa: E402

TYPE_MAP = {
    1: "text", 3: "image", 34: "voice", 37: "system", 40: "system",
    42: "contact_card", 43: "video", 47: "emoji", 48: "location", 49: "appmsg",
    51: "system", 52: "system", 62: "video", 2000: "system", 2001: "system",
    2002: "appmsg", 2003: "system", 2004: "file", 9999: "system",
    10000: "system", 10002: "system",
}

pending: list[dict] = []
server = "http://127.0.0.1:8000"
collector_token = ""
allow_dm = True
self_wxid = ""
whitelist = {"allow_all": True, "groups": []}


def refresh_whitelist() -> None:
    global whitelist
    try:
        resp = httpx.get(
            f"{server}/api/v1/ingest/whitelist",
            headers={"X-Collector-Token": collector_token},
            timeout=5,
        )
        data = resp.json()
        whitelist = {"allow_all": bool(data.get("allow_all")),
                     "groups": list(data.get("groups") or [])}
        print(f"[bridge] 白名单刷新 allow_all={whitelist['allow_all']} groups={len(whitelist['groups'])}")
    except Exception as exc:
        print(f"[bridge] 白名单刷新失败（沿用旧值）: {exc}")


def allow(wx_id: str, stype: str) -> bool:
    if whitelist["allow_all"]:
        return True
    if stype == "group":
        return wx_id in whitelist["groups"]
    return allow_dm or wx_id in whitelist["groups"]


def submit(msg: dict) -> None:
    pending.append(msg)
    if len(pending) >= 20:
        flush()


def flush() -> None:
    while pending:
        batch = {"schema_ver": 1, "messages": pending[:100]}
        try:
            resp = httpx.post(
                f"{server}/api/v1/ingest/messages",
                json=batch,
                headers={"X-Collector-Token": collector_token},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            pending[: len(batch["messages"])] = []
            if data.get("inserted"):
                print(f"[bridge] 入库 {data['inserted']} / 跳过 {data['skipped']}")
        except Exception as exc:
            print(f"[bridge] 上报失败（保留重试）: {exc}")
            return


def _pick(data: dict, *keys: str, default=None):
    """字段名防御性多候选（libencode 版本间字段名可能微调）。"""
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return data[k]
    return default


def convert(data: dict) -> dict | None:
    from_user = str(_pick(data, "fromUserName", "from_username", "fromUser", "sender") or "")
    to_user = str(_pick(data, "toUserName", "to_username", "toUser") or "")
    content = str(_pick(data, "content", "message") or "")
    base_type = int(_pick(data, "type", "msgType", "msg_type", default=1) or 1)
    create_time = _pick(data, "createTime", "create_time", "timestamp", default=0)
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(create_time)))
    except (ValueError, TypeError, OSError):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
    mtype = TYPE_MAP.get(base_type, f"type_{base_type}")

    if from_user.endswith("@chatroom"):
        session = {"wx_id": from_user, "type": "group", "name": ""}
        idx = content.find(":\n")
        if idx != -1:
            sender, content = content[:idx], content[idx + 2:]
        else:
            sender = self_wxid or to_user
    elif to_user.endswith("@chatroom"):
        session = {"wx_id": to_user, "type": "group", "name": ""}
        sender = from_user
        idx = content.find(":\n")
        if idx != -1:
            content = content[idx + 2:]
    else:
        counterpart = from_user if from_user != self_wxid else to_user
        session = {"wx_id": counterpart, "type": "dm", "name": ""}
        sender = from_user
    svr_id = str(_pick(data, "msgId", "newMsgId", "msg_id", "id", default="") or "")
    if not svr_id:
        return None
    return {
        "session": session,
        "svr_id": svr_id,
        "sender_wxid": sender,
        "msg_type": mtype,
        "content": content,
        "ts": ts,
        "source": "libencode",
    }


def make_handler(wechat):
    def on_any(bot, data: dict) -> None:
        global self_wxid
        try:
            if not self_wxid:
                try:
                    self_wxid = bot.get_self_info().wxid
                except Exception:
                    pass
            msg = convert(data)
            if msg is None or not allow(msg["session"]["wx_id"], msg["session"]["type"]):
                return
            submit(msg)
        except Exception as exc:
            print(f"[bridge] 消息处理失败: {exc}")
    return on_any


def main() -> int:
    global server, collector_token, allow_dm

    parser = argparse.ArgumentParser(description="libencode 实时桥")
    parser.add_argument("--version", default="4.1.8.67", help="微信版本号")
    parser.add_argument("--no-dm", dest="allow_dm", action="store_false")
    args = parser.parse_args()
    allow_dm = args.allow_dm

    settings = load_config(REPO / "collector" / "config.yaml")
    server = settings.server_base_url
    collector_token = settings.server_ingest_token
    refresh_whitelist()

    from pywechat_libencode import WeChat, events

    wechat = WeChat(version=args.version)

    wechat.handle(events.ALL_MESSAGE)(make_handler(wechat))

    def _on_login(bot, data=None):
        global self_wxid
        try:
            self_wxid = _pick(vars(bot), "wxid", default="") or self_wxid
        except Exception:
            pass
        print(f"[bridge] 登录成功（self={self_wxid or '待获取'}）")
        refresh_whitelist()

    for ev_name in ("USER_LOGIN_MESSAGE", "WECHAT_CONNECT_MESSAGE"):
        ev = getattr(events, ev_name, None)
        if ev is not None:
            wechat.handle(ev)(_on_login)

    def _flush_loop():
        while True:
            time.sleep(30)
            flush()

    threading.Thread(target=_flush_loop, daemon=True).start()
    print(f"[bridge] libencode 桥启动 version={args.version}")
    wechat.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

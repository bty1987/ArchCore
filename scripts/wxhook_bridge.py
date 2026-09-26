"""wxhook 实时桥：Bot(PC Hook 3.9.x) → ArchCore /api/v1/ingest。

前置：对应版本微信客户端（如 3.9.12.45）已登录；pip 环境已装 wxhook。
用法：
    python scripts/wxhook_bridge.py [--faked-version 3.9.12.51] [--allow-dm]

- 白名单从服务端 /ingest/whitelist 拉取（60s 刷新），未配置视为采集全部；
- svr_id = wxhook msgId，与解密轨（wechat4）去重并存；
- 群消息发送者在 content 前缀（"wxid:\n正文"），与 padlocal/wcferry 同语义。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "collector" / "src"))

from wxhook import Bot, events  # noqa: E402
from wxhook.model import Event  # noqa: E402

# 消息类型映射（wxhook type 码 → ingest msg_type）
TYPE_MAP = {
    1: "text", 3: "image", 34: "voice", 37: "system", 40: "system",
    42: "contact_card", 43: "video", 47: "emoji", 48: "location", 49: "appmsg",
    50: "system", 51: "system", 52: "system", 62: "video", 65: "system",
    2000: "system", 2001: "system", 2002: "appmsg", 2003: "system",
    2004: "file", 9999: "system", 10000: "system", 10002: "system",
}

pending: list[dict] = []
server = "http://127.0.0.1:8000"
collector_token = ""
allow_dm = True
self_wxid = ""
whitelist = {"allow_all": True, "groups": []}


def load_collector_settings() -> tuple[str, str]:
    from archcore_collector.config import load_config

    cfg = load_config(REPO / "collector" / "config.yaml")
    return cfg.server_base_url, cfg.server_ingest_token


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


def convert(event: Event) -> dict | None:
    from_user = event.fromUser or ""
    to_user = event.toUser or ""
    content = event.content or ""
    base_type = int(event.type or 0)
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
    if not event.msgId:
        return None
    return {
        "session": session,
        "svr_id": str(event.msgId),
        "sender_wxid": sender,
        "msg_type": mtype,
        "content": content,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.createTime or time.time())),
        "source": "wxhook",
    }


def on_message(bot: Bot, event: Event) -> None:
    if event.type and not allow(*_session_of(event)):
        return
    msg = convert(event)
    if msg is None:
        return
    if not allow(msg["session"]["wx_id"], msg["session"]["type"]):
        return
    submit(msg)


def _session_of(event: Event) -> tuple[str, str]:
    """快速会话判定（过滤用），完整解析在 convert。"""
    fu, tu = event.fromUser or "", event.toUser or ""
    if fu.endswith("@chatroom"):
        return fu, "group"
    if tu.endswith("@chatroom"):
        return tu, "group"
    return (fu if fu != self_wxid else tu), "dm"


def main() -> int:
    global server, collector_token, allow_dm, self_wxid

    parser = argparse.ArgumentParser(description="wxhook 实时桥")
    parser.add_argument("--faked-version", default=None, help="版本伪装（解除低版本登录限制）")
    parser.add_argument("--allow-dm", action="store_true", default=True)
    args = parser.parse_args()
    allow_dm = args.allow_dm

    server, collector_token = load_collector_settings()
    refresh_whitelist()

    bot = Bot(faked_version=args.faked_version) if args.faked_version else Bot()

    @bot.on_login
    def _(bot: Bot, event=None):
        global self_wxid
        info = bot.get_self_info()
        self_wxid = getattr(info, "wxid", "") or (info.get("wxid", "") if isinstance(info, dict) else "")
        print(f"[bridge] 登录成功: {self_wxid}（collector_wxid 需与此一致）")
        refresh_whitelist()

    bot.handle(events.ALL_MESSAGE)(on_message)

    def _flush_loop(bot: Bot):
        while True:
            time.sleep(30)
            flush()

    import threading

    threading.Thread(target=_flush_loop, args=(bot,), daemon=True).start()

    print(f"[bridge] wxhook 桥启动 faked_version={args.faked_version}")
    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

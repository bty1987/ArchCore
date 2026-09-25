"""采集端单测：normalize 边界 + 白名单过滤 + 指纹/去重职责边界。"""

import sys
from pathlib import Path

import pytest

COLLECTOR_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(COLLECTOR_SRC))

from archcore_collector.config import CollectorSettings, WhitelistConfig
from archcore_collector.transform.filter import WhitelistFilter
from archcore_collector.transform.normalize import normalize


class TestNormalize:
    def test_basic(self):
        out = normalize(
            "decrypt",
            {
                "session": {"wx_id": "g@chatroom", "type": "group", "name": "群"},
                "svr_id": "123",
                "sender_wxid": "wxid_a",
                "msg_type": "text",
                "content": "你好",
                "ts": "2026-09-01 10:00:00",
            },
        )
        assert out["svr_id"] == "123" and out["source"] == "decrypt"
        assert out["session"]["wx_id"] == "g@chatroom"

    def test_missing_session_returns_none(self):
        assert normalize("decrypt", {"content": "x", "ts": "2026-09-01 10:00:00"}) is None
        assert normalize("decrypt", {"session": {"wx_id": "g"}, "content": "x"}) is None

    def test_media_placeholder(self):
        out = normalize(
            "decrypt",
            {
                "session": {"wx_id": "g@chatroom", "type": "group", "name": ""},
                "svr_id": "9",
                "sender_wxid": "w",
                "msg_type": "file",
                "content": "",
                "ts": "2026-09-01 10:00:00",
                "media_meta": {"filename": "合同.pdf"},
            },
        )
        assert out["content"] == "[file] 合同.pdf"
        assert out["media_meta"]["filename"] == "合同.pdf"

    def test_svr_id_coerced_to_str(self):
        out = normalize(
            "decrypt",
            {
                "session": {"wx_id": "g@chatroom", "type": "group", "name": ""},
                "svr_id": 1234567890123,
                "sender_wxid": "w",
                "msg_type": "text",
                "content": "x",
                "ts": "2026-09-01 10:00:00",
            },
        )
        assert out["svr_id"] == "1234567890123"


class TestWhitelist:
    def test_exact_group_id(self):
        f = WhitelistFilter(WhitelistConfig(groups=["g1@chatroom"], allow_dm=False))
        assert f.allow("g1@chatroom", "group", "任意名")
        assert not f.allow("g2@chatroom", "group", "任意名")
        assert not f.allow("wxid_x", "dm", "联系人")  # allow_dm=False

    def test_group_name_pattern(self):
        f = WhitelistFilter(WhitelistConfig(group_name_patterns=[r"^ABC项目"]))
        assert f.allow("g9@chatroom", "group", "ABC项目-交付群")
        assert not f.allow("g9@chatroom", "group", "家庭群")

    def test_dm_allowed(self):
        f = WhitelistFilter(WhitelistConfig(groups=[], allow_dm=True))
        assert f.allow("wxid_client", "dm", "客户")

    def test_allow_all_overrides_everything(self):
        f = WhitelistFilter(WhitelistConfig(allow_all=True))
        assert f.allow("任意群@chatroom", "group", "")
        assert f.allow("任意私聊", "dm", "")
        assert not WhitelistFilter(WhitelistConfig()).allow("任意群@chatroom", "group", "")

    @pytest.mark.parametrize(
        "cfg",
        [
            WhitelistConfig(groups=["a"], allow_dm=False),
            WhitelistConfig(),
        ],
    )
    def test_config_roundtrip(self, cfg):
        s = CollectorSettings(whitelist=cfg)
        assert s.whitelist.groups == cfg.groups

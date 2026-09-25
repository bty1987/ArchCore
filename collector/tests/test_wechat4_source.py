"""wechat4 数据源单测：合成解密库，锁定表发现/发送者映射/ZSTD 解压逻辑。

背景：真机联调中曾出现 LIKE 反斜杠、Msg_ 前缀、Name2Id rowid 三处回归，此测试防复发。
"""

import sqlite3
import sys
from pathlib import Path

import pytest

COLLECTOR_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(COLLECTOR_SRC))

from archcore_collector.wechat4_source import WeChat4Source


@pytest.fixture()
def plain_dir(tmp_path):
    root = tmp_path / "plain"
    (root / "message").mkdir(parents=True)
    (root / "contact").mkdir()

    contact = sqlite3.connect(str(root / "contact" / "contact.db"))
    contact.execute("CREATE TABLE contact (username TEXT, nick_name TEXT, remark TEXT)")
    contact.execute("INSERT INTO contact VALUES ('wxid_boss', '老板', '老板备注')")
    contact.execute("INSERT INTO contact VALUES ('12345@chatroom', '测试群', '')")
    contact.execute("CREATE TABLE name2id (username TEXT)")
    contact.execute("INSERT INTO name2id VALUES ('wxid_boss')")
    contact.commit()
    contact.close()

    msg = sqlite3.connect(str(root / "message" / "message_0.db"))
    msg.execute("CREATE TABLE Name2Id (user_name TEXT, is_session INTEGER)")
    msg.execute("INSERT INTO Name2Id VALUES ('wxid_boss', 1)")  # rowid=1
    table = f"Msg_{__import__('hashlib').md5(b'wxid_boss').hexdigest()}"
    msg.execute(
        f"CREATE TABLE '{table}' ("
        "server_id INTEGER, real_sender_id INTEGER, local_type INTEGER, "
        "create_time INTEGER, message_content TEXT, WCDB_CT_message_content INTEGER)"
    )
    msg.execute(
        f"INSERT INTO '{table}' VALUES (9001, 1, 1, 1780000000, '你好老板', 0)"
    )
    msg.commit()
    msg.close()
    return root


def test_list_sessions_finds_dm_and_group(plain_dir):
    src = WeChat4Source(str(plain_dir))
    sessions = {s.wx_id: s for s in src.list_sessions()}
    assert sessions["wxid_boss"].type == "dm"
    assert sessions["wxid_boss"].name == "老板备注"  # 备注优先于昵称
    assert sessions["12345@chatroom"].type == "group"


def test_iter_messages_maps_fields(plain_dir):
    src = WeChat4Source(str(plain_dir))
    msgs = list(src.iter_messages(
        next(s for s in src.list_sessions() if s.wx_id == "wxid_boss")))
    assert len(msgs) == 1
    m = msgs[0]
    assert m.svr_id == "9001"
    assert m.sender_wxid == "wxid_boss"  # Name2Id rowid 反查
    assert m.msg_type == "text"
    assert m.content == "你好老板"

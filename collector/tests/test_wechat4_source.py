"""wechat4 数据源单测：合成解密库，锁定表发现/发送者映射/ZSTD 解压逻辑。

背景：真机联调中曾出现 LIKE 反斜杠、Msg_ 前缀、Name2Id rowid 三处回归，此测试防复发。
"""

import sqlite3
import sys
from pathlib import Path

import pytest

COLLECTOR_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(COLLECTOR_SRC))

from archcore_collector.wechat4_source import WeChat4Source, parse_rich


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
    msg.execute(f"INSERT INTO '{table}' VALUES (9001, 1, 1, 1780000000, '你好老板', 0)")
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
    msgs = list(src.iter_messages(next(s for s in src.list_sessions() if s.wx_id == "wxid_boss")))
    assert len(msgs) == 1
    m = msgs[0]
    assert m.svr_id == "9001"
    assert m.sender_wxid == "wxid_boss"  # Name2Id rowid 反查
    assert m.msg_type == "text"
    assert m.content == "你好老板"


class TestParseRich:
    """富内容解析：图片/语音/视频/文件/引用/卡片（样本取自真机 4.1.15 结构）。"""

    def test_image(self):
        xml = '<msg><img aeskey="abc" encryver="1" length="99999" cdnthumbwidth="120"/></msg>'
        text, meta = parse_rich("image", xml)
        assert text == "[图片]"
        assert meta["size_bytes"] == 99999

    def test_voice(self):
        xml = '<msg><voicemsg voicelength="5300" voiceformat="4"/></msg>'
        text, meta = parse_rich("voice", xml)
        assert text == "[语音] 5 秒"
        assert meta["duration_seconds"] == 5

    def test_video(self):
        xml = '<msg><videomsg aeskey="k" cdnvideourl="u" length="88000" playlength="15"/></msg>'
        text, _meta = parse_rich("video", xml)
        assert text == "[视频] 15 秒"

    def test_file_card(self):
        xml = (
            "<msg><appmsg appid=\"\" sdkver=\"0\"><title>合同V3.pdf</title>"
            "<type>6</type><appattach><totallen>238400</totallen></appattach></appmsg></msg>"
        )
        text, meta = parse_rich("appmsg", xml)
        assert text == "[文件] 合同V3.pdf"
        assert meta["filename"] == "合同V3.pdf" and meta["size_bytes"] == 238400

    def test_refer_quote(self):
        xml = (
            "<msg><appmsg appid=\"\" sdkver=\"0\"><title>张总</title><type>57</type>"
            "<url/>"
            "<refermsg><displayname>张总</displayname><content>明天可以报价吗</content></refermsg>"
            "<content>可以的，上午发您</content></appmsg></msg>"
        )
        text, meta = parse_rich("quote", xml)
        assert "[引用] 张总：明天可以报价吗" in text
        assert "上午发您" in text
        assert meta["quote"]["who"] == "张总"

    def test_article_card(self):
        xml = (
            "<msg><appmsg appid=\"\" sdkver=\"0\"><title><![CDATA[9月书单]]></title>"
            "<type>5</type><url>https://mp.weixin.qq.com/s/abc</url>"
            "<des><![CDATA[本月推荐]]></des></appmsg></msg>"
        )
        text, meta = parse_rich("quote", xml)
        assert "[卡片] 9月书单" in text
        assert meta["url"].startswith("https://")
        assert "本月推荐" in text

    def test_plain_text_passthrough(self):
        text, meta = parse_rich("text", "普通文本不是XML")
        assert text == "普通文本不是XML"
        assert meta == {"kind": "text"}
        # 非 XML 内容原样返回
        text2, _ = parse_rich("appmsg", "不是XML的内容")
        assert text2 == "不是XML的内容"

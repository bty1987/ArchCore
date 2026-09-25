// ArchCore PadLocal 实时桥接（直连 padlocal-client-ts，不经 wechaty）：
// PadLocalClient（iPad 协议）→ 白名单过滤 → ArchCore /api/v1/ingest
//
// 用法（需 PadLocal token，puppet_padlocal_xxx）：
//   node padlocal_bridge.mjs --token puppet_padlocal_xxx --server http://127.0.0.1:8000 \
//     --collector-token xxx [--allow-dm] [--bridge-name archcore-padlocal]
// 首次运行按控制台给出的二维码图片 URL 扫码登录。
// svr_id = PadLocal 消息 id，与解密轨（wechat4）经 svr_id 去重自然并存。

import { PadLocalClient } from "padlocal-client-ts";
import * as PadLocal from "padlocal-client-ts/dist/proto/padlocal_pb.js";

const args = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const m = argv[i].match(/^--([\w-]+)(?:=(.*))?$/);
  if (!m) continue;
  if (m[2] !== undefined) {
    args[m[1]] = m[2];
  } else if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) {
    args[m[1]] = argv[i + 1];
    i++;
  } else {
    args[m[1]] = true;
  }
}
const TOKEN = args.token || "";
const SERVER = args.server || "http://127.0.0.1:8000";
const COLLECTOR_TOKEN = args["collector-token"] || "";
const ALLOW_DM = !!args["allow-dm"];
const BRIDGE_NAME = args["bridge-name"] || "archcore-padlocal";

if (!TOKEN || !COLLECTOR_TOKEN) {
  console.error("[bridge] 需要 --token 与 --collector-token");
  process.exit(1);
}

// ---------- 白名单（服务端管控，5 分钟刷新） ----------
const whitelist = { allow_all: false, groups: [] };

async function refreshWhitelist() {
  try {
    const resp = await fetch(`${SERVER}/api/v1/ingest/whitelist`, {
      headers: { "X-Collector-Token": COLLECTOR_TOKEN },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    whitelist.allow_all = !!data.allow_all;
    whitelist.groups = data.groups || [];
    console.log(`[bridge] 白名单已刷新 allow_all=${whitelist.allow_all} groups=${whitelist.groups.length}`);
  } catch (err) {
    console.warn(`[bridge] 白名单刷新失败（沿用旧值）: ${err.message}`);
  }
}
await refreshWhitelist();
setInterval(refreshWhitelist, 5 * 60 * 1000);

function allow(wxId, type) {
  if (whitelist.allow_all) return true;
  if (type === "group") return whitelist.groups.includes(wxId);
  return ALLOW_DM || whitelist.groups.includes(wxId);
}

// ---------- 上报（失败入重试队列，30 秒冲刷） ----------
const pending = [];

async function post(batch) {
  const resp = await fetch(`${SERVER}/api/v1/ingest/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Collector-Token": COLLECTOR_TOKEN },
    body: JSON.stringify(batch),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

async function submit(message) {
  pending.push(message);
  if (pending.length >= 20) await flush();
}

async function flush() {
  while (pending.length) {
    const batch = { schema_ver: 1, messages: pending.slice(0, 100) };
    try {
      const r = await post(batch);
      pending.splice(0, batch.messages.length);
      if (r.inserted) console.log(`[bridge] 入库 ${r.inserted} / 跳过 ${r.skipped}`);
    } catch (err) {
      console.warn(`[bridge] 上报失败（保留重试）: ${err.message}`);
      return;
    }
  }
}
setInterval(() => flush().catch(() => {}), 30 * 1000);

// ---------- 消息类型映射与富内容摘要 ----------
const TYPE_MAP = {
  1: "text", 3: "image", 34: "voice", 42: "contact_card", 43: "video",
  47: "emoji", 48: "location", 49: "appmsg", 51: "system",
  10000: "system", 10002: "system",
};
const TYPE_LABEL = {
  image: "图片", video: "视频", voice: "语音", file: "文件", emoji: "表情",
  location: "位置", contact_card: "名片", quote: "卡片", appmsg: "卡片", system: "系统消息",
};

function titleOf(xml) {
  const m = /<title(?:[^>]*)><!\[CDATA\[([\s\S]*?)\]\]><\/title>|<title[^>]*>([\s\S]*?)<\/title>/.exec(xml);
  return (m && (m[1] || m[2])) || "";
}

function contentOf(baseType, raw) {
  const text = typeof raw === "string" ? raw : "";
  if (baseType === 1) return text;
  if ((baseType === 49 || baseType === 57) && text.includes("<title")) {
    const title = titleOf(text);
    if (title) return `[卡片] ${title}`;
  }
  const label = TYPE_LABEL[Object.keys(TYPE_MAP).find((k) => TYPE_MAP[k] === baseType) === undefined
    ? baseType
    : { 3: "image", 34: "voice", 42: "contact_card", 43: "video", 47: "emoji",
        48: "location", 49: "appmsg", 51: "system", 10000: "system", 10002: "system" }[baseType]] || "消息";
  return `[${label}]`;
}

// ---------- 消息解析（对齐 wechaty-puppet-padlocal 的 roomParser 语义） ----------
let SELF_WXID = "";

function parseMessage(message) {
  const from = message.fromusername || "";
  const to = message.tousername || "";
  let content = message.content || "";
  const baseType = Number(message.type) || 0;
  const msgType = TYPE_MAP[baseType] || `type_${baseType}`;
  const ts = new Date(Number(message.createtime) * 1000)
    .toISOString().replace("T", " ").slice(0, 19);
  const isRoom = from.endsWith("@chatroom") || to.endsWith("@chatroom");

  let session;
  let sender;
  if (from.endsWith("@chatroom")) {
    // 他人发的群消息：content = "wxid_sender:\n正文"
    session = { wx_id: from, type: "group", name: "" };
    const idx = content.indexOf(":\n");
    if (idx !== -1) {
      sender = content.slice(0, idx);
      content = content.slice(idx + 2);
    } else {
      sender = to;
    }
  } else if (to.endsWith("@chatroom")) {
    // 自己发的群消息：from = 自己，tousername = 群
    session = { wx_id: to, type: "group", name: "" };
    sender = from;
    const idx = content.indexOf(":\n");
    if (idx !== -1) content = content.slice(idx + 2);
  } else {
    // 单聊：会话对象 = 对方；自己发的消息 sender = 自己
    const counterpart = from === SELF_WXID ? to : from;
    session = { wx_id: counterpart, type: "dm", name: "" };
    sender = from;
  }
  return {
    session,
    svr_id: String(message.id || ""),
    sender_wxid: sender,
    msg_type: TYPE_MAP[baseType] || `type_${baseType}`,
    content: contentOf(baseType, content) || content,
    ts,
    source: "padlocal",
    _baseType: baseType,
    _msgType: msgType,
  };
}

async function handleMessage(message) {
  const parsed = parseMessage(message);
  if (!parsed.svr_id) return;
  if (!allow(parsed.session.wx_id, parsed.session.type)) return;
  if (parsed._msgType !== "text" && parsed._msgType !== "system") {
    // 非 text/system 已由 contentOf 生成展示占位
  }
  delete parsed._baseType;
  delete parsed._msgType;
  await submit(parsed);
}

// ---------- 主流程 ----------
console.log(`[bridge] 启动：server=${SERVER} allow_dm=${ALLOW_DM}`);
const client = await PadLocalClient.create(TOKEN, true);

client.on("kickout", (detail) => {
  console.error(`[bridge] 被踢下线: ${detail.errorMessage}（监护器将重启）`);
  process.exit(1);
});
client.on("message", async (messageList) => {
  for (const message of messageList) {
    try {
      await handleMessage(message);
    } catch (err) {
      console.error(`[bridge] 消息处理失败: ${err.message}`);
    }
  }
});

const QR_STATUS = {
  [PadLocal.QRCodeStatus.NEW]: "等待扫码",
  [PadLocal.QRCodeStatus.SCANNED]: "已扫码，请在手机确认",
  [PadLocal.QRCodeStatus.CONFIRMED]: "已确认",
  [PadLocal.QRCodeStatus.CANCELLED]: "已取消",
  [PadLocal.QRCodeStatus.EXPIRED]: "二维码已过期（等待刷新）",
};
const onQrCodeEvent = async (qrCodeEvent) => {
  const status = qrCodeEvent.getStatus();
  const name = PadLocal.QRCodeStatus[status] || String(status);
  const url = qrCodeEvent.getImageurl();
  console.log(`[bridge] 扫码状态: ${QR_STATUS[name] || name}${url ? " → 二维码图片: " + url : ""}`);
};

await client.api.login(PadLocal.LoginPolicy.DEFAULT, {
  onLoginStart: (loginType) => console.log(`[bridge] 开始登录，方式: ${loginType}`),
  onLoginSuccess: async () => {
    SELF_WXID = client.selfContact?.getUsername() || "";
    console.log(`[bridge] 登录成功: ${SELF_WXID}（${client.selfContact?.getNickName?.() || ""}）`);
    console.log(`[bridge] 请确认 collector 配置 collector_wxid=${SELF_WXID}（方向判定依据）`);
    await refreshWhitelist();
  },
  onOneClickEvent: onQrCodeEvent,
  onQrCodeEvent,
  onSync: async (syncEvent) => {
    // 登录后的增量同步：与实时消息同一处理（svr_id 去重）
    for (const message of syncEvent.getMessageList()) {
      try {
        await handleMessage(message);
      } catch (err) {
        console.error(`[bridge] 同步消息处理失败: ${err.message}`);
      }
    }
  },
});

console.log("[bridge] 实时接收中（Ctrl+C 退出）");
setInterval(() => {}, 1 << 30); // 保持进程常驻

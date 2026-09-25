// ArchCore PadLocal 实时桥接 v2：双模式对接
//
//   --mode direct  直连 PadLocal 网关（padlocal-client-ts，官方 token）
//   --mode service 网关化 PuppetService（rpachat 自建网关 / 托管服务）
//
// 通用参数：--token --server --collector-token --bridge-name --allow-dm
// service 附加：--endpoint 127.0.0.1:9001 / --authority token-service-discovery... / --no-tls
//
// 消息流：扫码登录 → wechaty/padlocal 事件 → 白名单过滤（5 分钟刷新）→
//         POST /ingest/messages（失败入重试队列）。svr_id 去重，与解密轨并存。

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
const MODE = args.mode || "direct";
const TOKEN = args.token || "";
const SERVER = args.server || "http://127.0.0.1:8000";
const COLLECTOR_TOKEN = args["collector-token"] || "";
const ALLOW_DM = !!args["allow-dm"];
const BRIDGE_NAME = args["bridge-name"] || "archcore-padlocal";

if (!COLLECTOR_TOKEN) {
  console.error("[bridge] 需要 --collector-token");
  process.exit(1);
}
if (MODE === "padlocal" && !TOKEN) {
  console.error("[bridge] padlocal 模式需要 --token");
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

async function submit(msg) {
  pending.push(msg);
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

// ---------- 归一化 ----------
const TYPE_LABEL = {
  image: "图片", video: "视频", voice: "语音", file: "文件", emoji: "表情",
  location: "位置", contact_card: "名片", quote: "卡片", appmsg: "卡片", system: "系统消息",
};

function titleOf(xml) {
  const m = /<title(?:[^>]*)><!\[CDATA\[([\s\S]*?)\]\]><\/title>|<title[^>]*>([\s\S]*?)<\/title>/.exec(xml);
  return (m && (m[1] || m[2])) || "";
}

function contentOf(mtype, raw) {
  const text = typeof raw === "string" ? raw : "";
  if (mtype === "text") return text;
  if ((mtype === "quote" || mtype === "appmsg") && text.includes("<title")) {
    const title = titleOf(text);
    if (title) return `[卡片] ${title}`;
  }
  const label = TYPE_LABEL[mtype] || "消息";
  return `[${label}]`;
}

// ---------- direct 模式（padlocal-client-ts 直连） ----------
async function runDirectMode() {
  const { PadLocalClient } = await import("padlocal-client-ts");
  const PadLocal = await import("padlocal-client-ts/dist/proto/padlocal_pb.js");

  const client = await PadLocalClient.create(TOKEN, true);
  let SELF_WXID = "";

  function parsePadLocal(message) {
    const from = message.fromusername || "";
    const to = message.tousername || "";
    let content = message.content || "";
    const baseType = Number(message.type) || 0;
    const TYPE_MAP = {
      1: "text", 3: "image", 34: "voice", 42: "contact_card", 43: "video",
      47: "emoji", 48: "location", 49: "appmsg", 51: "system",
      10000: "system", 10002: "system",
    };
    const mtype = TYPE_MAP[baseType] || `type_${baseType}`;
    const ts = new Date(Number(message.createtime) * 1000)
      .toISOString().replace("T", " ").slice(0, 19);

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
      // 自己发的群消息：from = 自己
      session = { wx_id: to, type: "group", name: "" };
      sender = from;
      const idx = content.indexOf(":\n");
      if (idx !== -1) content = content.slice(idx + 2);
    } else {
      const counterpart = from === SELF_WXID ? to : from;
      session = { wx_id: counterpart, type: "dm", name: "" };
      sender = from;
    }
    return {
      session,
      svr_id: String(message.id || ""),
      sender_wxid: sender,
      msg_type: mtype,
      content: contentOf(mtype, content) || content,
      ts,
      source: "padlocal",
    };
  }

  async function handleMessage(message) {
    const parsed = parsePadLocal(message);
    if (!parsed.svr_id) return;
    if (!allow(parsed.session.wx_id, parsed.session.type)) return;
    await submit(parsed);
  }

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

  console.log("[bridge] direct 模式启动");
  await client.api.login(PadLocal.LoginPolicy.DEFAULT, {
    onLoginStart: (loginType) => console.log(`[bridge] 开始登录，方式: ${loginType}`),
    onLoginSuccess: async () => {
      SELF_WXID = client.selfContact?.getUsername() || "";
      console.log(`[bridge] 登录成功: ${SELF_WXID}`);
      console.log(`[bridge] 请确认 collector 配置 collector_wxid=${SELF_WXID}（方向判定依据）`);
      await refreshWhitelist();
    },
    onOneClickEvent: onQrCodeEvent,
    onQrCodeEvent,
    onSync: async (syncEvent) => {
      for (const message of syncEvent.getMessageList()) {
        try {
          await handleMessage(message);
        } catch (err) {
          console.error(`[bridge] 同步消息处理失败: ${err.message}`);
        }
      }
    },
  });
}

// ---------- wcferry 模式（PC Hook，本机 3.9.2.23 64 位微信） ----------
async function runWcferryMode() {
  const { WechatferryAgent } = await import("@wechatferry/agent");
  const agent = new WechatferryAgent();
  let selfWxid = "";

  const TYPE_MAP = {
    0: "post", 1: "text", 3: "image", 34: "voice", 37: "system", 40: "system",
    42: "contact_card", 43: "video", 47: "emoji", 48: "location", 49: "appmsg",
    50: "system", 51: "system", 52: "system", 62: "video", 65: "system",
    2000: "system", 2001: "system", 2002: "appmsg", 2003: "system",
    2004: "file", 9999: "system", 10000: "system", 10002: "system",
  };

  agent.on("login", (user) => {
    selfWxid = user?.wxid || "";
    console.log(`[bridge] 登录成功: ${selfWxId}`);
    refreshWhitelist();
  });
  agent.on("error", (err) => console.error(`[bridge] wcf error: ${err.message}`));
  agent.on("message", async (m) => {
    try {
      const isRoom = m.is_group || (m.roomid || "").endsWith("@chatroom");
      let content = m.content || "";
      let sender;
      let session;
      if (isRoom) {
        session = { wx_id: m.roomid, type: "group", name: "" };
        const idx = content.indexOf(":\n");
        if (idx !== -1) {
          sender = content.slice(0, idx);
          content = content.slice(idx + 2);
        } else {
          sender = m.is_self ? selfWxid : m.sender;
        }
      } else {
        session = { wx_id: m.sender, type: "dm", name: "" };
        sender = m.is_self ? selfWxid : m.sender;
      }
      if (!allow(session.wx_id, session.type)) return;
      await submit({
        session,
        svr_id: String(m.id),
        sender_wxid: sender,
        msg_type: TYPE_MAP[Number(m.type)] || `type_${m.type}`,
        content: contentOf(TYPE_MAP[Number(m.type)] || "appmsg", content) || content,
        ts: new Date(Number(m.ts) * 1000).toISOString().replace("T", " ").slice(0, 19),
        source: "wcferry",
      });
    } catch (err) {
      console.error(`[bridge] 消息处理失败: ${err.message}`);
    }
  });

  console.log("[bridge] wcferry 模式启动（等待微信 3.9.2.23 客户端）");
  agent.start();
}

// ---------- service 模式（wechaty-puppet-service，网关化） ----------
async function runServiceMode() {
  // 对接 rpachat 自建网关 / 托管服务（环境变量见 RPA Chat 接入文档）
  process.env.WECHATY_PUPPET = "wechaty-puppet-service";
  process.env.WECHATY_PUPPET_SERVICE_TOKEN = TOKEN;
  if (args.endpoint) process.env.WECHATY_PUPPET_SERVICE_ENDPOINT = args.endpoint;
  if (args.authority) process.env.WECHATY_PUPPET_SERVICE_AUTHORITY = args.authority;
  if (args["no-tls"]) {
    process.env.WECHATY_PUPPET_SERVICE_NO_TLS_INSECURE_CLIENT = "true";
    process.env.WECHATY_PUPPET_SERVICE_NO_TLS_INSECURE_SERVER = "true";
  }

  const { WechatyBuilder } = await import("wechaty");

  const bot = WechatyBuilder.build({ name: BRIDGE_NAME }); // puppet 来自环境变量

  bot
    .on("scan", (qrcode, status) => {
      console.log(`[bridge] 扫码状态 ${status}: https://wechaty.js.org/qrcode/${encodeURIComponent(qrcode)}`);
    })
    .on("login", (user) => {
      console.log(`[bridge] 登录成功: ${user.id}（${user.name()}）`);
      console.log(`[bridge] 请确认 collector 配置 collector_wxid=${user.id}（方向判定依据）`);
      refreshWhitelist();
    })
    .on("logout", (user) => console.warn(`[bridge] 已登出: ${user}`))
    .on("error", (err) => console.error(`[bridge] bot error: ${err.message}`))
    .on("message", async (msg) => {
      try {
        const room = await msg.room();
        const talker = await msg.talker();
        const self = msg.self();
        const rawType = Number(msg.type());
        // wechaty-puppet MessageType 枚举（数字稳定）：7 文本 6 图片 15 视频 2 语音
        // 5 表情 14 链接卡片 9 小程序 1 文件 4 聊天记录 3 名片 10 群公告 13 撤回
        const TYPE_MAP = {
          1: "file", 2: "voice", 3: "contact_card", 4: "quote", 5: "emoji",
          6: "image", 7: "text", 9: "appmsg", 10: "system", 13: "system",
          14: "quote", 15: "video", 16: "post",
        };
        const mtype = TYPE_MAP[rawType] || "appmsg";
        const session = room
          ? { wx_id: room.id, type: "group", name: (await room.topic()) || "" }
          : { wx_id: self ? (msg.listener()?.id || selfWxId) : talker.id,
              type: "dm", name: talker.name() || "" };
        const sender = room ? talker.id : (self ? session.wx_id : talker.id);
        if (!allow(session.wx_id, session.type)) return;
        await submit({
          session,
          svr_id: String(msg.id),
          sender_wxid: sender,
          msg_type: mtype,
          content: contentOf(mtype, msg.text()),
          ts: msg.date().toISOString().replace("T", " ").slice(0, 19),
          source: "padlocal",
        });
      } catch (err) {
        console.error(`[bridge] 消息处理失败: ${err.message}`);
      }
    });

  function selfWxId(msg, talker) {
    // 自己发的单聊：listener 为对方；sender 语义由 server 侧 collector_wxid 判定
    return talker.id;
  }

  console.log("[bridge] service 模式启动");
  await bot.start();
}

const RUNNERS = { direct: runDirectMode, service: runServiceMode, wcferry: runWcferryMode };
(RUNNERS[MODE] || runDirectMode)()
  .then(() => {
    console.log(`[bridge] ${MODE} 模式实时接收中（Ctrl+C 退出）`);
    setInterval(() => {}, 1 << 30); // 常驻
  })
  .catch((err) => {
    console.error(`[bridge] 启动失败: ${err.message}`);
    process.exit(1);
  });

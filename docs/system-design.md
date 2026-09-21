# ArchCore 系统设计文档

| | |
|---|---|
| 文档版本 | v0.1 |
| 日期 | 2026-09-21 |
| 状态 | 初稿（待评审） |
| 上游文档 | [PRD v0.1](wechat-archive-prd.md) · [技术调研报告](wechat-local-access-survey.md) |
| 密级 | 内部 |

---

## 1. 设计目标与原则

**目标**：把 PRD 定义的功能需求（采集/归档/分析/预警/管理台）落成一套可在内网单机起步、后续可平滑拆分的系统。

**原则**：

1. **主轨优先**：架构围绕「本地 DB 解密」设计为不依赖任何登录窗口的主干；实时 hook（WCF）作为可整体摘除的增强模块——M0 验证失败不影响产品核心价值；
2. **单机起步**：MVP 阶段全部组件部署在一台 Windows 主机，零运维；接口按拆分预留（采集端与平台走 HTTP），后续平台可迁 Linux；
3. **拒绝过度设计**：不上消息队列、不上微服务、不上 ES——SQLite FTS5 覆盖检索，APScheduler 覆盖调度，单体覆盖一切；
4. **数据安全红线**：会话数据与密钥类文件一律不进 git（.gitignore 已拦截），导出操作全部审计。

## 2. 总体架构

```
┌─────────────────────────── Windows 采集主机（与登录微信同机）───────────────────────────┐
│                                                                                       │
│  [微信 PC 客户端 3.9.12]                                                              │
│        │ 本地加密 SQLite                    ┌──────────────────────────────┐          │
│        ▼                                    │        collector 采集端       │          │
│  ┌──────────────┐   内存取密钥+解密          │  ┌────────────────────────┐  │          │
│  │ 微信数据目录  │ ──────────────────────▶   │  │ decrypt_worker         │  │          │
│  └──────────────┘   （主轨：历史+定时增量）   │  │ (PyWxDump/WDA 封装)    │  │          │
│                                              │  └────────────────────────┘  │          │
│  ┌──────────────┐   DLL 消息回调（可选）      │  ┌────────────────────────┐  │          │
│  │ WCF 注入 DLL │ ──────────────────────▶   │  │ wcf_worker（可摘除）    │  │          │
│  └──────────────┘                           │  └───────────┬────────────┘  │          │
│                                             │      统一变换 transform       │          │
│                                             │      （标准化+指纹去重）       │          │
│                                             └──────────────┬───────────────┘          │
└────────────────────────────────────────────────────────────┼──────────────────────────┘
                                                   HTTP /api/v1/ingest（唯一通道）
                                                              ▼
┌───────────────────────────── 平台服务端 server（MVP 同机 / V1 可迁内网 Linux）──────────┐
│  FastAPI 单体                                                                          │
│  ┌─────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ ingest  │ │ 领域服务      │ │ 分析引擎 jobs │ │ 预警引擎    │ │ 通知分发 dispatcher │  │
│  │ 接收去重 │ │ 客户/映射/检索 │ │ 聚合+健康度   │ │ 规则扫描   │ │ 站内/邮件/企微      │  │
│  └────┬────┘ └──────┬───────┘ └──────┬───────┘ └─────┬─────┘ └─────────┬──────────┘  │
│       └─────────────┴────────┬───────┴───────────────┴─────────────────┘            │
│                              ▼                                                       │
│                 SQLite（WAL + FTS5） + media/ 媒体目录                                │
└───────────────────────────────────────────────────────────────────────────────────────┘
                                                              ▲
                                              HTTP（内网浏览器）
                                                              │
                                                   ┌──────────┴──────────┐
                                                   │   web 管理台 (Vue3)  │
                                                   └─────────────────────┘
```

## 3. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 采集端 | Python 3.10+ | PyWxDump / WeChatDataAnalysis / wcferry SDK 均为 Python 生态，无第二选择 |
| 调度 | APScheduler | 单进程内覆盖定时增量、预警巡检、聚合任务，免额外组件 |
| 服务端 | FastAPI + SQLAlchemy | 与采集端同语言，一套技术栈两个人力成本减半；自动生成 OpenAPI 文档 |
| 存储 | SQLite（WAL 模式）+ FTS5 | 10 万级消息量完全够用；FTS5 提供中文全文检索（unicode61 分词 + 按需二元分词）；零部署 |
| 认证 | JWT + RBAC（内置 admin/manager/sales 三角色） | 内网场景够用，不引入 OAuth 复杂度 |
| 前端 | Vue3 + Vite + Element Plus + ECharts | 管理台成熟组合；主题定制遵循团队 UI 偏好（大圆角、柔和阴影、pill 控件、微交互） |
| 图表 | ECharts | 趋势图/词云/时段热力开箱即用 |

**明确不引入**：MySQL/PG（schema 用 SQLAlchemy 写，迁移成本可控时再换）、Redis、ES、Docker（Windows 主机上直接跑 venv + 前端构建产物）。

## 4. 数据模型设计

### 4.1 实体关系

```
app_user ──< customer(owner) 
customer ──< chat_session(归属映射, 可空=待认领)
chat_session ──< message
customer ──< contact(单聊联系人挂靠)
member(内部名单) ── 判定 message.sender_type
alert_rule ──< alert ──< notify_record
```

### 4.2 核心表

**chat_session（会话，群聊/单聊统一模型）**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| wx_id | TEXT UNIQUE | 微信会话 ID（群 ID 或对方 wxid） |
| type | TEXT | `group` / `dm`，单聊群聊分区的依据 |
| name | TEXT | 群名 / 联系人备注名（快照） |
| customer_id | FK 可空 | 归属客户；空 = 待认领 |
| last_msg_at | DATETIME | 冗余，列表排序与沉默计算用 |
| status | TEXT | `active` / `archived` |

**message（消息）**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| session_id | FK | |
| sender_wxid | TEXT | 发送者 wxid；系统消息为空 |
| sender_type | TEXT | `external` / `internal` / `me` / `system`，由内部成员名单判定 |
| msg_type | TEXT | `text` / `image` / `video` / `voice` / `file` / `quote` / `emoji` / `system` |
| content | TEXT | 文本正文；媒体类存占位与摘要 |
| media_path | TEXT 可空 | media/ 下的相对路径 |
| media_meta | JSON 可空 | 大小/时长/文件名等 |
| ts | DATETIME | 消息时间（取微信原始时间戳） |
| fingerprint | TEXT UNIQUE | 去重指纹：sha256(wx_id + sender + ts + content_hash) |
| source | TEXT | `decrypt` / `wcf`，双轨数据溯源与对账 |
| raw | JSON | 原始结构，保底可回放 |

索引：`session_id + ts` 复合、`fingerprint` 唯一、`content` FTS5 虚表（外部内容表模式，随 message 增删同步）。媒体文件不入库，存 `media/` 目录（按 session_id 分桶），经鉴权接口下发。

**其余表（简）**

| 表 | 关键字段 | 用途 |
|---|---|---|
| customer | name, industry, stage, owner_user_id, health_score, health_level | 客户档案 + 健康度冗余 |
| contact | wx_id, nickname, remark, customer_id | 单聊联系人挂靠（F2-3） |
| member | match_type, match_value, display_name | 内部成员名单（F2-4），sender_type 判定依据 |
| group_member_snap | session_id, wx_id, first_seen_at, left_at | 群成员快照与退群事件（F2-5，退群预警输入） |
| message_daily | session_id, date, total, ext_count, int_count, reply_latencies(JSON) | **日聚合表**：仪表盘与趋势图直接读此表，不扫 message |
| alert_rule | code, params(JSON), level, enabled, cooldown | 规则引擎配置 |
| alert | rule_code, customer_id, session_id, message_id, level, status, detail(JSON), handle_note | 预警流水：pending/handled/ignored |
| notify_record | alert_id, channel, target, status, error | 通知发送留痕 |
| keyword | category(`risk`/`focus`), word, enabled | 风险词库 + 关注词库 |
| sync_task | type, status, stats(JSON), log | 采集任务历史（F1-5 监控数据源） |
| audit_log | user_id, action, target, detail | 全操作审计（导出必记） |

### 4.3 消息指纹与双轨去重

- 同一条消息可能被解密轨和 WCF 轨各采一次：以 `fingerprint` 唯一约束 + `INSERT OR IGNORE` 幂等入库，`source` 保留先到者；
- 对账视图（F1-4）：按 session 统计双轨条数差异，差异超阈值告警给系统管理员；
- 解密轨以 ts 为准（微信原始时间戳），WCF 轨回调时间仅作参考。

## 5. 模块设计

### 5.1 collector 采集端

```
collector/
├── config.example.yaml      # 微信数据目录、server 地址、token、调度周期
├── decrypt_worker/          # 主轨
│   ├── full_import.py       # 全量历史导入（M0 验证对象）
│   └── incr_sync.py         # 定时增量解密（默认每小时）
├── wcf_worker/              # 实时轨（feature flag 控制，可整体摘除）
│   └── callback.py          # wcferry 消息回调 → 标准化
├── transform/               # 统一变换：原始结构 → 标准 message + fingerprint
├── sender.py                # 批量上报 server（500 条/批，失败重试+本地暂存）
└── scheduler.py             # APScheduler 入口
```

设计要点：

- **单一出站通道**：两条轨产出的消息都经 transform 归一后走同一上报接口，服务端无感知来源差异；
- **断点续传**：每会话记录已同步水位（最后消息 ts），增量只取水位之后；全量导入支持按会话分片、失败重跑；
- **降级联动**：wcf_worker 启动失败/掉线超过阈值 → 自动切回解密轨分钟级加密增量（降级预案已在 PRD 第 7/10 节定义）；
- **发送隔离**：F8 代发能力做成独立模块 + 配置开关，**默认关闭**，与采集代码物理分离，永不自动触发。

### 5.2 server 平台服务端

```
server/app/
├── api/            # REST 路由（见第 6 节）
├── models/         # SQLAlchemy 模型 + FTS5 触发器
├── services/
│   ├── ingest.py       # 批量入库 + 指纹去重 + sender_type 判定
│   ├── mapping.py      # 客户/群/联系人映射
│   ├── analysis.py     # 聚合、健康度、检索
│   ├── alert_engine.py # 规则评估（触发型 + 巡检型）
│   ├── notify.py       # 渠道适配：inapp / email / wecom-webhook
│   └── exporter.py     # CSV/HTML 导出（写审计日志）
└── jobs/           # APScheduler 任务：增量聚合 / 健康度重算 / 沉默巡检 / 群成员快照
```

**预警引擎双模式**：

| 模式 | 规则 | 触发时机 |
|---|---|---|
| 触发型（消息驱动） | 响应超时、风险词命中 | ingest 入库后同步评估该消息 |
| 巡检型（时间驱动） | 客户沉默、长期不活跃、采集异常 | 定时巡检（沉默类每日一次；采集异常每 5 分钟） |

每条规则带 `cooldown` 冷却时间，避免同一客户重复轰炸；退群预警由 group_member_snap 差异比对产生事件。

**健康度模型（F4-4）**：`score = w1·活跃度 + w2·响应达标率 + w3·沉默惩罚 + w4·风险信号`，权重存 settings 可调；输出 0-100 分 + 红/黄/绿三档，写入 customer 冗余字段，巡检时每小时重算。MVP 不实现，V1 上线时先用默认权重（60/20/10/10）跑通再调参。

### 5.3 web 管理台

页面结构与 PRD F7 一一对应（仪表盘/客户列表/客户详情/会话浏览器/预警中心/采集管理/系统设置），设计约定：

- 会话浏览器为最高频页面：虚拟滚动（长会话万条级）、定位消息高亮 + 上下文展开、媒体懒加载；
- 视觉规范遵循团队偏好：大圆角卡片、柔和阴影、pill 筛选控件、主色渐变、hover 微交互；文档与导出样式保持朴素；
- 预警中心支持「点击预警 → 会话浏览器定位到触发消息」的深链。

## 6. 接口设计（REST /api/v1 概要）

| 分组 | 端点 | 说明 |
|---|---|---|
| 认证 | POST /auth/login · GET /auth/me | JWT |
| 客户 | /customers CRUD · POST /customers/{id}/claim（认领会话） | F2 |
| 会话 | GET /sessions?claimed=false · POST /sessions/{id}/map | 待认领列表与映射 |
| 消息 | GET /messages?session_id&q&from&to&sender_type&msg_type · GET /messages/{id}/context | 检索 + 上下文（keyset 分页） |
| 媒体 | GET /media/{path} | 鉴权后下发，不走静态目录 |
| 分析 | GET /dashboard · GET /analytics/customers/{id}/overview · GET /analytics/trends | 读 message_daily |
| 预警 | /alert-rules CRUD · GET /alerts?status= · POST /alerts/{id}/handle | F5 |
| 通知 | /notify-channels · POST /notify-channels/{id}/test | F6 |
| **采集上报** | POST /ingest/messages（批量）· POST /ingest/sync-tasks · GET /ingest/health | collector 专用，独立 token 认证 |
| 管理 | /users · /members · /keywords · /settings · /audit-logs | F7 设置页 |

## 7. 关键流程

**① 历史导入（MVP 第一跑）**
管理员在采集管理页发起 → full_import 解密全库 → transform 按会话分片 → 批量上报 → server 去重入库 → 前端展示任务进度与统计（会话数/消息数/时间跨度）→ 完成后进入「待认领」流程。

**② 定时增量（无 WCF 时的日常）**
APScheduler 每小时 → incr_sync 增量解密水位后的新消息 → 同一上报通道入库 → 更新 session.last_msg_at。

**③ 实时回调（WCF 可用时）**
WCF callback 收到消息 → transform → 上报 → ingest 入库 → 触发型预警评估（响应超时/风险词）→ 命中则预警 + 通知分发。

**④ 预警巡检（时间驱动）**
沉默巡检（每日）：读 customer 关联 session 的 last_msg_at → 生成/去重预警；采集异常巡检（每 5 分钟）：检查 sync_task 最新心跳，超阈值红警给系统管理员。

**⑤ 部署形态演进**
M0/MVP：单机 all-in-one（WeChat + collector + server + SQLite + web 静态产物），内网浏览器访问；V1：server + SQLite 可原样迁 Linux 内网服务器，collector 留在 Windows 采集主机，仅改 config 中 server 地址——因为唯一通道是 HTTP，无需改代码。

## 8. 关键设计决策记录

| # | 决策 | 备选（否决原因） |
|---|---|---|
| D1 | 群聊/单聊统一为 chat_session，type 字段区分 | 分表（检索、映射、聚合都要写两遍） |
| D2 | SQLite + FTS5 起步 | MySQL+ES（内网单机增加两个运维件，数据量未到） |
| D3 | 采集端→平台走 HTTP 唯一通道 | 共享 SQLite 文件（绑死同机部署，拆分时全部重写） |
| D4 | 采集端与平台同为 Python | Node/Go 服务端（采集端生态锁死 Python，双语言无收益） |
| D5 | WCF 轨做成可摘除模块 + 降级联动 | 全押 WCF（M0 登录验证存在失败可能，架构不能押在最脆弱环节） |
| D6 | 发送能力独立模块 + 默认关闭 | 与采集同模块（封号风险隔离，防止误触发） |
| D7 | 分析读日聚合表，不扫明细 | 实时聚合（仪表盘每次全表扫，10 万级后不可接受） |

## 9. 安全设计

| 层面 | 措施 |
|---|---|
| 认证授权 | JWT（8h 过期）、三角色 RBAC（admin/manager/sales）、sales 仅见自己客户 |
| 数据边界 | 服务只绑内网网卡；媒体经鉴权接口下发；数据库文件与 media/ 目录禁入 git（已配 .gitignore） |
| 审计 | 导出、预警处理、映射变更、账号操作全量审计日志 |
| 传输 | 内网 HTTP 起步；如需跨网段，上 Nginx 反代 + TLS，不在应用层实现 |
| 备份 | SQLite 单文件 + media/ 目录，提供一键备份脚本（deploy/backup），建议每日任务 |

## 10. 与里程碑的对应关系

| 里程碑 | 本设计中的交付物 |
|---|---|
| M0 技术验证 | collector/decrypt_worker/full_import.py 原型（PyWxDump 跑通 + 字段映射表确认）；wcf_worker 最小回调 demo；产出「字段质量评估」结论回填 PRD/本设计 |
| MVP | 全部 P0 需求对应模块：ingest + mapping + 会话浏览器 + 活跃度分析 + 基础页面；单机部署脚本 |
| V1 | wcf_worker 正式启用（视 M0 结论）+ 触发型/巡检型预警 + 通知渠道 + 健康度 + RBAC 完整版 |
| V2 | AI 摘要（F4-6，模型选型届时评估）、语音转写、发送模块（谨慎决策） |

---

*ArchCore 系统设计文档 v0.1 · 2026-09-21 · 内部资料。设计遵循调研报告结论：主轨不依赖登录窗口，实时轨可摘除。*

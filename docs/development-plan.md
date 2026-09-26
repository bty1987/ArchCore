# ArchCore 代码工程规划

| | |
|---|---|
| 文档版本 | v0.2 |
| 日期 | 2026-09-21 |
| 状态 | v0.2（评审修订） |
| 上游文档 | [系统设计 v0.1](system-design.md) · [PRD v0.1](wechat-archive-prd.md) |
| 密级 | 内部 |

---

## 1. 文档定位

把系统设计落到**可执行的工程规范与开发任务**：仓库结构定到文件级、迭代拆到 ticket 级、质量口径定到可验收。原则延续设计文档：单机起步、拒绝过度设计、主轨优先。

## 2. 仓库结构与工程划分

Monorepo，四工程一目录，各自独立依赖清单：

```
ArchCore/
├── docs/                          # 文档（共 8 份，见 README 索引）
├── collector/                     # 采集端 [Python]
│   ├── pyproject.toml             # 依赖：apscheduler httpx pywxdump(可选)
│   ├── config.example.yaml
│   ├── src/archcore_collector/
│   │   ├── main.py                # 入口：加载配置 → 启动 scheduler
│   │   ├── config.py              # pydantic-settings 配置模型
│   │   ├── decrypt_worker/
│   │   │   ├── full_import.py     # [M0] 全量历史导入原型
│   │   │   └── incr_sync.py       # 定时增量（水位管理）
│   │   ├── transform/
│   │   │   ├── filter.py          # 会话白名单过滤（F1-6，数据不出微信目录）
│   │   │   └── normalize.py       # 原始结构 → 标准 message（指纹由 server 端计算）
│   │   ├── sender.py              # 批量上报（500/批、重试、本地暂存）
│   │   └── scheduler.py
│   └── tests/
├── server/                        # 平台服务端 [Python/FastAPI]
│   ├── pyproject.toml             # 依赖：fastapi uvicorn sqlalchemy alembic apscheduler pydantic-settings
│   ├── alembic/                   # 数据库迁移（版本化）
│   ├── src/archcore_server/
│   │   ├── main.py                # app 工厂 + 路由挂载 + jobs 启动
│   │   ├── core/
│   │   │   ├── config.py          # 环境/密钥/开关（send_enabled 默认 false）
│   │   │   ├── security.py        # JWT + RBAC 依赖
│   │   │   └── db.py              # engine/session（WAL、FTS5 初始化）
│   │   ├── models/                # SQLAlchemy：chat_session/message/customer/...（唯一 schema 源）
│   │   ├── schemas/               # Pydantic 请求/响应模型
│   │   ├── api/
│   │   │   ├── auth.py  customers.py  sessions.py  messages.py
│   │   │   ├── analytics.py  alerts.py  notify.py  admin.py
│   │   │   └── ingest.py          # collector 专用（独立 token）
│   │   ├── services/
│   │   │   ├── ingest.py  mapping.py  analysis.py
│   │   │   ├── alert_engine.py  notify.py  exporter.py
│   │   └── jobs/
│   │       ├── aggregate.py       # message_daily 聚合
│   │       ├── health.py          # 健康度重算 [V1]
│   │       └── inspectors.py      # 沉默巡检/采集异常巡检
│   └── tests/
├── web/                           # 管理台 [Vue3 + TS + Vite]
│   ├── package.json
│   └── src/
│       ├── api/                   # 按 server OpenAPI 生成的类型 + 请求封装
│       ├── stores/                # pinia：auth / alert 未读数
│       ├── views/
│       │   ├── Dashboard.vue  CustomerList.vue  CustomerDetail.vue
│       │   ├── SessionBrowser.vue  AlertCenter.vue
│       │   ├── CollectorPanel.vue  Settings.vue  Login.vue
│       └── components/            # MessageFlow(虚拟滚动)/FilterBar/HealthBadge/...
├── deploy/
│   ├── backup.py                  # SQLite + media/ 一键备份
│   ├── install-windows.md         # 单机部署手册
│   └── archcore-server.service    # [V1] Linux 迁移用 systemd 单元
└── scripts/
    └── gen-fixtures.py            # 脱敏测试数据生成器
```

**依赖方向**：`web → server(HTTP/OpenAPI) → SQLite`；`collector → server(HTTP /ingest)`。collector 与 server **代码零共享**——去重指纹仅由 server 端计算（系统设计 4.3/D8），collector 不实现指纹算法，保证未来拆机部署无隐性耦合。

## 3. 工程规范

| 项 | 规范 |
|---|---|
| Python | 3.10+；类型注解强制（服务层/转换层）；ruff 一并承担 lint + format |
| 提交前检查 | pre-commit：ruff check + ruff format + 基础检查；web 端 eslint + prettier |
| 测试 | pytest + httpx TestClient（server）；核心层（transform/ingest（含指纹与 svr_id 去重）/alert_engine）为必测范围，其余按需 |
| 日志 | 标准 logging，统一格式 `时间 级别 模块 事件 键值对`；采集端每次同步任务一条汇总日志（会话数/条数/耗时/失败数） |
| 错误处理 | collector 上报失败不丢数据：本地 SQLite 暂存队列 + 指数退避重试；server API 统一错误体 `{code, message, detail}` |
| 配置 | pydantic-settings：YAML + 环境变量覆盖；**禁止**密钥/路径写死进代码；`config.yaml` 在 .gitignore 中（example 入库） |
| 命名 | Python snake_case / Vue 组件 PascalCase / API 路径复数资源 kebab-free；表名单数、字段 snake_case |
| 分支 | main 受保护（不直接 push）；功能分支 `feat/<ticket-id>-<slug>`；Conventional Commits（仓库已按此执行） |
| 版本 | SemVer；MVP 起打 tag（v0.1.0 起）；文档与代码同仓库同版本 |

**Windows 注意事项**：所有文件 IO 显式 `encoding="utf-8"`；路径用 pathlib；计划任务用 APScheduler 进程内跑（不依赖 Windows 任务计划）；微信数据目录路径从配置读（不同版本安装位置不同）。

## 4. 契约先行与数据演进

1. **schema 源头唯一**：SQLAlchemy models 是唯一 schema 定义；变更一律走 alembic 迁移（`alembic revision --autogenerate` + 人工确认），禁止手改库；
2. **API 契约即文档**：FastAPI 自动产出 OpenAPI；web 端用 openapi-typescript 生成 TS 类型，接口改动前后端同步感知；
3. **采集协议向后兼容**：`/ingest/messages` 的消息 schema 带 `schema_ver` 字段；server 对旧版本字段做兼容解析，避免升级期间采集端/平台版本错位丢数据；
4. **raw 字段保底**：消息原始结构永久保留（JSON），任何解析缺陷都可离线重放修复，这是历史数据不可再得的保险。

## 5. 迭代计划（任务拆解）

### M0 技术验证（1 周，spike 标准：跑通即达标，不要求工程规范）

| Ticket | 任务 | 产出/验收 |
|---|---|---|
| M0-01 | 装微信 3.9.12（关自动更新）+ 小号登录实测 | 登录成功/失败结论（PRD 第九节 #1#2） |
| M0-02 | PyWxDump 全量解密跑通 | 解密库文件 + 消息/会话/联系人表清单 |
| M0-03 | 字段映射评估：微信库字段 → 标准 message 模型 | 《字段映射与质量评估》笔记回填本仓库 docs/（含：媒体路径可达性、时间戳口径、群成员可获取性） |
| ~~M0-04~~ | ~~wcferry 最小回调 demo~~（已取消：WCFerry 路线移除，见调研报告） | —— |
| M0-05 | 结论决策：实时轨启用 or 降级；4.x 兜底是否成立 | 更新 PRD/设计的对应开关与排期 |
| M0-06 | 微信 4.x + WeChatDataAnalysis 解密验证（兜底路线） | 历史可导出 + 字段质量结论（调研报告 #6） |
| ~~M0-07~~ | ~~WCF 位数匹配确认~~（已取消：WCFerry 路线移除） | —— |
| M0-08 | 解密库群成员数据可得性抽查 | F2-5 可交付性结论（调研报告 #8） |
| M0-09 | 撤回/红包/转账/系统消息残留情况 | PRD 3.3 消息边界口径结论（调研报告 #9） |

### MVP（4~6 周，5 个迭代，每个以「可运行 + 可演示」收口；单人每迭代 4~6 张票为上限，超出砍范围不压工期）

| 迭代 | Ticket | 任务 | 对应需求 |
|---|---|---|---|
| M1 服务端地基 | MVP-101 | server 骨架：app 工厂/配置/日志/alembic 初始迁移（全量表结构） | — |
| | MVP-102 | models + FTS5（trigram）虚表 + ingest API（svr_id/指纹去重，指纹 server 端计算） | F1-4 |
| | MVP-103 | 认证 + 内置 admin 账号 | F7 设置 |
| M2 采集端 | MVP-201 | transform：normalize + 会话白名单过滤 | F1-4/F1-6 |
| | MVP-202 | full_import 工程化（M0 原型重构：分片/水位/重跑） | F1-1 |
| | MVP-203 | incr_sync 定时增量 + sync_task 记录 | F1-2(手动/定时) |
| | MVP-204 | sender 重试与本地暂存 | 可靠性 |
| M3 会话与检索 | MVP-301 | 消息检索 API（组合过滤 + 上下文 + keyset 分页） | F3-2/F3-3 |
| | MVP-302 | 媒体鉴权下发接口 | F3-1 |
| | MVP-303 | SessionBrowser 页面（虚拟滚动/高亮/懒加载） | F3-1 |
| M4 客户与映射 | MVP-401 | customer CRUD + 待认领/映射 API | F2-1/F2-2 |
| | MVP-402 | 内部成员名单 + sender_type 判定 | F2-4 |
| | MVP-403 | CustomerList/CustomerDetail 基础页 | F7 |
| M5 分析与收口 | MVP-501 | aggregate job + 活跃度 API | F4-1 |
| | MVP-502 | Dashboard 简化版（总量/趋势/待认领数） | F7 |
| | MVP-503 | 采集管理页（任务历史/状态） | F1-5 基础 |
| | MVP-504 | 部署手册 + 备份脚本 + 性能验收（10 万条 <2s） | PRD 验收 #3 |

### V1（+6 周，预警与实时轨）

| Ticket | 任务 | 对应需求 |
|---|---|---|
| V1-101 | alert_rule/alert API + 规则配置页 | F5-1 |
| V1-102 | 触发型引擎（ingest 后评估：响应超时/风险词） | F5 |
| V1-103 | 巡检型引擎（沉默/不活跃/采集异常） | F5 |
| V1-104 | 通知渠道：站内/邮件/企微 webhook + 发送留痕 | F6-1~3 |
| V1-105 | AlertCenter 页面（流水/处理/深链定位） | F5-2/F5-3 |
| V1-106 | 健康度模型 + 客户红黄绿 | F4-4 |
| V1-107 | 响应时效/关键词/参与结构分析 | F4-2/F4-3/F4-5 |
| V1-108 | RBAC 完整 + 审计日志页面 | 安全设计 |
| V1-109 | wcf_worker 正式版（视 M0-05 结论）+ 降级联动 | F1-3 |
| V1-110 | 群成员快照 + 退群预警（依赖 WCF 轨；解密库群成员不全，WCF 不可用则暂缓，以 M0-08 结论定） | F2-5 |
| V1-111 | 导出（CSV/HTML + 审计） | F3-5 |
| V1-112 | 消息标注/标签 | F3-4 |

V2（AI 摘要、语音转写、发送模块）届时另立规划，不在此排期。

## 6. 测试策略

| 层 | 手段 | 重点 |
|---|---|---|
| 纯函数层 | pytest 单测 | server 端 fingerprint 稳定性（同输入永远同指纹）与 svr_id 优先去重、normalize 边界（缺字段/系统消息/媒体占位）、filter 白名单命中 |
| server API | httpx TestClient + 内存库 | ingest 幂等（重放同批数据条数不增）、检索过滤组合、权限（sales 越界 403） |
| 采集→入库链路 | gen-fixtures.py 造脱敏样本库 → 跑 full_import → 断言落库条数与抽样内容 | M0-03 字段映射结论固化为断言，防微信版本差异引入回归 |
| 性能 | 脚本灌 10 万条样本消息 | PRD 验收 #3：组合检索 <2s；不达标先加索引/调 FTS 分词，不换数据库 |
| 前端 | 手工验收清单（每迭代附） | 关键路径：检索→定位→上下文；映射→列表联动 |

**测试数据红线**：任何真实会话数据不入仓库（.gitignore 已挡 data/）；demo/测试一律用 gen-fixtures 生成或手工脱敏样本。

## 7. 质量口径（DoD）

每个 ticket 收口标准：ruff 无告警 → 必测范围单测通过 → 手工冒烟通过 → Conventional Commit → PR 合入 main。每个迭代收口标准：可运行、可演示、部署手册同步更新、无已知 P0/P1 缺陷。MVP 整体收口 = PRD 第九节验收标准逐条打勾。

## 8. 风险与技术债登记（起始）

| 编号 | 事项 | 处置 |
|---|---|---|
| TD-1 | M0 字段映射结论未定前，models/message 字段可能返工 | M1 迁移初版按PRD 3.3 保守设计，M0-03 结论出来后一次修订 |
| TD-2 | FTS5 中文分词（v0.2 已消解） | 直接采用 trigram 分词（SQLite 3.34+），MVP-301 用真实样本验证效果即可 |
| TD-3 | PyWxDump 对 3.9.12 的支持版本细节 | M0-02 首日验证，不行即切 WeChatDataAnalysis（接口留 adapter 层） |
| TD-4 | 单人开发节奏风险 | 迭代按可独立演示切分，任意迭代中止都有可用产物；排期已按单人 MVP 4~6 周口径修订，超出即砍范围不压工期 |
| TD-5 | 4.x 解密兜底工具（WeChatDataAnalysis/DbkeyHook）成熟度未实测 | M0-06 首周验证；不可用则冻结 3.9.x 版本组合，加密保护现有采集环境并评估存量数据续采方案 |

---

*ArchCore 代码工程规划 v0.2 · 2026-09-21 · 内部资料。迭代排期以 M0-05 决策结论为调整点。*

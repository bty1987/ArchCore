# Customer OS 衔接分析（与 ArchCore 的对比、复用与融合路径）

| | |
|---|---|
| 文档版本 | v1.0 |
| 日期 | 2026-09-26 |
| 性质 | 产品方向研究：对 docs/customer-os/ 五件套方案的分析与 ArchCore 的衔接评估 |
| 上游资料 | docs/customer-os/（竞品拆解/定位/PRD/架构/90天路线，2026-09-26 版） |
| 密级 | 内部 |

---

## 1. 这套方案是什么

基于 2026 年公开资料整理的「中小企业 Customer OS」完整产品方案（七家竞品拆解 → 定位 → MVP PRD → 技术架构 → 90 天路线），核心主张：

> **Conversation + CRM + Automation + AI**——帮助中小企业把分散在微信（企微）、WhatsApp、网站等渠道的客户对话，转化为可管理、可自动化、可成交的客户资产。

与 ArchCore 的根本差异：**ArchCore 是「被动归档观察者」（个人微信解密），Customer OS 是「主动经营参与者」（官方多渠道 SaaS）**。两者解决不同问题，但领域模型高度同构。

## 2. 与 ArchCore 的对比

| 维度 | ArchCore（现项目） | Customer OS（方案） |
|---|---|---|
| 渠道合规 | 个人微信解密（灰色） | 官方 API / WebChat（合规） |
| 形态 | 单机内网部署 | 多租户 Freemium SaaS |
| 客户模型 | 一个群 ≈ 一个客户（微信视角） | Contact 360（经营视角） |
| 商业 | 内网部署 + 年度维保 | Freemium + AI 收费 + Partner |
| 技术栈 | Python/FastAPI/SQLite/Vue | 文档建议 Java/微服务/PG |
| 目标用户 | 自己 / 有 IT 的企业 | 5~200 人 SMB 注册即用 |

## 3. 交叉印证：两份独立来源得出同一结论

文档核心原则（原文）：**「个人微信第三方 API 不应该成为产品核心依赖」**，渠道优先级：

> 官方企微/WhatsApp/Meta/WebChat API > 第三方 Connector > UI Automation > 协议逆向

这与本项目 2026-09-25~26 的**实机试错结论完全吻合**（见实战复盘 §5）：

| 文档优先级档位 | 我们的同档实测 | 结果 |
|---|---|---|
| 协议逆向 | PadLocal（网关下线）、3.9 伪装登录三档 | ❌ 全灭 |
| UI Automation | pywechat/pywxauto 在 4.1.15.13（自绘表面） | ❌ 死；**4.1.8.67 上存活**（讲述人前置） |
| 第三方 Connector | libencode（800 终身，待获取） | ⚠️ 可用但分发封闭 |
| 官方 API | 企微 WorkPro token（已验证到扫码层） | ✅ 存活 |

**两份独立来源（我们的实机试错 + 该方案的公开资料研究）指向同一结论——「合规官方渠道是唯一可持续路径」现在是铁的结论。**

## 4. 领域模型映射：ArchCore 就是 Customer OS Core 的雏形

| Customer OS 概念 | ArchCore 现有实现 | 复用度 |
|---|---|---|
| Contact 360 | customer + 客户详情页（健康度/趋势/标签/预警时间线） | ★★★ 高 |
| Conversation / Inbox | chat_session + message + 检索/上下文/标签 | ★★★ 高 |
| Tag | message_tag + 标签汇总 | ★★★ 已实现 |
| Timeline | message 流 + alert 时间线 | ★★★ 已实现 |
| AI Summary | services/ai.py（可插拔 LLM）+ 客户摘要 | ★★★ 代码就绪 |
| Analytics/Reports | message_daily + insights 聚合 + 洞察页 | ★★★ 已实现 |
| Assignment | customer.owner_user_id + sales 数据边界 | ★★★ 已实现（RBAC） |
| Notification | notify.py（站内/企微/邮件） | ★★★ 已实现 |
| **Workspace（多租户）** | ❌ 无（单租户） | 🔴 缺口 |
| **WebChat 渠道** | ❌ 无 | 🔴 缺口 |
| **Workflow 引擎** | ❌ 无（预警引擎是它的一个特例） | 🔴 缺口 |
| Channel Adapter 统一模型 | 解密源适配层（DecryptSource Protocol）+ 桥接框架 | ★★ 架构同构，渠道不同 |
| Event Model | ingest 事件驱动 + APScheduler | ★★ 部分具备 |

**结论：ArchCore 不是 Customer OS 的对手，是它的 Core Service 雏形。** 90 天路线的 0~30 天清单（Workspace/Contact/Inbox/WebChat/Tag/Assignment/Timeline/Workflow/AI Summary/AI Reply）中，**我们已完成 6/10**（Contact/Inbox/Tag/Assignment/Timeline/AI Summary），缺 4 个：**Workspace 多租户、WebChat 渠道、Workflow 引擎、AI Reply**。

## 5. 融合路径评估（三条路）

### 路径 1：渐进演进（推荐）

在 ArchCore 现有代码上加 **workspace_id 多租户字段**（alembic 迁移 + 全表 + 查询过滤），FastAPI 单体直接作为 Customer OS 的 Core Service——**不采纳文档的 Java/微服务建议**（单人开发效率优先，FastAPI 性能足够支撑 SMB 规模）。

- 增量工作：workspace 迁移、WebChat 渠道组件、Workflow 引擎（可从预警引擎泛化）
- 优势：现有管理台/检索/分析/预警全部保留并自动获得多租户能力
- 风险：单租户假设散落在查询中，改造面需评估（预估 1~2 周）

### 路径 2：WebChat 原型先行（市场验证优先）

不先做多租户，先做**单租户 WebChat demo**（文档的最短价值链：客户在网页发消息 → 自动建档 → AI 总结 → 接管）——两周内可验证市场反应，有真实用户再走路径 1。

### 路径 3：按文档 Java 新建

❌ 不建议——重复造 Core，单人成本不可承受。

## 6. 个微解密轨在新格局中的位置

文档原则「个人微信第三方 API 不作核心依赖」**不影响 ArchCore 解密轨的存续**：

- 解密轨降级为「**微信历史数据导入器**」——把存量个人微信会话批量灌入 Customer OS（作为 Channel Adapter 之一，与 WebChat/企微并列）；
- 发送仍由人在微信正常操作（4.1.8.67 + pyweixin 程序化发送作为受治理的辅助）；
- 这恰好构成差异化：**竞品（尘锋/微盛）做不了个人微信存量归档，我们可以**——存量迁移能力本身是获客钩子。

## 7. 决策点与建议

| 决策 | 时机 | 建议 |
|---|---|---|
| 是否立项 Customer OS | 商业判断 | 先入档研究，ArchCore 照常运行 |
| 路径 1 / 2 / 3 | 有第一个潜在 SaaS 客户时 | 路径 2（WebChat demo 两周验证）→ 反馈好走路径 1 |
| Java vs Python | 路径 1 启动时 | Python/FastAPI 演进（单人与 SMB 规模效率优先） |
| libencode 800 | 发送刚需时 | 与 Customer OS 无耦合——它是微信 Connector 层的选项 |
| 企微通道 | 使用企微时 | WorkPro token / PyWeWork（文档方案里的官方企微 API 同理） |

## 8. 立即可做的低成本动作（不动现有系统）

1. **WebChat 原型 demo**（路径 2 首步）：FastAPI 加一个 `/webchat` 页面 + WebSocket 消息端点 + WebChat Channel Adapter——与现有 ingest 管线对接，访客消息直接进 Inbox；
2. **Workspace 字段预埋**：即使不做多租户，新表设计统一预留 workspace_id（成本趋零，未来多租户免返工）；
3. **Workflow 引擎设计稿**：预警引擎泛化为规则引擎的设计文档（事件 → 条件 → 动作），为 Customer OS 的自动化模块铺路。

以上三项均为增量、不破坏现有功能，合计约一周工作量。

---

*Customer OS 衔接分析 v1.0 · 2026-09-26 · 内部资料。本文档是对 docs/customer-os/ 方案的评估与衔接规划，不构成立项决策；立项需结合商业验证（路径 2 的市场反馈）。*

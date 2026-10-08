<div align="center">

# ArchCore

**微信客户会话归档与分析平台**

_让每一条客户消息，都变成企业可以理解和经营的业务资产。_

[![star](https://gitee.com/bty1987/ArchCore/badge/star.svg?theme=gitee)](https://gitee.com/bty1987/ArchCore/stargazers)
[![fork](https://gitee.com/bty1987/ArchCore/badge/fork.svg?theme=gitee)](https://gitee.com/bty1987/ArchCore/fork)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
![Vue](https://img.shields.io/badge/Vue-3.x-42B883)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20%2B%20FTS5-003B57)

</div>

---

## 这是什么

ArchCore 是一套**部署在你自己电脑/内网**的微信客户会话归档与分析平台：把微信群聊与客户单聊消息自动归档成可检索、可分析、可预警的**客户资产**，围绕 **"一个微信群 ≈ 一个客户"** 的核心模型做客户维度的办公分析。

**它解决的真实痛点：**

- 客户在微信群里说了需求，三天后没人找得到那条消息；
- 员工离职，客户沟通记录跟着走，接手的人两眼一抹黑；
- 老板问"这个客户聊到哪了"，答案只能靠员工回忆。

**数据边界（卖点，也是底线）**：系统部署在你自己的电脑/内网，数据全程不离开你的服务器；系统**只收不发**——不做任何自动群发、加好友类操作。

## 核心能力

| 能力 | 说明 |
|---|---|
| 🗄️ 全量归档 | 历史消息一次导入：自研微信 4.x 本地库解密（冻结 4.1.8.67，17 个库解密零异常） |
| 🔄 自动增量 | WAL 监听器 + 30 分钟定时任务双自动同步，新消息自动入库、断点续传 |
| 🔍 秒级检索 | SQLite FTS5 全文检索：按客户、关键词、时间、发送者定位任何一段对话（10 万条 <2s） |
| 👤 客户档案 | 微信群自动映射客户档案，沟通历史一页看全，配标签体系 |
| 🚨 主动预警 | 响应超时、投诉、报价、竞品提及等规则引擎 → 推送企业微信等通知渠道 |
| 📊 基础分析 | 消息量趋势、响应时长、成员活跃（ECharts 可视化） |
| 🧩 富内容解析 | 图片/引用/合并转发等富媒体消息解析归档 |
| 🤖 AI 摘要 | 会话 AI 摘要与自动标签 |
| ⚡ 实时轨（可选） | WeChatFerry hook 实时增强轨（技术验证中，非当前依赖） |

## 系统架构

```text
微信客户端 (4.x)
 │ 本地数据库（历史全量 + WAL 实时增量）
 ▼
collector 采集端 ─── 白名单过滤 · 解密适配 · 批量上报 / 断点续传
 │ HTTP 上报
 ▼
server 服务端（FastAPI + SQLAlchemy + SQLite WAL/FTS5 + APScheduler）
 ├─ 归档入库（alembic 迁移管理）
 ├─ 群 → 客户映射 / 客户档案
 ├─ 预警引擎 + 通知渠道
 └─ 定时任务（增量同步、心跳报告）
 │
 ├──▶ web 管理台（Vue3 + Element Plus + ECharts）
 └──▶ 通知推送（企业微信等）
```

采集路线：**主轨 = 本地数据库解密**（历史 + 周期增量，已实机验证）；**实时轨 = WeChatFerry hook**（可选增强，技术验证中）。

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 服务端 | Python 3.10+ · FastAPI · SQLAlchemy 2 · Alembic · APScheduler · PyJWT | REST API、认证、定时任务 |
| 存储 | SQLite（WAL + FTS5） | 单文件内网存储，备份即拷贝文件 |
| 采集端 | Python（fixture / 自研 4.x 解密适配） | 白名单过滤、批量上报、断点续传 |
| 前端 | Vue 3 · Element Plus · ECharts · Vite | 内网管理台 |
| 质量 | pytest · ruff | server 33 + collector 13 全绿，ruff 0 告警 |

## 快速开始（开发/演示）

```bat
python -m venv .venv && .venv\Scripts\pip install -e server -e collector
python scripts\gen-fixtures.py            # 生成脱敏合成数据（红线：真实数据不入仓库）
cd server && ..\.venv\Scripts\python -m uvicorn archcore_server.main:app --port 8000
cd web && npm install && npm run dev      # 管理台 http://127.0.0.1:5173
python scripts\perf_check.py              # 性能验收：10 万条检索 <2s
```

> 登录账号：未设置 `ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD` 时为 admin / admin123456；设置了该环境变量（或用 start-server.bat 启动）则以设置的值为准。首次登录后建议改密。

正式部署（个人单机形态：fixture 跑通 → 4.x 解密归档 → 建档分析 → 备份排查）见[本机部署实操指南](docs/local-deploy-guide.md)；测试与质量门禁见 [docs/test-plan.md](docs/test-plan.md)。

## 目录结构

```text
ArchCore/
├── docs/       # 产品与调研文档（见下方索引）
├── server/     # 平台服务端：FastAPI + SQLAlchemy + SQLite(WAL+FTS5) + alembic + APScheduler
├── collector/  # 采集端：解密适配（fixture/pywxdump）+ 白名单过滤 + 批量上报/断点续传 + WCF 可选
├── web/        # 管理台前端：Vue3 + Element Plus + ECharts（vite build → dist/）
├── deploy/     # 部署：单机手册 / 一键备份 / systemd 单元 / 交付工具箱
└── scripts/    # 解密与增量同步 · 合成数据生成 · 性能验证 · 心跳报告
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [docs/wechat-local-access-survey.md](docs/wechat-local-access-survey.md) | 技术调研报告 v1.1（接入路线、同类工具全景、风险评估、9 项 P0 验证清单） |
| [docs/wechat-archive-prd.md](docs/wechat-archive-prd.md) | PRD v0.2（功能需求、预警规则、版本规划、验收标准） |
| [docs/system-design.md](docs/system-design.md) | 系统设计文档 v0.2（总体架构、技术选型、数据模型、关键流程、设计决策记录） |
| [docs/development-plan.md](docs/development-plan.md) | 代码工程规划 v0.2（仓库结构、工程规范、迭代任务拆解 M0/MVP/V1、测试策略） |
| [docs/ops-promotion-plan.md](docs/ops-promotion-plan.md) | 运维与推广规划 v0.2（监控/备份/版本冻结/Runbook/账号资产、三阶段推广路径/定价/交付流程） |
| [docs/outbound-push-plan.md](docs/outbound-push-plan.md) | 主动推送消息方案 v0.2（默认永久只收不发；外发风险分级、工单管道与熔断的实施预案） |
| [docs/compliance-plan.md](docs/compliance-plan.md) | 合规方案 v0.1（第三方个人信息告知、数据最小化、权限收敛、合同责任划分） |
| [docs/test-plan.md](docs/test-plan.md) | 测试方案 v1.0（八层测试体系、46 个自动化用例清单、性能与冒烟、M0 真机验证项） |
| [docs/local-deploy-guide.md](docs/local-deploy-guide.md) | 本机部署实操指南 v1.1（个人单机形态：fixture 跑通 → 4.x 解密归档 → 建档分析 → 备份排查） |
| [docs/retrospective-20260926.md](docs/retrospective-20260926.md) | 实战复盘与决策档案 v1.0（4.x 攻关时间线/决策档案/踩坑清单/生态地图/试错成本/方法论） |
| [docs/customer-os/](docs/customer-os/) | Customer OS 产品方案五件套（竞品拆解/定位/PRD/架构/90天路线，2026-09 方向研究） |
| [docs/customer-os-analysis.md](docs/customer-os-analysis.md) | Customer OS 衔接分析 v1.0（与 ArchCore 对比/领域模型映射/三条融合路径/决策点） |
| [docs/productization-gap-analysis.md](docs/productization-gap-analysis.md) | 产品化差距分析 v1.1（四层差距盘点：交付力/支撑体系/合规/售前材料，P0 清单现状标注与 6~8 周节奏） |
| [docs/product-scenarios.md](docs/product-scenarios.md) | 应用场景与商业定位分析（愿景素材，见文首交付边界说明） |
| [deploy/交付工具箱/](deploy/交付工具箱/) | 交付工程化：客户交付档案模板（版本冻结登记/账号台账/上线检查/验收签字）+ 媒体本体归档攻关任务卡（2026-10-01） |
| [docs/合规文件包/](docs/合规文件包/) | 入群告知与员工知情话术模板 + 合同条款模板（角色/数据归属/账号风险/版本冻结/责任上限；待法务复核） |
| [docs/售前工具箱/](docs/售前工具箱/) | 一页纸介绍 / 15 分钟演示脚本 / FAQ 与预期管理红线 / 定价表（内部勿外发）（2026-10-01） |
| [docs/自媒体推广作战包.md](docs/自媒体推广作战包.md) | 内容线推广 v1.0：3+1 账号矩阵 / 公开内容五红线 / 首批 10 篇选题 / 私域漏斗 / 60 天可证伪门槛（口碑线并行） |

## 里程碑

- **M0 技术验证**：✅ 2026-09-25~26 实机完成（路线定型：冻结 4.1.8.67、自研 4.x 解密 17 库零异常、pyweixin 发送回环验证；3.9 路线终结）——见复盘档案；剩余=阶段 0 内部试点（真实业务连用 1 个月）
- **MVP**（4~6 周）：历史导入（白名单范围）、群→客户映射、会话浏览器、活跃度分析、管理台基础页面（✅ 代码已落地，见 test-plan）
- **V1**（+6 周）：实时轨、预警引擎、通知渠道、健康度模型（预警/通知/健康度核心已随 MVP 代码就位）

## 常见问题（FAQ）

**Q：数据会上传到云端吗？**
不会。归档数据全部存放在你自己服务器/电脑上的 SQLite 单文件库中，系统只收不发，备份即拷贝文件（见[一键备份脚本](deploy/backup.py)）。

**Q：支持哪些微信版本？**
当前技术路线冻结在 **微信 4.1.8.67**（自研 4.x 本地库解密）；3.9 路线已于 2026-09 终结。微信版本升级可能导致路线失效，版本冻结与应对策略见[复盘档案](docs/retrospective-20260926.md)。

**Q：和第三方会话存档 SaaS 比有什么不同？**
会话数据是客户资产，也是敏感个人信息，出域即失控。本项目的差异化就是"数据不出内网 + 只收不发"：部署在你自己的机器上，不依赖任何外部云服务。

**Q：商用交付前需要做哪些合规动作？**
归档涉及客户方成员（第三方个人信息主体）的会话数据，正式商用前须完成[合规方案](docs/compliance-plan.md)所列评估项：入群/员工告知话术、合同责任条款、数据最小化与权限收敛等（模板见[合规文件包](docs/合规文件包/)）。

## 风险提示与使用边界

本项目采用的非官方微信接入方案存在违反微信用户协议与**封号风险**（详见[调研报告](docs/wechat-local-access-survey.md)），仅限内部客户管理用途；归档涉及客户方成员（第三方个人信息主体）的会话数据，正式商用前须完成[合规方案](docs/compliance-plan.md)所列评估项。

请勿将本项目用于批量营销群发、自动加好友、爬取他人会话数据等任何"主动外发"类场景。

## 许可证

本项目暂未附带开源许可证，**默认保留所有权利（All Rights Reserved）**。当前面向内部试点与授权交付；如需评估、试用或二次集成，请先与作者取得联系。

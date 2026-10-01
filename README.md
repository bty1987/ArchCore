# ArchCore

微信客户会话归档与分析平台 —— 基于本地客户端采集的微信群/单聊消息归档、客户维度办公分析与预警管理。

## 项目定位

- **核心模型**：一个微信群 ≈ 一个客户，围绕客户进行沟通资产沉淀与办公分析；
- **采集路线**：主轨 = 本地数据库解密（历史 + 周期增量），实时轨 = WeChatFerry hook（可选增强，依赖技术验证）；
- **产品形态**：内网 Web 管理台（分析 / 记录检索 / 预警 / 通知）。

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
| [docs/product-scenarios.md](docs/product-scenarios.md) | 应用场景与商业定位分析（愿景素材，见文首交付边界说明） |
| [deploy/交付工具箱/](deploy/交付工具箱/) | 交付工程化：客户交付档案模板（版本冻结登记/账号台账/上线检查/验收签字）+ 媒体本体归档攻关任务卡（2026-10-01） |
| [docs/合规文件包/](docs/合规文件包/) | 入群告知与员工知情话术模板 + 合同条款模板（角色/数据归属/账号风险/版本冻结/责任上限；待法务复核） |
| [docs/售前工具箱/](docs/售前工具箱/) | 一页纸介绍 / 15 分钟演示脚本 / FAQ 与预期管理红线 / 定价表（内部勿外发）（2026-10-01） |

## 目录规划

```
ArchCore/
├── docs/       # 产品与调研文档（9 份，见索引）
├── server/     # 平台服务端：FastAPI + SQLAlchemy + SQLite(WAL+FTS5) + alembic + APScheduler
├── collector/  # 采集端：解密适配（fixture/pywxdump）+ 白名单过滤 + 批量上报/断点续传 + WCF 可选
├── web/        # 管理台前端：Vue3 + Element Plus + ECharts（vite build → dist/）
├── deploy/     # 部署：单机手册 / 一键备份 / systemd 单元
└── scripts/    # gen-fixtures 合成数据 · perf_check 10 万条性能验证
```

## 快速开始（开发/演示）

```bat
python -m venv .venv && .venv\Scripts\pip install -e server -e collector
python scripts\gen-fixtures.py            # 生成脱敏合成数据（红线：真实数据不入仓库）
cd server && ..\.venv\Scripts\python -m uvicorn archcore_server.main:app --port 8000
cd web && npm install && npm run dev      # 管理台 http://127.0.0.1:5173
python scripts\perf_check.py              # 性能验收：10 万条检索 <2s
```

> 登录账号：未设置 `ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD` 时为 admin / admin123456；设置了该环境变量（或用 start-server.bat 启动）则以设置的值为准。首次登录后建议改密。

测试与质量门禁见 [docs/test-plan.md](docs/test-plan.md)（当前：server 33 + collector 13 全绿，ruff 0 告警）。

## 里程碑

- **M0 技术验证**：✅ 2026-09-25~26 实机完成（路线定型：冻结 4.1.8.67、自研 4.x 解密 17 库零异常、pyweixin 发送回环验证；3.9 路线终结）——见复盘档案；剩余=阶段 0 内部试点（真实业务连用 1 个月）
- **MVP**（4~6 周）：历史导入（白名单范围）、群→客户映射、会话浏览器、活跃度分析、管理台基础页面（✅ 代码已落地，见 test-plan）
- **V1**（+6 周）：实时轨、预警引擎、通知渠道、健康度模型（预警/通知/健康度核心已随 MVP 代码就位）

## 风险提示

本项目采用的非官方微信接入方案存在违反微信用户协议与封号风险（详见调研报告），仅限内部客户管理用途；归档涉及客户方成员（第三方个人信息主体）的会话数据，正式商用前须完成[合规方案](docs/compliance-plan.md)所列评估项。

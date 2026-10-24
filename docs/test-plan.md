# ArchCore 测试方案（具体测试方案 v1.0）

| | |
|---|---|
| 文档版本 | v1.1（2026-10-15 修订：路线口径与用例数同步现状） |
| 日期 | 2026-09-23（v1.1 修订 2026-10-15） |
| 状态 | 随代码持续维护；路线锚定微信 4.1.8.67 |
| 上游文档 | [代码工程规划 v0.2](development-plan.md) §6 · [PRD v0.2](wechat-archive-prd.md) §9 |
| 密级 | 内部 |

---

## 1. 分层测试体系

| 层 | 手段 | 位置 | 当前状态 |
|---|---|---|---|
| L1 纯函数单测 | pytest | `server/tests`、`collector/tests` | ✅ 全绿 |
| L2 server API 测试 | httpx TestClient + 临时 SQLite | `server/tests/` | ✅ 全绿 |
| L3 采集→入库链路 | gen-fixtures 合成库 + 真实 uvicorn 进程 | `collector/tests/test_e2e_pipeline.py` | ✅ 全绿 |
| L4 数据库迁移 | alembic upgrade head + FTS 检索断言 | `server/tests/test_migrations.py` | ✅ 全绿 |
| L5 性能 | 10 万条灌库脚本 | `scripts/perf_check.py` | ✅ FTS 50ms / 组合 1ms（<2s 达标） |
| L6 进程级冒烟 | 真实 uvicorn + urllib 全链路 | 本文档 §4（脚本化） | ✅ 5 步全过 |
| L7 前端 | **vitest 单测**(auth store/改密表单/对话流基线)+ Vite build + 手工验收清单 | `web/tests/`,npm test | ✅ 9 用例全绿 / 清单待真机 |
| L8 M0 真机验证 | 微信 4.1.8.67 实机 | 调研报告第九节 | ✅ 2026-09-25~26 完成（登录/解密 17 库零异常/端到端归档检索） |
| L9 工具链离线自测 | Frida hook 解析逻辑 mock 断言 | `research/hook/selftest.py` 等 | ✅ 收侧 17 字段 + 发送信封 13 字段 |

## 2. 运行方式

```bat
:: 全部单元/API/链路/迁移测试（73 个）
cd server   && ..\.venv\Scripts\python -m pytest tests -q      # 50 passed
cd collector && ..\.venv\Scripts\python -m pytest tests -q     # 23 passed

:: 代码规范
python -m ruff check server collector scripts && python -m ruff format --check server collector scripts

:: 性能验收（PRD #3：10 万条组合检索 <2s）
python scripts/perf_check.py --rows 100000

:: 合成演示/测试数据（红线：永不使用真实会话数据）
python scripts/gen-fixtures.py --out ./data/fixture_wechat.db
```

## 3. 测试用例清单（已自动化）

### 3.1 认证与 RBAC（test_auth_rbac.py）
- 登录成功/密码错误 401；无 token 401；`/auth/me` 身份正确；
- sales 角色写操作 403；sales 数据边界：客户列表/消息检索只见自己负责的客户。

### 3.2 采集入库（test_ingest.py）
- 批量入库成功计数；**同批重放幂等**（重放 inserted=0，总数不增）——对应工程规划 §6 测试红线；
- 采集端 token 校验（缺失/错误 401）；
- **去重第一优先 svr_id、指纹兜底**：同会话同发送者同秒同内容去重 1 条；同秒不同内容/发送者不误杀；
- sender_type 判定：采集号=me、成员名单=internal、其余=external、系统消息=system；
- sync-task 上报与 /ingest/health。

### 3.3 检索（test_search.py）
- FTS trigram 中文检索（≥3 字）；2 字回退 LIKE；
- 组合过滤（时间窗 + sender_type + msg_type + 会话）；
- keyset 分页正确性（cursor 推进、无重复无遗漏）；
- 消息上下文（前 N + 锚点 + 后 N 有序）；
- sales 角色消息边界（未映射到他客户的会话不可见）。

### 3.4 预警引擎（test_alerts.py）
- 风险词命中 → 红/预警 + 站内通知负责人；
- 冷却窗口内第二条命中**不重复**告警；
- 响应超时：客户发言 4h（工作时间口径）无回复 → 橙/预警；我方已回复不误报；
- 非工作时间（22:00→次日 06:00）不计入工作分钟、不触发；
- 沉默巡检（客户方 10 天未发言 → 黄/预警）且冷却期内不重复；
- 采集异常巡检（最近同步超 2h → 红/预警）；无任务不误报；
- 预警处理流转 + 审计留痕。

### 3.5 映射/分析/导出（test_mapping_analytics.py）
- 待认领列表 → 映射 → 解除映射回到待认领；
- 日聚合 + 仪表盘统计 + 趋势接口；
- 响应时延统计（达标/未达标样本、P50、SLA 率）；
- 健康度重算（0-100 分 + 红黄绿分级落库）；
- CSV 导出内容正确且**写审计日志**；
- 指纹稳定性（同输入恒同指纹，防实现漂移）；
- 词库管理 + 新增词立即生效触发预警。

### 3.6 采集端单测（collector/tests/test_transform.py）
- normalize：基本字段、媒体占位（`[file] 合同.pdf`）、缺会话/缺时间返回 None、svr_id 数字转字符串；
- 白名单：精确群号、群名正则、单聊开关、配置往返。

### 3.7 端到端链路（test_e2e_pipeline.py，真实 HTTP）
- fixture 合成库 → 白名单过滤（家庭群被拦截）→ full_import → 落库条数与 manifest 一致；
- **全量重跑幂等**（svr_id 去重，总数不变）；
- 水位增量：无新数据 0 条；追加 3 条（含 1 条白名单外）只采 2 条；
- **断点续传**：server 不可达时批次留 outbox 退避，恢复后冲刷成功、零丢失；
- 链路后 server 检索命中、白名单外数据**不可检索**（根本未入库）。

### 3.8 迁移（test_migrations.py）
- upgrade head 生成全部 17 张表 + message_fts 虚表 + alembic_version；
- 迁移后 FTS 中文检索可用；重复 upgrade 幂等。

## 4. 进程级冒烟（上线前必跑）

真实 uvicorn 进程 + 环境变量注入，验证「启动→登录→上报→去重→检索→仪表盘→认领映射」：

1. 服务启动健康检查通过；
2. admin 登录获取 token；
3. 采集端通道上报 2 条（重放全部 skipped）；
4. 中文关键词检索命中 1 条；
5. 仪表盘统计正确；待认领群认领到客户后 claimed_sessions=1。

结果记录在发布说明中；任何一步失败禁止部署。

## 5. 前端验收清单（真机手工）

- [ ] 登录 → 仪表盘四卡 + 趋势图渲染；
- [ ] 客户列表搜索/筛选/新建/导出 CSV（触发下载）；
- [ ] 客户详情：认领待认领群 → 趋势/响应指标刷新；
- [ ] 会话检索：选会话/关键词/方向过滤、加载更多（keyset）、点击消息展开上下文抽屉；
- [ ] 预警中心：待处理/已处理/已忽略流转、规则启停开关；
- [ ] 采集管理：健康状态、审计日志表；
- [ ] 系统设置四 Tab：账号/成员名单/词库/通知渠道（含企微 webhook「测试」实发）；
- [ ] sales 账号登录验证数据边界（只见自己客户）。

## 6. M0 真机验证项（✅ 2026-09-25~26 已完成）

实测结论（详见[复盘档案](retrospective-20260926.md)）：微信 **4.1.8.67 登录成功**（3.9 整代被服务端拒，版本伪装无效）；**自研 4.x 解密管线 17 库零 HMAC 异常**；端到端归档→检索→预警验证通过；群成员可得性由 4.x `contact.db` 的 `chatroom_member` 提供（不再依赖已移除的 WCF 轨）。

**剩余待补**：MVP 验收 #1（与客户端人工核对一致率）——需用真实库抽样 200 条核对，排入阶段 0 试点。

> 附：2026-10 新增产品化能力的测试入口 `server/tests/test_p1_quickwins.py`（AI 周报/管家/管道仪表）与 `test_auth_rbac.py` 的改密用例。

## 7. 质量门禁（DoD，工程规划 §7 重申）

每次合入：ruff 0 告警 → pytest 全绿（73：server 50 + collector 23）+ vitest 全绿（web 9）→ 冒烟通过 → Conventional Commit → PR 合入。

**测试数据含时间的红线**：断言依赖「近 N 天」窗口的用例，时间戳必须相对 `utcnow` 且避开 UTC 午夜档（v1.1 修订前有两处硬编码日期用例在翻月/跨日后必炸，已修）。
每个迭代：可运行可演示 + 本文档清单同步更新。

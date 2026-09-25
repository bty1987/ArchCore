# ArchCore 本机部署实操指南（个人聊天记录归档与分析）

| | |
|---|---|
| 文档版本 | v1.0 |
| 日期 | 2026-09-23 |
| 适用形态 | **单机 all-in-one**：一台 Windows 主机 = 微信客户端 + 采集端 + 服务端 + 数据库 + 管理台 |
| 数据边界 | 全部数据存在**本机** `data/` 目录，不上传任何服务器 |
| 密级 | 内部 |

---

## 0. 开始前：两条路径与风险告知

本指南有两条路径，建议**先 A 后 B**：

- **路径 A（5 分钟跑通）**：用合成演示数据把「导入 → 档案 → 检索 → 分析 → 预警」全流程走一遍，不碰微信。适合先确认这套东西是不是你想要的；
- **路径 B（真实聊天记录）**：接入你本机已登录的微信本地数据库，导入真实历史消息并持续增量归档。

**路径 B 的三条风险，先读再动手：**

1. **版本窗口**：微信 PC 3.9.12 是旧版本，腾讯服务端对新号/新设备可能拒绝登录（提示「版本过低」）。这是外部前提，不是本方案能保证的（详见调研报告第四节）；
2. **封号风险**：解密读取本地库属于非官方接入。本方案**只收不发**（不做任何自动发消息），风险相对可控，但请使用你能承受的账号；建议不要用主力个人号，也不要频繁换设备登录；
3. **隐私边界**：归档的聊天记录包含**对话方**（同事/客户/家人）的内容。自用归档没问题，但不要把数据库分享、公开或用于对话方未知情的其他用途（见[合规方案](compliance-plan.md)精神）。

**诚实的预期管理**：真实解密链路的字段映射（M0-02/03）尚未在真实环境实测过——本文档就是首次实测手册。第 7~8 步首跑若报「解密库结构与预期不符」，属于预期内的首次验证工作，按 12.3 排查即可，不影响架构。路径 A 无此不确定性。

---

## 1. 环境准备（一次性，约 10 分钟）

| 要求 | 说明 |
|---|---|
| Windows 10/11 x64 | 采集端必须 Windows（微信本地库在 Windows 上） |
| Python 3.10+ | 实测 3.14 可用；[python.org](https://www.python.org/downloads/) 安装时勾选 **Add to PATH** |
| Node.js 18+ | 仅管理台前端构建需要 |
| git | 拉取仓库用（也可直接下载 zip 解压） |

```bat
:: 1) 取代码（假设装到 D:\archcore，下文所有路径以此为准）
git clone https://gitee.com/bty1987/ArchCore.git D:\archcore
cd /d D:\archcore

:: 2) Python 虚拟环境 + 依赖（服务端与采集端）
python -m venv .venv
.venv\Scripts\pip install -e server -e collector

:: 3) 生成两个随机密钥（记下来，第 5 步要用）
.venv\Scripts\python -c "import secrets; print('JWT_SECRET:', secrets.token_hex(32))"
.venv\Scripts\python -c "import secrets; print('COLLECTOR_TOKEN:', secrets.token_hex(16))"
```

---

## 2. 路径 A：合成数据 5 分钟跑通全流程

```bat
cd /d D:\archcore

:: 1) 生成脱敏合成微信库（3 个群 + 2 个单聊，约 4 个月消息量）
.venv\Scripts\python scripts\gen-fixtures.py --out data\fixture_wechat.db

:: 2) 写采集端配置
copy collector\config.example.yaml collector\config.yaml
```

编辑 `collector\config.yaml`，改成：

```yaml
server_base_url: http://127.0.0.1:8000
server_ingest_token: <第 1 步生成的 COLLECTOR_TOKEN>
collector_wxid: "wxid_staff_001"        # fixture 里的"我方"账号
state_db: ./data/collector_state.db
source:
  type: fixture
  fixture_path: ./data/fixture_wechat.db
whitelist:                               # fixture 里有两个业务群 + 一个家庭群
  groups: ["11111111@chatroom", "22222222@chatroom"]
  group_name_patterns: []
  allow_dm: true
```

```bat
:: 3) 启动服务端（新开一个窗口跑，或直接用第 5 步的 start-server.bat）
cd /d D:\archcore\server
set ARCHCORE_DB_URL=sqlite:///D:/archcore/data/archcore.db
set ARCHCORE_MEDIA_DIR=D:/archcore/data/media
set ARCHCORE_JWT_SECRET=<第 1 步生成的 JWT_SECRET>
set ARCHCORE_COLLECTOR_TOKEN=<同 config.yaml 里的 token>
set ARCHCORE_COLLECTOR_WXID=wxid_staff_001
set ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD=<你的管理台密码>
..\.venv\Scripts\uvicorn archcore_server.main:app --host 127.0.0.1 --port 8000
```

```bat
:: 4) 全量导入（回到仓库根目录）
cd /d D:\archcore
.venv\Scripts\archcore-collector -c collector\config.yaml --full
```

看到 `full_import done` 与统计即成功。然后做第 6 步打开管理台登录（admin / 你设的密码），应该能看到：待认领 2 个群 → 认领 → 仪表盘趋势 → 会话检索「报价」→ 预警中心有风险词命中。**走完这一遍，路径 B 只是换数据源而已。**

---

## 3. 路径 B（1）：微信 3.9.12 安装与登录

> 你的微信消息以**加密 SQLite 库**存在本机；解密工具从运行中的微信进程内存提取密钥。所以：**微信必须安装且保持登录在本机**。

1. **关闭微信自动更新**：安装前断网装完再登录；设置里关闭自动更新（若有）。后续**不要升级微信**（版本冻结策略，运维规划 2.5）；
2. 安装微信 **3.9.12（32 位）**。官方下载页通常只保留最新版，旧版安装包需自备（这是离线安装包存在的意义，运维规划 2.5）；
3. 用**你自己的账号**扫码登录（若提示「版本过低」被拒，见 12.1）；
4. 随便发几条消息，确认微信工作正常、本地已有新消息落库。

## 4. 路径 B（2）：pywxdump 解密与目录准备

```bat
:: 1) 安装解密工具（微信保持登录状态）
.venv\Scripts\pip install pywxdump

:: 2) 查看微信信息（确认能读到你的账号与数据目录；建议用管理员身份运行终端）
.venv\Scripts\wxdump info
```

记下输出里的 **`wxid_xxxxx`（你自己的 wxid，第 5/7 步要用）**。然后做一次解密导出（两种方式任选）：

- 用 pywxdump 自带 CLI 解密到固定目录，例如：
  ```bat
  .venv\Scripts\wxdump db decrypt -o D:\archcore\data\decrypt
  ```
  （不同版本子命令略有差异，可用 `wxdump --help` 查看，目标是拿到**解密后的 .db 文件目录**）；
- 或直接让采集端指向 pywxdump 的默认解密输出目录（第 7 步 `db_dir` 填它）。

确认 `D:\archcore\data\decrypt`（或你选的目录）下有 `MSG0.db`（或 MSG1…多个分库）、`MicroMsg.db` 等文件。

## 5. 路径 B（3）：初始化并启动服务端

把第 2 步的启动命令固化成 `D:\archcore\start-server.bat`（一次性写好，以后双击启动）：

```bat
@echo off
cd /d D:\archcore\server
set ARCHCORE_DB_URL=sqlite:///D:/archcore/data/archcore.db
set ARCHCORE_MEDIA_DIR=D:/archcore/data/media
set ARCHCORE_JWT_SECRET=<第 1 步生成的 JWT_SECRET>
set ARCHCORE_COLLECTOR_TOKEN=<第 1 步生成的 COLLECTOR_TOKEN>
set ARCHCORE_COLLECTOR_WXID=<第 4 步记下的你的 wxid>
set ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD=<你的管理台密码>
D:\archcore\.venv\Scripts\alembic upgrade head
D:\archcore\.venv\Scripts\uvicorn archcore_server.main:app --host 127.0.0.1 --port 8000
```

说明：

- `alembic upgrade head` 每次启动前跑一遍是幂等的（已是最新则无动作），省心；
- `ARCHCORE_COLLECTOR_WXID` **务必填你的 wxid**：它决定消息方向判定（你自己发的 = 「我」）。漏填的话你自己的消息会被当成客户方，响应时效分析会失真；
- 首次启动自动创建 `admin` 账号，密码取 `ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD`；
- 服务只绑 127.0.0.1，仅本机可访问。

## 6. 管理台

```bat
cd /d D:\archcore\web
npm install
npm run dev
```

浏览器打开 **http://127.0.0.1:5173**，`admin` + 你设的密码登录。个人长期使用也可以 `npm run build` 后用 `npm run preview`（同样代理到 8000 端口），更轻。

> 本机单用户形态下，「系统设置 → 账号」建销售/主管账号不是必需的；预警通知、词库、成员名单仍建议配置。

## 7. 路径 B（4）：配置采集端与白名单

编辑 `D:\archcore\collector\config.yaml`：

```yaml
server_base_url: http://127.0.0.1:8000
server_ingest_token: <与服务端 ARCHCORE_COLLECTOR_TOKEN 一致>
collector_wxid: "<你的 wxid>"
state_db: ./data/collector_state.db

source:
  type: pywxdump
  db_dir: "D:/archcore/data/decrypt"     # 第 4 步的解密输出目录

whitelist:                                # 合规与降噪边界：只归档你关心的会话
  groups: []                              # 先留空，用下面的命令查到群号再填
  group_name_patterns: []                 # 也可用群名正则，如 ['^ABC项目']
  allow_dm: true                          # 是否归档你的全部单聊（含家人/同事私聊），不想归就 false
```

**先查有哪些会话，再决定白名单**（避免一上来把全部聊天灌进去）：

```bat
cd /d D:\archcore
.venv\Scripts\python -c "import sys; sys.path.insert(0, 'collector/src'); from archcore_collector.config import load_config; from archcore_collector.sources import build_source; [print(s.type, s.wx_id, s.name) for s in build_source(load_config('collector/config.yaml').source).list_sessions()]"
```

输出是 `类型 群号/对方wxid 群名` 列表。把想归档的群号填进 `whitelist.groups`（群名显示为空时用群号识别；群名读取是尽力而为的，见 12.2）。

## 8. 路径 B（5）：全量导入与每日增量

```bat
cd /d D:\archcore
:: 全量导入历史消息（首次执行；几万条约 1~2 分钟，10 万+ 也只需几分钟）
.venv\Scripts\archcore-collector -c collector\config.yaml --full

:: 手动增量一次（拉取水位之后的新消息）
.venv\Scripts\archcore-collector -c collector\config.yaml --once

:: 常驻增量：每小时自动同步一次（关掉窗口即停止）
.venv\Scripts\archcore-collector -c collector\config.yaml
```

增量只采各会话水位之后的新消息；中断重跑安全（svr_id 幂等去重，不会重复入库）。**注意：微信需保持在本机登录**——它不在线，就没有新消息可采。

常驻可以做成开机自启（二选一）：

```bat
:: 方式一：启动文件夹放个 bat（最简单）
:: 把下面这行存为 %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\archcore-collector.bat
D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml

:: 方式二：任务计划
schtasks /Create /TN "ArchCore-Collector" /TR "D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml" /SC ONLOGON
```

## 9. 建档案：把会话变成「客户」

导入完成后回到管理台：

1. **客户列表 → 新建客户**：为你关心的人/项目建档（如「XX 项目」「家人群」也可是个「客户」）；
2. **客户详情 → 待认领会话**：把对应的群认领到该客户（一个客户可挂多个群）；
3. **系统设置 → 内部成员名单**：把家人/同事的 wxid 加进来（匹配类型选 wxid）——他们发言会被记为「我方同事」，你自己是「我」，其余是「客户方」；
4. **系统设置 → 词库**：内置了投诉/退款/竞品等风险词和报价/合同等关注词，可自行增删；
5. **系统设置 → 通知渠道**（可选）：填入企微群机器人 webhook，预警能推到你手机（级别 ≥ 橙才外发）。

## 10. 日常怎么用（功能速查）

| 想做什么 | 去哪里 |
|---|---|
| 看整体活跃、近 14 天趋势、待处理预警 | 仪表盘 |
| 看某个「客户」的活跃趋势、响应速度（P50/P90） | 客户列表 → 客户详情 |
| 翻历史聊天、按关键词/时间/方向过滤、看上下文 | 会话检索（关键词 ≥3 字走全文检索，2 字走模糊） |
| 客户沉默 / 响应超时 / 风险词 / 群长期不活跃提醒 | 预警中心（规则可停用，冷却防轰炸） |
| 确认采集是否正常 | 采集管理（最近同步时间、已归档条数） |
| 导出某客户全部记录（CSV） | 客户列表 → 导出（写审计日志） |

## 11. 备份

```bat
:: 手动备份（数据库一致性快照 + 配置）
cd /d D:\archcore
.venv\Scripts\python deploy\backup.py --db data\archcore.db --media data\media --config collector\config.yaml --out backups

:: 每天凌晨 3 点自动备份
schtasks /Create /TN "ArchCore-Backup" /TR "D:\archcore\.venv\Scripts\python.exe D:\archcore\deploy\backup.py --db D:\archcore\data\archcore.db --media D:\archcore\data\media --config D:\archcore\collector\config.yaml --out D:\archcore\backups" /SC DAILY /ST 03:00
```

备份目录建议复制一份到另一块盘/NAS。恢复 = 装 Python + 微信 3.9.12 → 还原 `archcore.db` 与 `config.yaml` → 启动登录即可。

---

## 12. 常见问题排查

### 12.1 微信 3.9.12 登录被拒（提示版本过低）

按顺序尝试：① 先装微信 4.x 登录一次，再装回 3.9.12 登录（「4.x 先登一次」法）；② 换常用老设备；③ 都不行说明该账号/设备的登录窗口已关闭——旧版登录权在腾讯服务端，这不是软件能绕的（调研报告第四节）。此时本工具对该账号不可用，请勿反复重试（加重风控）。

### 12.2 首跑报「解密库结构与预期不符」/ 群名都是空的

前者：说明你的 pywxdump 版本解密库结构与适配层假设不同（**预期内的 M0-02/03 首次验证**）。按报错里的表名/字段名，打开对应 .db 看 schema，修订 `collector\src\archcore_collector\pywxdump_source.py` 里的 SQL 与 `MSG_TYPE_MAP` 即可，改完重跑 `--full`（幂等）。后者：群名来自 MicroMsg.db 的 Contact 表，读取失败会降级为空名——不影响消息归档，用群号识别即可。

### 12.3 其他速查表

| 现象 | 原因与处理 |
|---|---|
| `pip install`/命令找不到 | 用 `.venv\Scripts\` 下的完整路径，或先 `.venv\Scripts\activate` |
| 管理台登录 401 | 服务端没起来（看 8000 端口窗口），或密码不对 |
| 导入后管理台没数据 | 采集端 token 与服务端不一致；或白名单没放行任何会话（看第 7 步查询命令输出） |
| `--full` 重跑会重复入库吗 | 不会，svr_id 幂等去重 |
| 检索不到刚导入的词 | 中文关键词 ≥3 字走全文检索；2 字走模糊匹配；确认该消息在被白名单放行的会话里 |
| 自己的消息显示成「客户方」 | `collector_wxid` 没配成你的 wxid（第 5/7 步），改后重新 `--full` |
| 增量采不到新消息 | 微信没在本机登录在线；或确认常驻采集端在跑 |
| 微信被自动升级导致解密失败 | 卸载 → 用离线安装包回滚 3.9.12 → 重新登录后重试；之后关闭自动更新 |

## 13. 已知限制（诚实清单）

- **真实解密链路未经实测**（M0-02/03）：本文档即首次验证手册，适配层已按多分库 + 群名尽力而为实现，但字段级确认只能在真实环境完成；
- **媒体文件**：图片/语音/视频/文件只归档占位与元数据（大小/文件名），本体提取是后续迭代项；
- **撤回消息、群成员快照**：口径以 M0-08/09 真机验证结论为准；
- **单机单账号**：只归档「本机登录的这个微信」的会话；想归档家人/同事的账号需要他们本机各跑一套（多采集端为 V2+ 评估项）；
- **不做任何发送**：系统只收不发，没有也不该有「替你回消息」的功能。

---

*ArchCore 本机部署实操指南 v1.0 · 2026-09-23 · 内部资料。非官方接入存在违反微信用户协议的风险，仅供个人归档研究使用，商用前须完成合规评估（见合规方案）。*

# ArchCore 本机部署实操指南（个人聊天记录归档与分析）

| | |
|---|---|
| 文档版本 | v1.2 |
| 日期 | 2026-10-15 |
| 适用形态 | **单机 all-in-one**：一台 Windows 主机 = 微信客户端 + 采集端 + 服务端 + 数据库 + 管理台 |
| 数据边界 | 全部数据存在**本机** `data/` 目录，不上传任何服务器 |
| 密级 | 内部 |

> **版本口径（2026-10-15 修订）**：本文 v1.0（2026-09-23）写作于 3.9.12 + pywxdump 时代。9-25~26 攻关后路线已变——**微信客户端冻结 4.1.8.67**（3.9 整代登录被服务端拒，版本伪装无效），采集主轨为**自研 4.x 解密管线**（`scripts/decrypt_wechat4.py`：双引擎密钥提取 + 逐库派生 + WAL 合并），采集端数据源类型为 `wechat4`。与 pywxdump 相关的旧章节已整体替换。产品化改造（一键安装/演示模式/首启强制改密/AI 周报/AI 助手/管道仪表）已并入本文。

---

## 0. 开始前：两条路径与风险告知

本指南有两条路径，建议**先 A 后 B**：

- **路径 A（5 分钟跑通）**：一条命令起演示环境（合成数据），把「导入 → 档案 → 检索 → 分析 → 预警」全流程走一遍，不碰微信。适合先确认这套东西是不是你想要的；
- **路径 B（真实聊天记录）**：接入你本机已登录的微信本地数据库，导入真实历史消息并持续增量归档。

**路径 B 的三条风险，先读再动手：**

1. **版本冻结**：路线锚定微信 **4.1.8.67**。升级微信可能让解密管线失效（密钥与库结构随版本变），因此**装好后必须关闭自动更新**（见 3.1）。微信版本升级后的恢复流程见 [复盘档案](retrospective-20260926.md)；
2. **封号风险**：解密读取本地库属于非官方接入。本方案**只收不发**（不做任何自动发消息），且为被动读盘（不注入、不修改微信进程），风险相对可控，但请使用你能承受的账号；建议不要用主力个人号；
3. **隐私边界**：归档的聊天记录包含**对话方**（同事/客户/家人）的内容。自用归档没问题，但不要把数据库分享、公开或用于对话方未知情的其他用途（见[合规方案](compliance-plan.md)精神）。

---

## 1. 环境准备

| 要求 | 说明 |
|---|---|
| Windows 10/11 x64 | 采集端必须 Windows（微信本地库在 Windows 上） |
| Python 3.10+ | 实测 3.14 可用；[python.org](https://www.python.org/downloads/) 安装时勾选 **Add to PATH** |
| Node.js 18+ | 管理台前端构建需要（仅演示/手动流程需要，`install.bat` 无 node 会优雅跳过） |
| git | 拉取仓库用（也可直接下载 zip 解压） |

### 1.1 一键安装（推荐）

```bat
git clone https://gitee.com/bty1987/ArchCore.git D:\archcore
cd /d D:\archcore
install.bat
```

`install.bat` 固化七步：建 venv → 装服务端/采集端依赖 → 生成配置（随机密钥）→ 数据库迁移 → 构建管理台。要点：

- 会交互询问**采集号 wxid**（形如 `wxid_xxxxx`，路径 B 第 3 步之后可回填）；
- 生成 `start-server.bat`（含随机 JWT/采集 token 与 bootstrap 密码，**不入 git**）与 `collector\config.yaml`；
- **已存在的配置文件一律保留**，重复安装安全；
- 安装结束会打印 bootstrap 密码——**首次登录后会被强制要求改密**（安全机制，见 6.1）。

### 1.2 手动安装（等价，便于理解每一步）

```bat
cd /d D:\archcore
python -m venv .venv
.venv\Scripts\pip install -e server -e collector

:: 生成两个随机密钥（记下来，第 5 步要用）
.venv\Scripts\python -c "import secrets; print('JWT_SECRET:', secrets.token_hex(32))"
.venv\Scripts\python -c "import secrets; print('COLLECTOR_TOKEN:', secrets.token_hex(16))"
```

---

## 2. 路径 A：一条命令跑通全流程（合成数据，5 分钟）

```bat
cd /d D:\archcore
run-demo.bat
```

它会自动完成：生成 120 天合成数据（3 群 + 2 单聊 + 2 客户）→ 写入演示专用采集配置 → 建**隔离数据库** `data/demo/archcore.db` → 全量导入 → 塑形预警场景（客户沉默 / 群不活跃 / 响应超时 / 风险词四类）→ 打开浏览器。

登录 **admin / demo-arch-2026**（演示密码，非默认值，不触发强制改密）。你应该能看到：

- **工作台**：今日概览（客户数、消息量、趋势图、Top 会话、健康度、待处理预警）
- **客户中心**：3 个已建档客户 + 待认领会话
- **消息检索**：按关键词「报价」检索命中
- **预警中心**：四类预警若干条，带处理/忽略闭环
- **洞察分析**：健康度分布、客户排行、词库命中、AI 经营周报（需配置 LLM，见 9.6）

> **数据隔离保证**：演示模式全部写在 `data/demo/` 下，与真实数据（`data/archcore.db`）完全隔离，可随时整目录删除。想换端口/密码见 `run-demo.bat` 顶部变量。

**走完这一遍，路径 B 只是换数据源而已。**

---

## 3. 路径 B（1）：微信 4.1.8.67 安装与登录

> 你的微信消息以**加密 SQLite 库（SQLCipher 4）**存在本机；解密从运行中的微信进程内存提取密钥。所以：**微信必须安装且保持登录在本机**。

### 3.1 装微信并关闭自动更新

1. 安装微信 **4.1.8.67**（64 位）。官方下载页只保留最新版，旧版安装包需自备并归档（离线包是部署与回滚的生命线，见[运维规划](ops-promotion-plan.md) 2.5）；
2. **关闭自动更新**（本机实查发现 `WeixinUpdate.exe` 常在，务必确认）：设置里关闭自动更新；稳妥起见可将安装目录下更新程序改名或阻断其网络；
3. 用**你自己的账号**扫码登录；4.1.8.67 实测可直接登录（无需任何伪装）；
4. 随便发几条消息，确认微信正常工作、本地已有新消息落库。

### 3.2 加密与密钥模型（了解即可，工具已封装）

- 4.x 数据目录：`xwechat_files/<账号>/db_storage/**.db`；SQLCipher 4 参数：页 4096B、PBKDF2-SHA512 256000 轮、AES-256-CBC、每页 reserve=80（IV 16B + HMAC-SHA512 64B）；
- **真实密钥 = 内存密钥 XOR 内部密钥**（`internal_db_key`）。内部密钥藏在安装目录 `Weixin.dll` 代码段（`mov rdx, imm64` 序列）；内存密钥在 `Weixin.exe` 私有内存中以指针桩模式定位，经 HMAC 校验确认；
- **每库用自身 salt 派生**，故须逐库派生（不能一把钥匙开所有库）。

## 4. 路径 B（2）：自研解密

```bat
cd /d D:\archcore

:: 全自动：找库 → 取钥（双引擎）→ 逐库解密 → 报告表结构
.venv\Scripts\python scripts\decrypt_wechat4.py

:: 数据目录不在默认位置（Documents）时指定
.venv\Scripts\python scripts\decrypt_wechat4.py --data-root "C:\Users\你\xwechat_files"

:: 拉取 WAL 增量：忽略已解密产物强制重解（每日增量同步会自动加此参数）
.venv\Scripts\python scripts\decrypt_wechat4.py --force

:: 只处理部分库（排查用）
.venv\Scripts\python scripts\decrypt_wechat4.py --db-filter message
```

**注意事项：**

- 需**管理员终端**（读进程内存要求）；
- 微信需**保持登录运行**（密钥在进程内存里）；
- 解密产物为普通 SQLite，输出到 `data/wechat4_plain/<账号>/`，供采集端 `wechat4` 源读取；
- 首次解密成功后，密钥会持久化到 `data/wechat4_key.json`——**之后解密无需微信进程在跑**（重装微信或重登后密钥轮换，此时删掉该文件重新提取）；
- 命令结束会打印各库页数/表结构摘要与 HMAC 异常率。**HMAC 异常率是机制变更哨兵**：正常应接近 0；若 ≥20 页且 >30% 异常，说明格式已变（多为微信被升级），工具会以退出码 2 报警，此时不要继续，按 12.2 处理。

---

## 5. 路径 B（3）：初始化并启动服务端

若用 `install.bat`，`start-server.bat` 已生成，直接双击即可。手动等价写法：

```bat
@echo off
cd /d D:\archcore\server
set ARCHCORE_DB_URL=sqlite:///D:/archcore/data/archcore.db
set ARCHCORE_MEDIA_DIR=D:/archcore/data/media
set ARCHCORE_JWT_SECRET=<第 1.2 步生成的 JWT_SECRET>
set ARCHCORE_COLLECTOR_TOKEN=<第 1.2 步生成的 COLLECTOR_TOKEN>
set ARCHCORE_COLLECTOR_WXID=<你的 wxid>
set ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD=<你的管理台密码>
D:\archcore\.venv\Scripts\alembic upgrade head
D:\archcore\.venv\Scripts\uvicorn archcore_server.main:app --host 127.0.0.1 --port 8000
```

说明：

- `alembic upgrade head` 每次启动前跑一遍是幂等的（已是最新则无动作），省心；
- `ARCHCORE_COLLECTOR_WXID` **务必填你的 wxid**：它决定消息方向判定（你自己发的 = 「我」）。**注意：数据目录名常带多开后缀（如 `wxid_xxx_a694`），而真实 wxid 不带后缀**——用不带后缀的值，否则你自己的消息会被判成客户方，响应时效分析失真；
- 服务只绑 127.0.0.1，仅本机可访问。

## 6. 管理台

```bat
cd /d D:\archcore\web
npm install
npm run dev
```

浏览器打开 **http://127.0.0.1:5173** 登录。个人长期使用可 `npm run build` 后由服务端静态托管，更轻。

### 6.1 首启强制改密

若登录密码是默认值（bootstrap 密码或历史默认 `admin123456` / `admin123`），登录后**会被强制跳转到改密页**，改完须重新登录才能进入系统。这是产品化要求的安全机制（避免演示/交付后长期使用弱口令）。

---

## 7. 路径 B（4）：配置采集端与白名单

编辑 `D:\archcore\collector\config.yaml`（`install.bat` 已生成骨架，核对以下字段）：

```yaml
server_base_url: http://127.0.0.1:8000
server_ingest_token: <与服务端 ARCHCORE_COLLECTOR_TOKEN 一致>
collector_wxid: "<你的 wxid，不带多开后缀>"
state_db: ./data/collector_state.db

source:
  type: wechat4                        # 4.x 主轨（自研解密产物）
  db_dir: ./data/wechat4_plain/<你的 wxid>   # 第 4 步解密输出目录

whitelist:                             # 合规与降噪边界：只归档你关心的会话
  allow_all: false                     # 个人本机测试可设 true：忽略白名单采全部（商用禁止）
  groups: []                           # 先留空，用下面的命令查到群号再填
  group_name_patterns: []              # 也可用群名正则，如 ['^ABC项目']
  allow_dm: true                       # 是否归档你的全部单聊（含家人/同事私聊），不想归就 false

schedule:
  incr_minutes: 60                     # 定时兜底增量周期
  flush_seconds: 30
send_enabled: false                    # 永久 false：归档系统只收不发
```

**先查有哪些会话，再决定白名单**（避免一上来把全部聊天灌进去）：

```bat
cd /d D:\archcore
.venv\Scripts\python -c "import sys; sys.path.insert(0, 'collector/src'); from archcore_collector.config import load_config; from archcore_collector.sources import build_source; [print(s.type, s.wx_id, s.name) for s in build_source(load_config('collector/config.yaml').source).list_sessions()]"
```

输出是 `类型 群号/对方wxid 群名` 列表。把想归档的群号填进 `whitelist.groups`。

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

增量只采各会话水位之后的新消息；中断重跑安全（svr_id 幂等去重，不会重复入库）。

**实时性说明**：本机的标准配置是**双自动同步**——

| 通道 | 机制 | 延迟 |
|---|---|---|
| WAL 监听器 | `scripts/watch_sync.py` 轮询消息库 mtime，触发解密+采集 | 分钟级 |
| 定时任务 | `scripts/sync-wechat4.bat`（`decrypt --force` + `collector --once`） | 30 分钟兜底 |

两者用 `schtasks` 注册即可（本机实例已如此配置）。注意：微信需保持在本机登录——它不在线，就没有新消息可采。

```bat
:: 常驻采集端的开机自启（二选一）
:: 方式一：启动文件夹放个 bat（最简单）
:: 把下面这行存为 %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\archcore-collector.bat
D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml

:: 方式二：任务计划
schtasks /Create /TN "ArchCore-Collector" /TR "D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml" /SC ONLOGON
```

## 9. 建档案与配置

导入完成后回到管理台：

1. **客户列表 → 新建客户**：为你关心的人/项目建档（如「XX 项目」「家人群」也可是个「客户」）；
2. **客户详情 → 待认领会话**：把对应的群认领到该客户（一个客户可挂多个群）；
3. **系统设置 → 内部成员名单**：把家人/同事的 wxid 加进来（匹配类型选 wxid）——他们发言会被记为「我方同事」，你自己是「我」，其余是「客户方」；
4. **系统设置 → 词库**：内置了投诉/退款/竞品等风险词和报价/合同等关注词，可自行增删；
5. **系统设置 → 通知渠道**（可选）：填入企微群机器人 webhook，预警能推到你手机（级别 ≥ 橙才外发）；
6. **AI 能力**（可选）：见 10.3。

## 10. 日常怎么用（功能速查）

### 10.1 核心功能

| 想做什么 | 去哪里 |
|---|---|
| 看整体活跃、近 14 天趋势、待处理预警 | 工作台（今日概览） |
| 看某个「客户」的活跃趋势、响应速度（P50/P90） | 客户列表 → 客户详情 |
| 翻历史聊天、按关键词/时间/方向过滤、看上下文 | 消息检索（关键词 ≥3 字走全文检索，2 字走模糊） |
| 客户沉默 / 响应超时 / 风险词 / 群长期不活跃提醒 | 预警中心（规则可停用，冷却防轰炸，处理闭环留痕） |
| 确认采集是否正常 | 采集与通道（管道仪表：成功率/耗时/最近成败/每日消息量） |
| 导出某客户全部记录（CSV） | 客户列表 → 导出（写审计日志） |
| 给关键消息打标签（如「报价」「承诺」） | 消息检索 → 消息下方「标注」（客户详情按标签汇总） |

### 10.2 管道仪表

「采集与通道」页顶部展示近 30 天同步成功率、平均耗时、最近成功/失败（失败带错误日志）与近 7 天每日消息量柱图——**采集静默失败一眼可见**，不需要翻日志。

### 10.3 AI 能力（可选，需配置 LLM）

在「系统设置 → AI 配置」填入 OpenAI 兼容端点（`api_base` / `api_key` / `model`）。**数据红线：内容只发往你所配置的端点**——用内网/私有 LLM 即全程不出内网。

| 能力 | 说明 |
|---|---|
| 会话 AI 摘要 | 客户详情页一键生成近 N 天会话摘要（含意向、风险、待办） |
| **AI 经营周报** | 洞察分析页：统计快照（消息量/新客户/活跃会话/预警分布）+ AI 撰写一页周报；**每周一 09:00 自动生成并推送通知渠道** |
| **AI 助手** | 工作台横幅：输入自然语言（如「客户问报价了吗」）→ 基于归档数据的回答 + 相关消息引用；系统已约束「只依据给定数据回答，没有就说没有」 |

未配置 LLM 时这些功能会明确报「AI 未配置」，不影响其余功能。

## 11. 备份

```bat
:: 手动备份（数据库一致性快照 + 配置）
cd /d D:\archcore
.venv\Scripts\python deploy\backup.py --db data\archcore.db --media data\media --config collector\config.yaml --out backups

:: 每天凌晨 3 点自动备份
schtasks /Create /TN "ArchCore-Backup" /TR "D:\archcore\.venv\Scripts\python.exe D:\archcore\deploy\backup.py --db D:\archcore\data\archcore.db --media D:\archcore\data\media --config D:\archcore\collector\config.yaml --out D:\archcore\backups" /SC DAILY /ST 03:00
```

备份目录建议复制一份到另一块盘/NAS。**恢复演练**（建议每季度做一次，验证备份真的能用）= 装 Python + 微信 4.1.8.67 → 还原 `archcore.db` 与配置 → 启动服务 → 重新扫码登录微信 → 恢复采集。

---

## 12. 常见问题排查

### 12.1 解密报「无内存密钥候选」/「内部密钥未找到」

按顺序排查：① 微信是否**已登录并在运行**（密钥在进程内存）；② 终端是否**管理员**权限；③ 装的是否为 4.1.8.67（其他 4.x 小版本密钥位置可能有差异，工具会打印扫描详情）；④ `Weixin.dll` 是否被更新过（版本变了则内部密钥位置变）。若确认微信已被升级，按 12.2 处理。

### 12.2 HMAC 异常率高（哨兵报警）/ 解密后表结构不符

机制变更信号，**直接原因几乎都是微信被升级**。处理：① 关闭自动更新（3.1）；② 用离线安装包回滚到 **4.1.8.67**；③ 重新登录后删 `data/wechat4_key.json` 重新提取密钥；④ 重跑解密。历史已归档数据（`archcore.db`）不受影响。若回滚后仍失败，附上工具输出的表结构摘要提 issue。

### 12.3 其他速查表

| 现象 | 原因与处理 |
|---|---|
| `pip install`/命令找不到 | 用 `.venv\Scripts\` 下的完整路径，或先 `.venv\Scripts\activate` |
| 管理台登录 401 | 服务端没起来（看 8000 端口窗口），或密码不对 |
| 登录后被强制跳改密页 | 正常机制（6.1）：用的是默认密码，改完重新登录 |
| 导入后管理台没数据 | 采集端 token 与服务端不一致；或白名单没放行任何会话（看第 7 步查询命令输出） |
| `--full` 重跑会重复入库吗 | 不会，svr_id 幂等去重 |
| 检索不到刚导入的词 | 中文关键词 ≥3 字走全文检索；2 字走模糊匹配；确认该消息在被白名单放行的会话里 |
| 自己的消息显示成「客户方」 | `collector_wxid` 填了带多开后缀的目录名（7 节注意事项），改成不带后缀的真实 wxid，改后重新 `--full` |
| 增量采不到新消息 | 微信没在本机登录在线；或确认常驻采集端/WAL 监听器在跑 |
| 「采集与通道」显示同步失败 | 看管道仪表的「最近失败」错误日志：解密失败→12.1/12.2；上报失败→服务端未启动或 token 不符 |
| 微信被自动升级导致解密失败 | 离线包回滚 4.1.8.67 → 重新登录 → 删除密钥缓存重提（12.2） |
| 卡片/图片/语音只有占位 | 见 13 已知限制（媒体本体归档为后续迭代项） |

## 13. 已知限制（诚实清单）

- **媒体本体**：图片/语音/视频/文件当前归档占位与元数据（大小/文件名/XML 富内容说明），本体提取与语音转文字是后续迭代项；
- **单机单账号**：只归档「本机登录的这个微信」的会话；想归档家人/同事的账号需要他们本机各跑一套（多采集端为后续评估项）；
- **版本冻结风险**：路线锚定 4.1.8.67，微信升级会失效（12.2 有回滚流程，但需要你保留离线安装包）；
- **实时性**：本机标准配置为分钟级（WAL 监听）到 30 分钟级（定时任务）；秒级需额外实时通道，属规划项；
- **不做任何发送**：系统只收不发，没有也不该有「替你回消息」的功能。

---

## 14. 版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.2 | 2026-10-15 | 路线同步：3.9.12+pywxdump → **4.1.8.67+自研解密**（第 3~4 节整体重写）；新增一键安装（1.1）与演示模式（第 2 节）；新增首启强制改密（6.1）、管道仪表（10.2）、AI 能力（10.3）；故障排查按新链路重写（12.1/12.2）；`collector_wxid` 多开后缀坑入档 |
| v1.1 | 2026-10-01 | 路径描述由「3.9.12+pywxdump」改为「4.x 解密归档」（局部标注） |
| v1.0 | 2026-09-23 | 初版（3.9.12 路线） |

---

*ArchCore 本机部署实操指南 v1.2 · 2026-10-15 · 内部资料。非官方接入存在违反微信用户协议的风险，仅供个人归档研究使用，商用前须完成合规评估（见[合规方案](compliance-plan.md)）。*

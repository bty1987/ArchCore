# ArchCore 单机部署手册（交付形态：Windows 采集主机）

> 形态：一台 Windows 主机承载 微信客户端 + collector + server + SQLite + 管理台静态产物。
> V1 平台可迁内网 Linux（collector 留在 Windows），见[运维规划](../docs/ops-promotion-plan.md) 2.1。
>
> **与[本机部署指南](../docs/local-deploy-guide.md)的分工**：那份面向「个人自用」的完整实操（含日常使用、AI 配置、故障排查）；本文面向「交付部署」——一键安装、进程守护、开机自启、验收清单与升级回滚。

> **版本口径（2026-10-15 正式改写）**：微信客户端**冻结 4.1.8.67**（3.9 整代登录被服务端拒，三次版本伪装实测无效）；采集主轨=**自研解密管线**（`scripts/decrypt_wechat4.py`：双引擎密钥提取 + 逐库派生 + WAL 合并），**非 pywxdump**（仅支持 3.x）。本文历史版本中的「3.9.12」读作「4.1.8.67」、「pywxdump」读作「自研解密轨」。

## 0. 前置条件

- [ ] Windows 10/11 x64 主机，不休眠、不锁屏（RDP 断开策略已调整）
- [ ] **微信 4.1.8.67 离线安装包**已存档，自动更新确认关闭
- [ ] 采集主号 + 备用号均已入群潜伏（[运维规划](../docs/ops-promotion-plan.md) 2.7），账号台账已建
- [ ] 离线安装包已存档：Python 3.10+、Node.js 18+（构建管理台用）、本仓库产物——**不依赖部署时外网下载**
- [ ] 版本组合已登记《采集管理页》（MVP-503 交付项）

## 1. 一键安装（首选）

```bat
:: 取代码并安装（venv + 依赖 + 配置生成 + 数据库迁移 + 管理台构建，共七步）
git clone https://gitee.com/bty1987/ArchCore.git D:\archcore
cd /d D:\archcore
install.bat
```

要点：

- 交互询问**采集号 wxid**（真实 wxid，**不带多开实例后缀**，如 `wxid_xxx` 而非 `wxid_xxx_a694`——它决定消息方向判定）；
- 生成 `start-server.bat`（含随机 JWT/采集 token 与 bootstrap 密码，**不入 git**）与 `collector\config.yaml`；
- **已存在的配置文件一律保留**，重复执行安全（可安全重跑）；
- 结束打印 bootstrap 密码；**首次登录会被强制改密**，改完重新登录。

**先验收安装**：双击 `start-server.bat` → 浏览器开 `http://127.0.0.1:8000` → admin + bootstrap 密码 → 强制改密 → 进工作台。
（想先看产品形态不碰真实数据：`run-demo.bat` 起隔离演示环境，admin / demo-arch-2026。）

## 2. 手工安装（等价步骤，便于排查）

```bat
cd /d D:\archcore
python -m venv .venv
.venv\Scripts\pip install -e server -e collector

:: 配置（生产值全部走环境变量或 start-server.bat，禁止写死进代码）
:: ARCHCORE_DB_URL / ARCHCORE_MEDIA_DIR / ARCHCORE_JWT_SECRET(32+ 位随机)
:: ARCHCORE_COLLECTOR_TOKEN(随机，与采集端一致) / ARCHCORE_COLLECTOR_WXID(采集号 wxid)
:: ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD(首启用，登录后强制改密)

cd server && ..\.venv\Scripts\alembic upgrade head && cd ..
```

管理台构建：

```bat
cd /d D:\archcore\web && npm install && npm run build
:: 产物 web/dist/ 交给 server 静态托管或任意内网静态服务器
```

## 3. 微信客户端安装

1. 安装微信 **4.1.8.67**（64 位；官方下载页只留最新版，须用存档的离线包）；
2. **关闭自动更新**（确认 `WeixinUpdate.exe` 不生效：改设置 + 必要时改名/断其网络）；
3. 用采集号扫码登录（4.1.8.67 直接可登，无需任何伪装）；
4. 记录数据目录：`xwechat_files/<账号>/db_storage/`（新装默认在用户根目录）。

## 4. 解密与采集

```bat
cd /d D:\archcore

:: 首次解密（管理员终端；微信保持登录运行以读取内存密钥）
.venv\Scripts\python scripts\decrypt_wechat4.py
:: 输出 data/wechat4_plain/<账号>/；密钥持久化 data/wechat4_key.json（之后无需微信在跑）

:: 全量历史导入
.venv\Scripts\archcore-collector -c collector\config.yaml --full

:: 单次增量
.venv\Scripts\archcore-collector -c collector\config.yaml --once
```

配置 `collector\config.yaml` 关键项（`install.bat` 已生成骨架）：

```yaml
source:
  type: wechat4                                  # 4.x 主轨
  db_dir: ./data/wechat4_plain/<账号>             # 解密输出目录
whitelist:
  allow_all: false                               # 商用必须 false（数据最小化，合规硬要求）
  groups: []                                     # 业务群白名单（xxx@chatroom）
  allow_dm: true
send_enabled: false                              # 永久 false：归档系统只收不发
```

> **白名单是合规边界**：非白名单会话的数据不出微信目录、不进上报通道。商用部署严禁 `allow_all: true`。

## 5. 服务化与开机自启

采集端常驻：

```bat
:: 方式一：启动文件夹（最简单）
:: 存为 %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\archcore-collector.bat
D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml

:: 方式二：任务计划
schtasks /Create /TN "ArchCore-Collector" /TR "D:\archcore\.venv\Scripts\archcore-collector.exe -c D:\archcore\collector\config.yaml" /SC ONLOGON
```

**双自动同步**（推荐配置，本机实例即如此）：

| 任务 | 内容 | 周期 |
|---|---|---|
| `ArchCore-Watch` | `scripts/watch_sync.py`（轮询消息库 mtime → 触发解密+采集），登录自启 | 分钟级 |
| `ArchCore-Sync` | `scripts/sync-wechat4.bat`（`decrypt --force` + `collector --once`） | 每 30 分钟兜底 |

```bat
schtasks /Create /TN "ArchCore-Sync" /TR "D:\archcore\scripts\sync-wechat4.bat" /SC MINUTE /MO 30
```

采集健康自查：管理台「采集与通道」→ **管道仪表**（成功率/平均耗时/最近成败/每日消息量）。验收计划任务时必须查 `LastTaskResult`（登记在[踩坑记录](../docs/retrospective-20260926.md)）。

服务端常驻：`start-server.bat` 已含启动逻辑（alembic 幂等 + uvicorn）；长期部署建议同样用启动文件夹/任务计划托管。

## 6. 交付验收清单（每客户一套）

- [ ] 微信 **4.1.8.67** 安装且自动更新已关；离线包已存档（唯一回滚手段）
- [ ] 采集主号 + 备用号均已入群潜伏；台账已登记
- [ ] collector/服务端进程守护配置；主机不休眠不锁屏
- [ ] 历史导入完成且对账视图无差异
- [ ] 群→客户映射完成；内部成员名单配置
- [ ] 通知渠道测试通过（企微 webhook 实发成功）
- [ ] **备份任务运行且首份备份已做恢复验证**（未验证的备份 = 没有备份）
- [ ] 版本冻结信息已登记到采集管理页
- [ ] 管理员/员工培训完成；员工知情沟通留痕；客户方成员入群告知话术已按[合规方案](../docs/compliance-plan.md)使用
- [ ] 合同/免责条款签署归档

## 7. 备份与恢复（RTO ≤ 2 小时）

```bat
:: 每日 03:00 自动备份（数据库 + media + 配置）
schtasks /Create /TN "ArchCore-Backup" /TR "D:\archcore\.venv\Scripts\python.exe D:\archcore\deploy\backup.py --db D:\archcore\data\archcore.db --media D:\archcore\data\media --config D:\archcore\collector\config.yaml --out D:\archcore\backups" /SC DAILY /ST 03:00
```

备份介质加密保管，本机 + 内网异地双份（禁止公有云盘）。**恢复流程**：备用机装 Python + 微信 **4.1.8.67** → 还原 `archcore.db`/`media/`/配置 → 启动服务 → 重新扫码登录 → 恢复采集。**每季度真实演练一次**。

## 8. 升级与回滚（重要）

**默认一切冻结**：微信版本、本仓库版本、Python 依赖全部锁定，禁止「顺手升级」。

- **微信被自动升级导致解密失效**（管道仪表会报 HMAC 异常/表结构不符）→ 用离线包**回滚 4.1.8.67** → 删除 `data/wechat4_key.json` → 重新登录后重跑解密（详见[本机部署指南](../docs/local-deploy-guide.md) 12.2）；
- **本仓库升级**：`git pull` → `pip install -e server -e collector` → `alembic upgrade head` → 重启服务（客户侧尚无自动升级通道，属规划项 #13）。

---

*ArchCore 单机部署手册 v2.0（2026-10-15 正式改写，取代 3.9.12 时代版本）· 内部资料。配套：[本机部署指南](../docs/local-deploy-guide.md)（个人自用完整实操）· [运维与推广规划](../docs/ops-promotion-plan.md)（日历/Runbook/账号资产）。*

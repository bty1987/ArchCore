# ArchCore 单机部署手册（Windows 采集主机，MVP 形态）

> 形态：一台 Windows 主机承载 微信客户端 + collector + server + SQLite + web 静态产物。
> V1 平台可迁内网 Linux（collector 留在 Windows），见运维规划 2.1。

## 0. 前置条件

- [ ] Windows 10/11 x64 主机，不休眠、不锁屏（RDP 断开策略已调整）
- [ ] 微信 3.9.12（32 位官方保留版）离线安装包，**关闭自动更新**
- [ ] 采集主号 + 备用号均已入群潜伏（运维规划 2.7），账号台账已建
- [ ] 离线安装包已存档：Python 3.11+、本仓库产物（不依赖部署时外网下载）
- [ ] 版本组合已登记《采集管理页》（MVP-503 交付项）

## 1. 安装平台服务端

```bat
:: 1) Python 3.11+ 与虚拟环境
python -m venv D:\archcore\venv
D:\archcore\venv\Scripts\pip install -e D:\archcore\server

:: 2) 配置（生产值全部走环境变量或 .env，禁止写死）
setx ARCHCORE_DB_URL sqlite:///D:/archcore/data/archcore.db
setx ARCHCORE_MEDIA_DIR D:/archcore/data/media
setx ARCHCORE_JWT_SECRET <32+ 位随机串>
setx ARCHCORE_COLLECTOR_TOKEN <随机串，与采集端一致>
setx ARCHCORE_COLLECTOR_WXID <采集号 wxid>
setx ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD <首次启动用，之后立即改密>

:: 3) 数据库迁移
cd D:\archcore\server
D:\archcore\venv\Scripts\alembic upgrade head

:: 4) 启动（NSSM 注册为 Windows 服务，进程守护见运维规划 2.2）
D:\archcore\venv\Scripts\uvicorn archcore_server.main:app --host 0.0.0.0 --port 8000
```

首次启动自动创建 `admin` 账号（密码取 `ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD`），**登录后立即改密并创建实名账号**。

## 2. 安装管理台前端

```bat
cd D:\archcore\web && npm install && npm run build
:: 产物 web/dist/ 交给 server 前的 Nginx/静态托管，或任意内网静态服务器
```

开发模式：`npm run dev`（已配置代理到 127.0.0.1:8000）。

## 3. 安装采集端

```bat
D:\archcore\venv\Scripts\pip install -e D:\archcore\collector

copy D:\archcore\collector\config.example.yaml D:\archcore\collector\config.yaml
:: 编辑 config.yaml：
::   server_ingest_token  = 与服务端 ARCHCORE_COLLECTOR_TOKEN 一致
::   collector_wxid       = 采集号 wxid
::   source.type          = pywxdump（生产）；db_dir = 解密库目录
::   whitelist.groups     = 业务群白名单（合规边界，白名单外数据不出微信目录）
```

调度：`archcore-collector` 常驻（APScheduler 小时级增量 + outbox 冲刷）；手动执行 `archcore-collector --full`（全量）或 `--once`（单次增量）。实时轨 `wcf_enabled: true` 仅在 M0 验证通过后开启。

## 4. 历史导入与初始化（对应 PRD 关键流程 ①）

1. `archcore-collector --full` 全量导入（进度看 server 日志与 /ingest/health）；
2. 管理台 → 采集管理：确认同步任务成功；
3. 管理台 → 客户：把待认领群映射到客户档案（半天工作坊，见交付流程 3.5）；
4. 系统设置：内部成员名单（sender_type 判定依据）、词库、通知渠道；
5. 首份备份并做一次恢复验证（`python deploy/backup.py`）。

## 5. 上线检查

逐项打勾《运维与推广规划》第 5 节清单（版本冻结、双号潜伏、对账无差异、通知实测、培训留痕、合同归档等）。

## 6. 备份与恢复

- 每日计划任务：`python D:\archcore\deploy\backup.py`（输出目录内网异地双份，加密保管）；
- 恢复：备用机装微信 3.9.12 + Python → 还原 archcore.db 与 media/ → 启动服务 → 扫码登录（RTO ≤ 2h，每月演练）。

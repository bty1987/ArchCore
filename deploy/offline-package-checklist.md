# ArchCore 离线交付包清单（#13）

> 用途：新客户部署与故障回滚都**不依赖部署时外网**（腾讯下载页只留最新版微信；npm/PyPI 可能不可达）。
> 打包后存内网固定目录（运维规划 2.5），随交付带至客户内网。每季度核对版本。

## 清单

| # | 项 | 来源 | 版本锚点 | 校验 |
|---|---|---|---|---|
| 1 | **微信 4.1.8.67 安装包**（64 位，`weixin_4.1.8.67.exe`） | SiverKing/wechat4.0-windows-versions release 存档 | 4.1.8.67（版本冻结，唯一回滚手段） | 文件字节数 + SHA256 + MZ 头 |
| 2 | **ArchCore 仓库快照**（zip：源码 + 本清单时刻的 tag） | `git archive` 或 Gitee 下载 | 与交付版本一致（`/api/v1/version` 的 git commit） | zip 完整性 |
| 3 | **Python 3.10+ 安装器**（本机实测 3.14 可用；保守交付 3.11/3.12 x64） | python.org 存档 | ≥3.10 | 安装器签名 |
| 4 | **Node.js 18+ 安装器**（仅管理台构建需要；已含 `web/dist/` 的快照可不带） | nodejs.org LTS | ≥18 | 安装器签名 |
| 5 | pip 离线轮子包（可选）：`pip download -e server -e collector -d wheels/` 产物 | PyPI 预下载 | 与交付时依赖锁定一致 | 目录清单 |
| 6 | 本清单 + 《[单机部署手册](install-windows.md)》 + 《[本机部署指南](../docs/local-deploy-guide.md)》打印件 | 仓库 | — | — |

## 打包命令（服务商侧，一次性）

```bat
:: 仓库快照(含子模块状态与版本接口锚点)
git -C D:\Svn\ArchCore archive --format=zip -o deliver\archcore-0.3.0.zip main

:: 依赖轮子(客户内网无 PyPI 时用;install.bat 改为 pip install --no-index --find-links wheels)
.venv\Scripts\pip download -e server -e collector -d deliver\wheels\
```

## 交付验收（离线环境重放）

- [ ] 断网状态下 `install.bat` 可完成（或 wheels 离线装依赖）
- [ ] `run-demo.bat` 演示可开
- [ ] 微信 4.1.8.67 可安装登录
- [ ] `/api/v1/version` 三层版本（app/git/db_revision）与交付登记一致

## 升级与回滚口径

- 在线升级：`upgrade.bat`（备份先行 → git pull → 依赖 → alembic → 前端构建）
- 离线升级：新版仓库 zip 覆盖 → 再跑 `upgrade.bat`（跳过 git pull 分支）
- 回滚：微信侧=离线包回装 4.1.8.67（[部署指南](../docs/local-deploy-guide.md) 12.2）；数据侧=`backups\pre-upgrade` 还原（§11）；应用侧=旧版仓库 zip 重装

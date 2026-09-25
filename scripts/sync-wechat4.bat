@echo off
rem ArchCore 定时同步：解密（拉 WAL 增量）→ 采集入库。由计划任务 ArchCore-Sync 每 30 分钟调用。
cd /d D:\Svn\ArchCore
echo ====== %date% %time% ====== >> data\sync.log
D:\Svn\ArchCore\.venv\Scripts\python scripts\decrypt_wechat4.py --data-root "D:\QMDownload\weixin\xwechat_files" --out data\wechat4_plain --force >> data\sync.log 2>&1
D:\Svn\ArchCore\.venv\Scripts\archcore-collector.exe -c collector\config.yaml --once >> data\sync.log 2>&1

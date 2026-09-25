@echo off
rem ArchCore scheduled sync: decrypt (WAL delta, --force) + collector incremental.
rem Scheduled task: ArchCore-Sync, every 30 minutes. Log: data\sync.log
cd /d D:\Svn\ArchCore
set PYTHONUTF8=1
echo ====== %date% %time% ====== >> data\sync.log
D:\Svn\ArchCore\.venv\Scripts\python -X utf8 scripts\decrypt_wechat4.py --data-root D:\QMDownload\weixin\xwechat_files --out data\wechat4_plain --force >> data\sync.log 2>&1
D:\Svn\ArchCore\.venv\Scripts\archcore-collector.exe -c collector\config.yaml --once >> data\sync.log 2>&1
exit /b 0
